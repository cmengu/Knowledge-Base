"""The typed KB diff a reconciliation run emits (Layer 5 output, ticket #08).

The daily digest (ticket #10) is *literally a diff of the knowledge base* since the last
run, so ``reconcile`` returns not just the updated KB but a structured :class:`Deltas`
describing exactly what changed. The shape mirrors the four things the digest shows per
topic (spec user story 23):

* :attr:`Deltas.newly_confirmed` — units that strengthened an existing position, split
  into ``redundant`` (low value) vs ``new-evidence`` (a fresh independent voice);
* :attr:`Deltas.net_new` — brand-new open positions the run opened;
* :attr:`Deltas.newly_contested` — positions a dissent contested, each carrying *both*
  competing claims quoted with source + date and the typed reconciliation attempt;
* :attr:`Deltas.maturity_transitions` — every maturity flag that moved this run, with the
  from/to and the reason, so the digest can show *when* something converged or reopened.

Every entry is self-contained and JSON-serializable: the digest renderer consumes a
:class:`Deltas` directly and never has to join back to the KB. The guardrail against
manufactured agreement is structural here — a :class:`ContestedDelta` cannot be built
without both a supporting and an opposing :class:`Citation`.
"""

from __future__ import annotations

import datetime as dt
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from kb.reconcile.schema import PositionSource

__all__ = [
    "Citation",
    "ConfirmingKind",
    "ReconciliationType",
    "Reconciliation",
    "ConfirmedDelta",
    "NetNewDelta",
    "ContestedDelta",
    "MaturityTransitionDelta",
    "Deltas",
]


class Citation(BaseModel):
    """A single quotable claim: the verbatim quote plus who said it and when.

    The atom the digest cites. Carries everything needed to attribute a claim without a
    join — its quote, the source video and date, the normalized statement, and the link
    back to the underlying unit.
    """

    model_config = ConfigDict(extra="forbid")

    unit_id: str = Field(min_length=1, description="Underlying unit id — provenance link.")
    video_id: str = Field(min_length=1, description="Source video id.")
    date: dt.date = Field(description="Upload date of the source video.")
    quote: str = Field(min_length=1, description="Verbatim quote, so the claim is citable exactly.")
    statement: str = Field(min_length=1, description="Normalized statement of what was said.")

    @classmethod
    def from_source(cls, source: PositionSource) -> "Citation":
        """Build a citation from a position source (denormalized quote + date + link)."""
        return cls(
            unit_id=source.unit_id,
            video_id=source.video_id,
            date=source.date,
            quote=source.quote,
            statement=source.statement,
        )


class ConfirmingKind(str, Enum):
    """How a confirming unit relates to the position it confirms.

    * ``redundant``     — restates a point the position already holds; low value, kept for
      provenance but flagged so the digest can collapse it (spec user story 13).
    * ``new_evidence``  — a fresh, independent voice for a known position; strengthens
      confidence and can ratchet the maturity flag upward.
    """

    redundant = "redundant"
    new_evidence = "new-evidence"


class ReconciliationType(str, Enum):
    """*Why* two credible sources disagree (spec user story 16).

    Classifying the disagreement is what turns "they contradict" into something a reader
    can act on. Whether the disagreement was actually resolved is a separate flag on
    :class:`Reconciliation` — ``unreconciled — genuinely open`` (``reconciled=False``) is
    a first-class, common outcome, not a failure.

    * ``empirical``     — a question of fact/measurement (who is right is checkable).
    * ``definitional``  — they mean different things by the same term (talking past).
    * ``contextual``    — both are right in their own setting (it depends on the case).
    """

    empirical = "empirical"
    definitional = "definitional"
    contextual = "contextual"


