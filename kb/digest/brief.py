"""The narrative topic brief — an LLM-written lede atop each digest (issue #19).

The first real evals run opened 31 positions, and the reader's feedback was blunt: the
per-position list is too much to scroll. What they wanted instead is a *detailed narrative
summary* per topic — roughly 500–1000 words — that sums up the whole topic's state so the
position list becomes an appendix, not the main read. This module produces that brief; the
renderer (:mod:`kb.digest.render`) drops it in as the first section and collapses the full
position list beneath it.

The brief LEADS with contradictions, by design and by prompt: every contested position, what
the two sides claim, which videos hold each side, and how the adjudicator resolved it (or
that it stands unresolved). Only then does it turn to what is emerging or converging, the big
open questions, and what changed this run. That ordering mirrors the whole pipeline's
posture — it critiques rather than predicts, so the live disagreements come first.

Like every other model call in this repo the LLM is an **injected dependency**: the briefer
depends on the narrow :class:`~kb.extract.llm.LLMClient` protocol (``complete(system, prompt,
model) -> str``), never on a concrete SDK. Production wires an
:class:`~kb.extract.llm.AgentSDKClient` at ``model=claude-opus-4-8`` (the strongest tier, on
the subscription credit); tests inject a scripted fake and never make a live call. Building
the prompt (:func:`build_brief_prompt`) is separated from calling the model
(:class:`TopicBriefer`) so tests can assert prompt content — that the contested claims are in
it — without any network.

**Word-count guard.** The model is asked for 500–1000 words. If it returns fewer than
:data:`MIN_WORDS` or more than :data:`MAX_WORDS`, the briefer retries **once** with a
corrective instruction; whatever the retry returns is then accepted (a warning is logged if
it is still out of range). The brief is a human read, not a machine contract — a slightly
off-length brief is far better than a failed run with no brief at all.

The rendering stays pure and deterministic: :class:`TopicBriefer` produces the *string*, and
:func:`~kb.digest.render.render_digest` takes that string as an optional argument. A render
with ``brief=None`` is byte-identical to today's, so existing callers and tests are
untouched.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from kb.extract.llm import LLMClient
from kb.reconcile.deltas import (
    Citation,
    ConfirmedDelta,
    ContestedDelta,
    Deltas,
    MaturityTransitionDelta,
    NetNewDelta,
    Reconciliation,
)
from kb.reconcile.schema import Position
from kb.reconcile.store import KBStore

__all__ = [
    "BRIEF_MODEL",
    "MIN_WORDS",
    "MAX_WORDS",
    "BriefConfig",
    "TopicBriefer",
    "build_brief_prompt",
    "word_count",
    "SYSTEM_PROMPT",
]

_log = logging.getLogger(__name__)

# The strongest tier, on the Claude subscription via the Agent SDK — the brief is the one
# piece of editorial synthesis in the pipeline, so it gets Opus (mirrors the adjudicator).
BRIEF_MODEL = "claude-opus-4-8"

# The 500–1000-word ask, with a tolerance band the guard enforces. A brief outside [400,
# 1200] triggers one corrective retry; outside after that is accepted with a logged warning.
MIN_WORDS = 400
MAX_WORDS = 1200


class BriefConfig(BaseModel):
    """Knobs for the real briefer (the model tier; the word band is a module constant)."""

    model_config = ConfigDict(extra="forbid")

    model: str = Field(
        default=BRIEF_MODEL,
        description="Agent SDK model for the brief — Opus, the strongest tier (spec us. 28).",
    )


# --- prompt ----------------------------------------------------------------

SYSTEM_PROMPT = """\
You are the EDITOR of a knowledge base that tracks what YouTube videos claim about an AI \
topic. Each run reconciles new videos against the tracked "positions" (claims) and produces \
a diff. Your job is to write the opening BRIEF for the digest: a detailed narrative summary \
of where the whole topic stands, so a reader gets the state of the field from your prose \
alone and only drills into the position list for detail.

Write 500 to 1000 words of plain, flowing PROSE. Not bullet points, not a list, not an \
outline. Use only 2 or 3 natural paragraph breaks; do NOT write section headers or headings \
of any kind inside the brief.

LEAD WITH CONTRADICTIONS. This is the most important rule. Open with the genuine \
disagreements. For EACH contested position, in prose:
  - state what the position claims and what the dissent claims — the two sides plainly;
  - name which video(s) back each side (use the source video ids and dates given to you);
  - say how the adjudicator resolved it — or, just as often and just as valid, that it \
