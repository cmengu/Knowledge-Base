"""Stage 2 of the matcher: the Opus "manager" that adjudicates a unit against candidates.

Stage 1 retrieves the few positions closest to an incoming unit; this stage *judges* them.
It is where the spec's rule "never merge on embedding distance alone" is enforced: a
:class:`Verdict` is produced by reading meaning, not by comparing vectors. Each unit is
classified as one of:

* **confirming** — the same claim as an existing position; split into ``redundant`` (adds
  nothing) vs ``new-evidence`` (a fresh independent voice that strengthens it);
* **novel** — matches none of the candidates; becomes a new open position;
* **adversarial** — contradicts an existing position; the position is flagged contested,
  holding *both* stances, with a typed :class:`~kb.reconcile.deltas.Reconciliation`
  attempt (empirical / definitional / contextual) whose common, first-class outcome is
  ``unreconciled — genuinely open``.

Like the extraction LLM seam this is an **injected dependency** (:class:`Adjudicator`):
the engine and its tests depend on the protocol, not on Opus. Production injects
:class:`OpusAdjudicator` (the real model, ``model=opus`` on the Claude subscription via the
same :class:`~kb.extract.llm.LLMClient` used for extraction); tests inject a scripted fake.

**The anti-manufactured-agreement guardrail is baked into the prompt** (:data:`SYSTEM_PROMPT`)
as a hard requirement, not a nicety: when adjudicating an adversarial unit the model must
quote the specific competing claims with their source + date, must never merge a claim with
its negation, and is told that leaving a disagreement unreconciled is the honest, expected
answer.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from kb.extract import extract_json_object
from kb.extract.llm import ExtractionError, LLMClient
from kb.reconcile.deltas import ConfirmingKind, Reconciliation
from kb.reconcile.incoming import IncomingUnit
from kb.reconcile.schema import Position

__all__ = [
    "Classification",
    "Verdict",
    "Adjudicator",
    "OpusAdjudicator",
    "AdjudicationConfig",
    "AdjudicationError",
    "parse_verdict",
    "build_adjudication_prompt",
    "SYSTEM_PROMPT",
    "ADJUDICATOR_MODEL",
]

ADJUDICATOR_MODEL = "opus"


class AdjudicationError(Exception):
    """Raised when the adjudicator cannot produce a usable verdict.

    Covers a non-JSON or schema-invalid model response and a verdict that names a target
    position outside the candidate set handed to it.
    """


class Classification(str, Enum):
    """How an incoming unit relates to the topic's existing positions.

    * ``confirming``   — the same claim as a candidate position (agrees with it).
    * ``novel``        — matches none of the candidates; open a new position.
    * ``adversarial``  — contradicts a candidate position; flag it contested.
    """

    confirming = "confirming"
    novel = "novel"
    adversarial = "adversarial"


class Verdict(BaseModel):
    """The adjudicator's decision for one incoming unit.

    A single disposition per unit — the engine takes exactly one action from it. Which
    fields are required depends on :attr:`classification`, enforced by the validator below
    so a malformed verdict is rejected at the seam rather than misapplied:

    * ``confirming``   → ``target_position_id`` + ``confirming_kind`` (no reconciliation);
    * ``novel``        → no target; ``canonical_statement`` names the position to open;
    * ``adversarial``  → ``target_position_id`` + ``reconciliation`` (no confirming_kind).
    """

    model_config = ConfigDict(extra="forbid")

    classification: Classification = Field(description="confirming / novel / adversarial.")
    target_position_id: str | None = Field(
        default=None,
        description="The matched candidate's id (confirming/adversarial); None for novel.",
    )
    confirming_kind: ConfirmingKind | None = Field(
        default=None,
        description="redundant vs new-evidence — required iff confirming.",
    )
    reconciliation: Reconciliation | None = Field(
        default=None,
        description="The typed reconciliation attempt — required iff adversarial.",
    )
    canonical_statement: str | None = Field(
        default=None,
        description="For a novel unit, the affirmative statement to open the new position with.",
    )
    rationale: str = Field(
        min_length=1,
        description="Why this classification — for adversarial, quoting the competing claims.",
    )

    @model_validator(mode="after")
    def _check_shape(self) -> "Verdict":
        c = self.classification
        if c is Classification.confirming:
            if not self.target_position_id:
                raise ValueError("a confirming verdict must name target_position_id")
            if self.confirming_kind is None:
                raise ValueError("a confirming verdict must set confirming_kind")
            if self.reconciliation is not None:
                raise ValueError("a confirming verdict must not carry a reconciliation")
        elif c is Classification.adversarial:
            if not self.target_position_id:
                raise ValueError("an adversarial verdict must name target_position_id")
            if self.reconciliation is None:
                raise ValueError("an adversarial verdict must carry a reconciliation")
            if self.confirming_kind is not None:
                raise ValueError("an adversarial verdict must not set confirming_kind")
        else:  # novel
            if self.target_position_id is not None:
                raise ValueError("a novel verdict must not name a target_position_id")
            if self.confirming_kind is not None or self.reconciliation is not None:
                raise ValueError("a novel verdict carries neither confirming_kind nor reconciliation")
        return self


@runtime_checkable
class Adjudicator(Protocol):
    """Stage-2 judgment: classify one incoming unit against its candidate positions.

    Implementations must return exactly one :class:`Verdict`. When the verdict names a
    target it must be one of the ``candidates`` passed in. The engine only calls this when
    there is at least one candidate — an empty candidate set is novel by construction and
    spends no judgment.
    """

    def adjudicate(self, *, unit: IncomingUnit, candidates: Sequence[Position]) -> Verdict: ...


class AdjudicationConfig(BaseModel):
    """Knobs for the real adjudicator (loaded from ``config/reconciliation.yaml``)."""

    model_config = ConfigDict(extra="forbid")

    model: str = Field(
        default=ADJUDICATOR_MODEL,
        description="Agent SDK model for adjudication — Opus, the strongest tier (spec).",
    )


# --- prompt ----------------------------------------------------------------

SYSTEM_PROMPT = """\
You are the MANAGER of a knowledge base about AI topics. Videos are broken into "units"; \
each unit is compared against the existing "positions" (tracked claims) for its topic. \
Your job: decide how ONE new unit relates to a short list of candidate positions, and \
return a single JSON verdict.

