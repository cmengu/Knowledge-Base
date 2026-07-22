"""The maturity state machine: from a position's evidence to its maturity flag.

:func:`compute_maturity` is the pure function the spec's Testing Decisions name
(``computeMaturity(position, config, now) -> flag``): given a position, the threshold
config, and the run time, it returns the single :class:`~kb.reconcile.schema.Maturity`
the position should hold. The reconciliation engine (ticket #08) calls it after every
change and records a transition when the flag moves, so maturity is *applied every batch*
rather than set once (ticket #09's Done-when).

The ladder ratchets on two signals — the number of **independent sources** (distinct
videos) and the **time span** they cover — and any contest short-circuits it:

* **contested** — the position holds both a supporting and an opposing source. This wins
  over everything: a single credible dissent reopens a question no matter how far up the
  ladder it had climbed (spec: "any adversarial unit resets to contested/open").
* **solved** — enough independent sources over a long span, and the position has never
  been contested.
* **converging** — enough independent sources agreeing over a meaningful span.
* **emerging** — at least a couple of independent sources, not yet enough to converge.
* **open** — too little evidence to say anything yet.

The thresholds live in :class:`MaturityConfig`, loaded from ``config/maturity.yaml`` so
they are tunable without code changes.

Scope note. This ships the spec's *default* thresholds so ticket #08 is runnable
end-to-end and can emit real ``maturity_transitions`` deltas. Because the function is
injected into ``reconcile``, ticket #09 can refine the policy (notably the true
"no contesting unit in the last N videos" rule, which needs the batch's video timeline
this position-only function approximates conservatively) without touching the engine.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from kb.config import CONFIG_DIR, load_yaml
from kb.reconcile.schema import Maturity, Position

__all__ = ["MaturityConfig", "compute_maturity", "maturity_reason", "load_maturity_config"]


class MaturityConfig(BaseModel):
    """Tunable thresholds for the maturity ladder (spec defaults; ``config/maturity.yaml``).

    "Independent sources" means distinct source videos; "span" means days between the
    oldest and newest source. Three months is encoded as 90 days.
    """

    model_config = ConfigDict(extra="forbid")

    emerging_min_sources: int = Field(
        default=2, ge=1, description="≥ this many independent sources to leave open-question."
    )
    converging_min_sources: int = Field(
        default=3, ge=1, description="≥ this many independent sources to converge."
    )
    converging_min_span_days: int = Field(
        default=90, ge=0, description="Span the converging sources must cover (≈3 months)."
    )
    solved_min_sources: int = Field(
        default=3, ge=1, description="≥ this many independent sources to be settled."
    )
    solved_min_span_days: int = Field(
        default=180, ge=0, description="Span a solved position must cover, uncontested throughout."
    )


def _ever_contested(position: Position) -> bool:
    """Whether the position was ever contested (any contested entry in its history).

    The conservative stand-in for "no contesting unit in the last N videos": ticket #08's
    position-only default will not promote a once-contested position to ``solved`` even
    after it quiets down; ticket #09 can implement the true windowed rule with batch
    context.
    """

    return any(event.to_maturity is Maturity.contested for event in position.status_history)


def compute_maturity(
    position: Position, *, now: dt.datetime, config: MaturityConfig | None = None
) -> Maturity:
    """Return the maturity flag ``position`` should hold given ``config`` and ``now``.

    Pure and deterministic: depends only on the position's sources and history, the
    thresholds, and (reserved for future windowed rules) the run time. ``now`` is accepted
    to match the spec's ``computeMaturity(position, config, now)`` signature and to let a
    later policy reason about recency; the default ladder does not need it.
    """

    config = config or MaturityConfig()

    # A live disagreement overrides the ladder entirely.
    if position.is_contested:
        return Maturity.contested

    sources = len(position.distinct_videos)   # independent sources = distinct videos
    span = position.span_days or 0

    if (
        sources >= config.solved_min_sources
        and span >= config.solved_min_span_days
        and not _ever_contested(position)
    ):
        return Maturity.solved
    if sources >= config.converging_min_sources and span >= config.converging_min_span_days:
        return Maturity.converging
    if sources >= config.emerging_min_sources:
        return Maturity.emerging_trend
    return Maturity.open_question


def maturity_reason(position: Position, flag: Maturity) -> str:
    """A plain-words reason for a *ladder* transition to ``flag`` (for the status history).

    Contested transitions are recorded by the engine with the reconciliation attempt's own
    reason, so this covers only the open/emerging/converging/solved rungs; it falls back to
    a generic line if handed ``contested``.
    """

    sources = len(position.distinct_videos)
    span = position.span_days or 0
    if flag is Maturity.solved:
        return f"settled — {sources} independent sources over {span}d, no contest"
    if flag is Maturity.converging:
        return f"converging — {sources} independent sources agreeing over {span}d"
    if flag is Maturity.emerging_trend:
        return f"emerging — {sources} independent sources so far ({span}d span)"
    if flag is Maturity.open_question:
        return "open question — a single source so far"
    return "contested — credible sources disagree"


def load_maturity_config(path: str | Path | None = None) -> MaturityConfig:
    """Load :class:`MaturityConfig` from YAML (defaults when the file is absent)."""

    path = Path(path) if path is not None else CONFIG_DIR / "maturity.yaml"
    if not path.exists():
        return MaturityConfig()
    return MaturityConfig.model_validate(load_yaml(path) or {})