stands UNRESOLVED ("genuinely open"). Never invent a resolution that the data does not show; \
an honest "this remains unsettled" is the expected answer.

Only AFTER the contradictions, move on to: what is emerging or converging (which claims are \
gathering independent support and appear to be settling), the big open questions the topic \
has not answered, and finally what actually CHANGED in this run (new positions opened, fresh \
evidence, positions that matured or reopened).

Do not smooth disagreements into a tidy consensus and do not forecast. This brief critiques; \
it does not predict. Quote or paraphrase faithfully from the material you are given and do \
not introduce claims that are not in it. Return ONLY the prose of the brief — no title, no \
preamble, no markdown, no closing sign-off."""


def _fmt_citation(c: Citation) -> str:
    return f'"{c.quote.strip()}" — {c.video_id} · {c.date.isoformat()}'


def _fmt_reconciliation(r: Reconciliation) -> str:
    outcome = "RESOLVED" if r.reconciled else "UNRESOLVED (genuinely open)"
    return f"{r.type.value} disagreement, {outcome}: {r.explanation.strip()}"


def _fmt_contested(d: ContestedDelta) -> str:
    flip = (
        "flipped to contested this run"
        if d.became_contested
        else "already contested, took a further dissent this run"
    )
    return "\n".join(
        [
            f'- position {d.position_id} ({flip}): "{d.position_statement}"',
            f"    supporting side: {_fmt_citation(d.supporting)}",
            f"    opposing side:   {_fmt_citation(d.opposing)}",
            f"    adjudication: {_fmt_reconciliation(d.reconciliation)}",
        ]
    )


def _fmt_contested_position(p: Position) -> str:
    """A standing contested position (from the KB), both stances quoted from its sources."""

    lines = [f'- position {p.position_id}: "{p.statement}"']
    for s in p.supporting_sources:
        lines.append(f'    supporting: "{s.quote.strip()}" — {s.video_id} · {s.date.isoformat()}')
    for s in p.opposing_sources:
        lines.append(f'    opposing:   "{s.quote.strip()}" — {s.video_id} · {s.date.isoformat()}')
    return "\n".join(lines)


def _fmt_net_new(d: NetNewDelta) -> str:
    return f'- {d.position_id}: "{d.statement}" (opened by {d.citation.video_id} · {d.citation.date.isoformat()})'


def _fmt_confirmed(d: ConfirmedDelta) -> str:
    return (
        f'- {d.position_id} ({d.kind.value}): "{d.position_statement}" '
        f"— reinforced by {d.citation.video_id} · {d.citation.date.isoformat()}"
    )


def _fmt_transition(t: MaturityTransitionDelta) -> str:
    return f'- {t.position_id}: {t.from_maturity} → {t.to_maturity} — {t.reason} ("{t.statement}")'


def _fmt_position_line(p: Position) -> str:
    n = len(p.distinct_videos)
    src = "1 source" if n == 1 else f"{n} sources"
    return f'- [{p.maturity.value}] {p.position_id}: "{p.statement}" ({src})'


def build_brief_prompt(
    topic: str,
    positions: KBStore | Sequence[Position] | None,
    deltas: Deltas,
) -> tuple[str, str]:
    """Return ``(system, user)`` prompts for a narrative brief of ``topic``.

    The user turn hands the model everything it needs to write the brief without a join:
    every currently-contested position with both stances quoted, the current state of the
    field (each position with its maturity), and this run's diff broken into the newly
    contested, net-new, confirmed, and maturity-transition buckets — each contested item
    carrying both competing quotes with source + date and the typed reconciliation outcome,
    so the "lead with contradictions" instruction has concrete material to lead with.
    """

    pos_list = _normalize_positions(positions)

    body: list[str] = [f"TOPIC: {topic}", ""]

    standing_contested = (
        [p for p in pos_list if p.is_contested] if pos_list is not None else []
    )
    if standing_contested:
        body.append(f"CURRENTLY CONTESTED POSITIONS ({len(standing_contested)}):")
        body.append(
            "Lead your brief with these. Each keeps both stances; say who claims what, "
            "which videos back each side, and how (or whether) it was resolved."
        )
        body += [_fmt_contested_position(p) for p in standing_contested]
        body.append("")

    body.append("THIS RUN'S CHANGES (the diff since the last run):")
    if deltas.newly_contested:
        body.append(f"  Newly contested ({len(deltas.newly_contested)}):")
        body += [_fmt_contested(d) for d in deltas.newly_contested]
    if deltas.net_new:
        body.append(f"  Net-new positions ({len(deltas.net_new)}):")
        body += [_fmt_net_new(d) for d in deltas.net_new]
    if deltas.newly_confirmed:
        body.append(f"  Newly confirmed ({len(deltas.newly_confirmed)}):")
        body += [_fmt_confirmed(d) for d in deltas.newly_confirmed]
    if deltas.maturity_transitions:
        body.append(f"  Maturity transitions ({len(deltas.maturity_transitions)}):")
        body += [_fmt_transition(t) for t in deltas.maturity_transitions]
    if deltas.is_empty:
        body.append("  Nothing changed this run — summarize where the field stands and rests.")
    body.append("")

    if pos_list:
        body.append(f"CURRENT STATE OF THE FIELD ({len(pos_list)} positions):")
        body += [_fmt_position_line(p) for p in pos_list]
        body.append("")

    body.append(
        "Write the brief now: 500–1000 words of prose, contradictions first, then what is "
        "emerging/converging, the open questions, and what changed this run."
    )
    return SYSTEM_PROMPT, "\n".join(body)


# --- the real briefer ------------------------------------------------------


def word_count(text: str) -> int:
    """Whitespace-delimited word count — the measure the length guard uses."""

    return len(text.split())


class TopicBriefer:
    """Real briefer — Opus over an injected :class:`~kb.extract.llm.LLMClient`.

    Reuses the same LLM seam as extraction and adjudication: production wires an
    :class:`~kb.extract.llm.AgentSDKClient` and this drives it at ``model=claude-opus-4-8``.
    :meth:`brief` builds the prompt, calls the model, and enforces the word-count guard (one
    corrective retry, then accept-with-warning), returning the brief's prose as a string for
    :func:`~kb.digest.render.render_digest` to place.
    """

    def __init__(self, llm: LLMClient, *, config: BriefConfig | None = None) -> None:
        self._llm = llm
        self._config = config or BriefConfig()

    def brief(
        self,
        *,
        topic: str,
        positions: KBStore | Sequence[Position] | None,
        deltas: Deltas,
    ) -> str:
        """Generate the narrative brief for ``topic`` and return its prose.

        Calls the model once; if the result is outside the [``MIN_WORDS``, ``MAX_WORDS``]
        band, calls once more with a corrective instruction and accepts whatever comes back
        (logging a warning if it is still out of range).
        """

        system, user = build_brief_prompt(topic, positions, deltas)
        raw = self._llm.complete(system=system, prompt=user, model=self._config.model)
        text = raw.strip()
        n = word_count(text)
        if MIN_WORDS <= n <= MAX_WORDS:
            return text

        corrective = f"{user}\n\n{_corrective(n)}"
        raw = self._llm.complete(system=system, prompt=corrective, model=self._config.model)
        text = raw.strip()
        n = word_count(text)
        if not (MIN_WORDS <= n <= MAX_WORDS):
            _log.warning(
                "topic brief for %r is %d words, outside [%d, %d] after one retry; "
                "accepting it anyway",
                topic,
                n,
                MIN_WORDS,
                MAX_WORDS,
            )
        return text


def _corrective(n: int) -> str:
    if n < MIN_WORDS:
        return (
            f"Your previous draft was only {n} words — too short. Rewrite it at 500 to 1000 "
            "words of plain prose, keeping the contradiction-first structure: every contested "
            "position with both sides, the videos behind each, and how it was (or was not) "
            "resolved, then what is emerging/converging, the open questions, and what changed."
        )
    return (
        f"Your previous draft was {n} words — too long. Tighten it to 500 to 1000 words of "
        "plain prose without dropping any contested position: keep both sides, the videos "
        "behind each, and the resolution (or that it is unresolved) for every disagreement."
    )


def _normalize_positions(
    positions: KBStore | Sequence[Position] | None,
) -> list[Position] | None:
    if positions is None:
        return None
    if isinstance(positions, KBStore):
        return positions.positions()
    return sorted(positions, key=lambda p: p.position_id)