Classify the unit as exactly one of:
  - "confirming":   it makes the SAME claim as one candidate position (agrees with it).
        Then set "confirming_kind":
          "redundant"    -> it adds nothing new (the position already says this).
          "new-evidence" -> it is a fresh, independent voice that strengthens the position.
  - "novel":        it matches NONE of the candidates. It becomes a new open position.
        Provide "canonical_statement": the claim phrased affirmatively, in your own words.
  - "adversarial":  it CONTRADICTS one candidate position. The position becomes contested \
and keeps BOTH stances.

Judge by MEANING, not by surface wording or similarity. A claim and its NEGATION often \
sound alike — they are adversarial, never confirming. Never merge two claims just because \
they are phrased similarly.

GUARDRAIL — this is a hard requirement, not a preference:
  - For an "adversarial" verdict, your "rationale" MUST quote the specific competing \
claims and attribute each with its source video id and date: quote what the existing \
position says (from its sources) and quote what the new unit says.
  - Then fill "reconciliation":
        "type": why they disagree:
            "empirical"    -> a question of fact/measurement (checkable who is right),
            "definitional" -> they mean different things by the same term,
            "contextual"   -> both hold in different settings ("it depends").
        "reconciled": true ONLY if the disagreement genuinely resolves. Leaving it \
unreconciled ("reconciled": false) is the HONEST and COMMON answer — do NOT manufacture \
a tidy agreement that isn't real.
        "explanation": in plain words, why they disagree; if reconciled, how.

Output ONLY a single JSON object with EXACTLY these fields (omit the ones marked optional \
when they do not apply):
  {
    "classification": "confirming" | "novel" | "adversarial",
    "target_position_id": "<candidate id>",        // confirming/adversarial only; omit for novel
    "confirming_kind": "redundant" | "new-evidence", // confirming only
    "canonical_statement": "<affirmative claim>",    // novel only
    "reconciliation": {                              // adversarial only
        "type": "empirical" | "definitional" | "contextual",
        "reconciled": false,
        "explanation": "<why they disagree>"
    },
    "rationale": "<why this classification; quote competing claims for adversarial>"
  }