class Reconciliation(BaseModel):
    """A typed attempt to reconcile a contested position — including *not* reconciling it.

    Per the anti-manufactured-agreement guardrail, the honest and common answer is
    ``reconciled=False`` ("unreconciled — genuinely open"): the disagreement is real and
    the system does not smooth it into a tidy conclusion. ``type`` still classifies *why*
    the two sides disagree even when they are left unreconciled.
    """

    model_config = ConfigDict(extra="forbid")

    type: ReconciliationType = Field(description="The nature of the disagreement.")
    reconciled: bool = Field(
        description="True only if the disagreement genuinely resolves; False = open (the common case).",
    )
    explanation: str = Field(
        min_length=1,
        description="Why the two sides disagree; if reconciled, how — in plain words.",
    )

    @property
    def is_open(self) -> bool:
        """``True`` for the first-class 'unreconciled — genuinely open' outcome."""
        return not self.reconciled


class ConfirmedDelta(BaseModel):
    """An incoming unit that confirmed an existing position this run."""

    model_config = ConfigDict(extra="forbid")

    position_id: str = Field(min_length=1)
    position_statement: str = Field(min_length=1, description="The confirmed position's statement.")
    kind: ConfirmingKind = Field(description="redundant vs new-evidence-for-known.")
    citation: Citation = Field(description="The confirming unit, quoted + dated.")


class NetNewDelta(BaseModel):
    """A brand-new open position opened from a novel unit this run."""

    model_config = ConfigDict(extra="forbid")

    position_id: str = Field(min_length=1)
    statement: str = Field(min_length=1, description="The new position's canonical statement.")
    citation: Citation = Field(description="The founding unit, quoted + dated.")


class ContestedDelta(BaseModel):
    """A position a dissent contested this run — both stances quoted, disagreement typed.

    Holds *both* competing claims as citations (the structural guardrail: you cannot
    record a contest without quoting both sides with source + date) plus the typed
    :class:`Reconciliation` attempt. ``became_contested`` distinguishes a position that
    *flipped* to contested this run from one that was already contested and took a further
    dissent.
    """

    model_config = ConfigDict(extra="forbid")

    position_id: str = Field(min_length=1)
    position_statement: str = Field(min_length=1)
    supporting: Citation = Field(description="The existing side, quoted with source + date.")
    opposing: Citation = Field(description="The incoming dissent, quoted with source + date.")
    reconciliation: Reconciliation = Field(description="The typed reconciliation attempt.")
    became_contested: bool = Field(
        description="True if this run flipped the position to contested (vs already contested).",
    )


class MaturityTransitionDelta(BaseModel):
    """One maturity flag that moved this run (spec user story 20: *when* it converged)."""

    model_config = ConfigDict(extra="forbid")

    position_id: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    from_maturity: str = Field(min_length=1, description="Flag before the transition.")
    to_maturity: str = Field(min_length=1, description="Flag after the transition.")
    reason: str = Field(min_length=1, description="Why the flag moved, in plain words.")
    trigger_unit_id: str | None = Field(
        default=None, description="The incoming unit that caused the transition, if any."
    )


class Deltas(BaseModel):
    """The complete diff of one reconciliation run — what the digest (#10) renders.

    Starts empty and is filled as the engine processes each incoming unit. All four
    buckets are lists so a run that changed nothing yields an all-empty (but valid)
    :class:`Deltas`, and the digest is never handed a null.
    """

    model_config = ConfigDict(extra="forbid")

    newly_confirmed: list[ConfirmedDelta] = Field(default_factory=list)
    net_new: list[NetNewDelta] = Field(default_factory=list)
    newly_contested: list[ContestedDelta] = Field(default_factory=list)
    maturity_transitions: list[MaturityTransitionDelta] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """True when nothing changed — no confirms, net-new, contests, or transitions."""
        return not (
            self.newly_confirmed
            or self.net_new
            or self.newly_contested
            or self.maturity_transitions
        )

    def total_changes(self) -> int:
        """Count of individual changes across all four buckets."""
        return (
            len(self.newly_confirmed)
            + len(self.net_new)
            + len(self.newly_contested)
            + len(self.maturity_transitions)
        )
