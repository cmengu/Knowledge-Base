"""Render a topic's positions as human-readable Markdown (Layer 4, ticket #06).

The canonical store is JSON; this Markdown is a *derived* view, rewritten from the JSON
on every save. Its job is to make the KB legible at a glance and to diff cleanly in git,
so a reader (or a code review) can see what changed between runs by reading the diff.

Two spec requirements drive the layout:

* **Contested positions quote both stances with source + date.** Each position lists its
  supporting sources and, when contested, its opposing sources — every source shown with
  its verbatim quote, video id, and date. Disagreement is displayed side by side, never
  smoothed into one narrative.
* **The status history shows when it converged.** Each position ends with its maturity
  timeline, one line per transition with the date it happened.

Rendering is deterministic: positions are emitted in ``position_id`` order and sources in
attachment order, so re-rendering unchanged data produces byte-identical output.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable

from kb.reconcile.schema import Position, PositionSource

__all__ = ["render_markdown", "MATURITY_BADGE"]

# A small glyph per maturity so the rendered KB scans quickly. Purely cosmetic; the JSON
# remains the source of truth for the flag.
MATURITY_BADGE = {
    "open-question": "○ open question",
    "emerging-trend": "◔ emerging trend",
    "converging": "◑ converging",
    "solved": "● solved",
    "contested": "⚔ contested",
}


def _fmt_date(value: dt.date) -> str:
    return value.isoformat()


def _fmt_datetime(value: dt.datetime) -> str:
    # Date granularity is enough for the human timeline; the JSON keeps the full stamp.
    return value.date().isoformat()


def _render_source(source: PositionSource) -> list[str]:
    lines = [
        f'- "{source.quote.strip()}"',
        f"  — {source.video_id} · {_fmt_date(source.date)} · {source.stance.value} · `{source.unit_id}`",
    ]
    if source.evidence_offered:
        lines.append(f"  evidence: {', '.join(source.evidence_offered)}")
    return lines


def _render_history(position: Position) -> list[str]:
    lines = ["**Status history**", ""]
    for event in position.status_history:
        arrow = (
            f"{event.from_maturity.value} → {event.to_maturity.value}"
            if event.from_maturity is not None
            else f"opened as {event.to_maturity.value}"
        )
        line = f"- {_fmt_datetime(event.at)} — {arrow}: {event.reason}"
        if event.trigger_unit_id:
            line += f" (`{event.trigger_unit_id}`)"
        lines.append(line)
    return lines


def _render_position(position: Position) -> list[str]:
    badge = MATURITY_BADGE.get(position.maturity.value, position.maturity.value)
    span = position.span_days
    if span is None:
        span_text = "no sources"
    elif span == 0:
        span_text = "same-day"
    else:
        span_text = f"{span}-day span"
    lines = [
        f"## {position.position_id} — {badge}",
        "",
        f"**{position.statement}**",
        "",
        f"_{len(position.distinct_videos)} source(s) · {span_text}_",
        "",
    ]

    supporting = position.supporting_sources
    opposing = position.opposing_sources

    # For a contested position show both sides under explicit headings; for an
    # uncontested one a single "Sources" list reads more naturally.
    if position.is_contested:
        lines += ["**Supporting**", ""]
        for source in supporting:
            lines += _render_source(source)
        lines += ["", "**Opposing** (contested — both stances kept)", ""]
        for source in opposing:
            lines += _render_source(source)
        lines.append("")
    else:
        lines += ["**Sources**", ""]
        for source in position.sources:
            lines += _render_source(source)
        lines.append("")

    lines += _render_history(position)
    lines.append("")
    return lines


def render_markdown(positions: Iterable[Position], *, topic: str) -> str:
    """Render all of a topic's positions as one Markdown document.

    ``positions`` is rendered in the order given; the store passes them sorted by
    ``position_id`` for a stable, diff-friendly file. A topic with no positions still
    yields a valid document (a header and a short note) rather than an empty file.
    """

    positions = list(positions)
    contested = sum(1 for p in positions if p.is_contested)
    lines = [
        f"# Knowledge base — {topic}",
        "",
        (
            f"{len(positions)} position(s), {contested} contested. "
            "Canonical data lives in `positions.json`; this file is a rendered view."
        ),
        "",
    ]
    if not positions:
        lines += ["_No positions yet._", ""]
        return "\n".join(lines).rstrip() + "\n"

    for position in positions:
        lines += _render_position(position)
    return "\n".join(lines).rstrip() + "\n"