No prose, no markdown, no code fences — just the JSON object."""


def _render_candidate(position: Position) -> str:
    lines = [
        f'- position_id: {position.position_id}',
        f'  maturity: {position.maturity.value}',
        f'  statement: "{position.statement}"',
        "  existing sources:",
    ]
    for source in position.sources:
        side = source.alignment.value
        lines.append(
            f'    [{side}] "{source.quote.strip()}" '
            f"— {source.video_id} · {source.date.isoformat()} · {source.stance.value}"
        )
    return "\n".join(lines)


def build_adjudication_prompt(
    unit: IncomingUnit, candidates: Sequence[Position]
) -> tuple[str, str]:
    """Return ``(system, user)`` prompts for adjudicating ``unit`` against ``candidates``.

    The user turn spells out the incoming unit (statement, verbatim quote, stance, source,
    date, evidence) and every candidate position with its statement and its sources quoted
    and dated — the material the guardrail requires the model to weigh and cite.
    """

    u = unit.unit
    evidence = ", ".join(u.evidence_offered) if u.evidence_offered else "(none offered)"
    body = [
        "NEW UNIT to classify:",
        f'  statement: "{u.text}"',
        f'  verbatim quote: "{u.raw_quote.strip()}"',
        f"  stance: {u.stance.value}",
        f"  source video: {unit.video_id}",
        f"  date: {unit.date.isoformat()}",
        f"  evidence offered: {evidence}",
        "",
        f"CANDIDATE POSITIONS ({len(candidates)}):",
    ]
    for position in candidates:
        body.append(_render_candidate(position))
    body += [
        "",
        "Return the single JSON verdict as instructed. If the unit matches none of the "
        "candidates, classify it novel.",
    ]
    return SYSTEM_PROMPT, "\n".join(body)


# --- parsing + the real adjudicator ----------------------------------------


def parse_verdict(raw: str) -> Verdict:
    """Parse a raw adjudicator response into a validated :class:`Verdict`.

    Tolerates a model that wraps its JSON in prose or fences (reusing the extraction
    layer's brace-matching scan). Raises :class:`AdjudicationError` on non-JSON output or
    a payload that violates the verdict schema.
    """

    try:
        payload = extract_json_object(raw)
    except ExtractionError as exc:
        raise AdjudicationError(f"adjudicator response contained no JSON object: {exc}") from exc
    try:
        return Verdict.model_validate_json(payload)
    except Exception as exc:  # pydantic ValidationError -> uniform adjudicator failure
        raise AdjudicationError(f"adjudicator output did not match the verdict schema: {exc}") from exc


class OpusAdjudicator:
    """Real :class:`Adjudicator` — the Opus manager over an injected :class:`LLMClient`.

    Reuses the same LLM seam as extraction: production wires an
    :class:`~kb.extract.llm.AgentSDKClient` and this drives it at ``model=opus`` on the
    subscription credit. Building the prompt, calling the model, and parsing the verdict
    are separated so the prototype can record a real response and tests can replay it
    through :func:`parse_verdict` with no live call.
    """

    def __init__(self, llm: LLMClient, *, config: AdjudicationConfig | None = None) -> None:
        self._llm = llm
        self._config = config or AdjudicationConfig()

    def adjudicate(self, *, unit: IncomingUnit, candidates: Sequence[Position]) -> Verdict:
        system, prompt = build_adjudication_prompt(unit, candidates)
        raw = self._llm.complete(system=system, prompt=prompt, model=self._config.model)
        verdict = parse_verdict(raw)
        self._check_target(verdict, candidates)
        return verdict

    @staticmethod
    def _check_target(verdict: Verdict, candidates: Sequence[Position]) -> None:
        if verdict.target_position_id is None:
            return
        ids = {p.position_id for p in candidates}
        if verdict.target_position_id not in ids:
            raise AdjudicationError(
                f"verdict targets {verdict.target_position_id!r}, not among candidates {sorted(ids)}"
            )
