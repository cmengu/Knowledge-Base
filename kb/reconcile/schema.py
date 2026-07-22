"""The position data model — the living unit the KB accumulates (Layer 4, ticket #06).

A **position** is a single claim the knowledge base tracks over time. Every new unit the
pipeline extracts is compared against the positions in its topic (the reconciliation
engine, ticket #08); the outcome either strengthens a position, opens a new one, or
records a contradiction. A position therefore has to remember more than a sentence — it
holds, per the spec's "Position data model" decision:

* a **canonical statement** — the proposition, phrased affirmatively;
* a **maturity flag** — where the claim sits on ``open-question -> emerging-trend ->
  converging -> solved``, or ``contested`` when credible sources disagree;
* its **supporting sources + dates** — each backing unit, quoted, with its video and date;
* its **contested stances** — when contested, the *opposing* sources are kept too, each
  quoted with source + date, so disagreement is preserved rather than smoothed away;
* a **status history** — one entry per maturity transition, so we can see *when* it
  converged or reopened;
* **links to the underlying units** — every source carries the ``unit_id`` it came from.

Design notes that shape the types below:

* **Sources are denormalized.** A :class:`PositionSource` copies the unit's quote, date,
  and stance into the position rather than only pointing at a ``unit_id``. Positions are
  stored as flat JSON + Markdown per topic (ticket #01) precisely so they are
  human-readable and git-diffable; a position must be legible — both stances quoted with
  source and date — without joining back to the units database. The ``unit_id`` link is
  still kept for provenance.
* **Maturity and the status history stay consistent.** ``maturity`` is only ever changed
  through :meth:`Position.record_transition`, which appends a :class:`StatusEvent` at the
  same moment. The head of ``status_history`` therefore always equals ``maturity``; a
  model validator enforces this so a hand-edited or corrupted JSON file is rejected on
  load rather than silently drifting.
* **Reuse, don't redefine.** The unit-layer :class:`~kb.extract.Stance` is reused as-is;
  :meth:`PositionSource.from_unit` is the bridge that projects an extracted
  :class:`~kb.extract.Unit` (plus its video's id and date, which live on the enclosing
  :class:`~kb.extract.ExtractedVideo`) into a position source.

The *thresholds* that decide which maturity a position should hold (source counts, time
spans, the adversarial-reset rule) are the maturity state machine, ticket #09; this
module provides the state and the transition-recording mechanism it drives, not the
policy.
"""

from __future__ import annotations

import datetime as dt
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from kb.extract import Stance, Unit

__all__ = [
    "Maturity",
    "Alignment",
    "PositionSource",
    "StatusEvent",
    "Position",
]


class Maturity(str, Enum):
    """How settled a position is.

    The four-step ladder ratchets as independent, agreeing sources accumulate over time
    (the thresholds themselves live in the ticket #09 config):

    * ``open_question``  — too little evidence to say anything yet (a fresh position).
    * ``emerging_trend`` — a couple of sources point the same way, but recently / briefly.
    * ``converging``     — several sources agree over a meaningful span, uncontested.
    * ``solved``         — settled consensus; no recent contradiction.

    ``contested`` is off the ladder: it is what a position becomes the moment credible
    sources disagree. Per the spec, *any* adversarial unit knocks a position back to
    ``contested`` regardless of how far up the ladder it had climbed — a single credible
    dissent reopens a question rather than being buried.
    """

    open_question = "open-question"
    emerging_trend = "emerging-trend"
    converging = "converging"
    solved = "solved"
    contested = "contested"


class Alignment(str, Enum):
    """Which side of a *position's* canonical statement a source lands on.

    This is deliberately distinct from the unit-level :class:`~kb.extract.Stance`. Stance
    is the speaker's polarity toward *their own* subject; alignment is that unit's
    polarity toward *this position's* statement. A unit that ``denies`` "small models are
    good enough" is a ``supporting`` source for a position phrased "small models are not
    good enough". Keeping the two separate is what lets reconciliation put a claim and its
    negation on opposite sides of the same position instead of merging them.
    """

    supporting = "supporting"
    opposing = "opposing"


class PositionSource(BaseModel):
    """One unit that bears on a position, with everything needed to cite it.

    Carries the link back to the underlying unit (``unit_id`` / ``video_id``) *and* a
    denormalized copy of the citation payload (``quote``, ``date``, ``stance``) so the
    position renders as legible, git-diffable JSON/Markdown on its own.
    """

    model_config = ConfigDict(extra="forbid")

    unit_id: str = Field(
        min_length=1,
        description="Link to the underlying unit (`{video_id}#{index}`); provenance.",
    )
    video_id: str = Field(
        min_length=1,
        description="Source video id — ties the source back to its video for the digest.",
    )
    date: dt.date = Field(
        description="Upload date of the source video. The time-series anchor for maturity.",
    )
    alignment: Alignment = Field(
        description="Whether this source supports or opposes the position's statement.",
    )
    stance: Stance = Field(
        description="The unit's own stance toward its subject (reused from the unit schema).",
    )
    quote: str = Field(
        min_length=1,
        description="Verbatim quote from the source, so the position can be cited exactly.",
    )
    statement: str = Field(
        min_length=1,
        description="The unit's normalized statement — what this source actually said.",
    )
    evidence_offered: list[str] = Field(
        default_factory=list,
        description="Backing the source offered for its point (carried over from the unit).",
    )

    @classmethod
    def from_unit(
        cls,
        unit: Unit,
        *,
        video_id: str,
        date: dt.date | str,
        alignment: Alignment | str,
    ) -> "PositionSource":
        """Project an extracted :class:`~kb.extract.Unit` into a position source.

        ``video_id`` and ``date`` are supplied by the caller because they live on the
        unit's enclosing :class:`~kb.extract.ExtractedVideo`, not on the unit itself.
        ``unit.unit_id`` must already be assigned (the extractor does this); a unit with
        no id cannot be linked to a position and is rejected.
        """

        if not unit.unit_id:
            raise ValueError("unit has no unit_id; assign one (via the extractor) before linking")
        return cls(
            unit_id=unit.unit_id,
            video_id=video_id,
            date=date,  # validated/coerced to a date by the field
            alignment=alignment,
            stance=unit.stance,
            quote=unit.raw_quote,
            statement=unit.text,
        )


class StatusEvent(BaseModel):
    """One entry in a position's status history: a maturity transition and when it happened.

    The first event of a position's life is its *creation* (``from_maturity is None``).
    Every later event records a genuine change of :class:`Maturity`, tagged with the run
    timestamp (``at``), a human ``reason``, and — when the change was triggered by a
    specific incoming unit — that unit's id, so the history reads as an audit trail.
    """

    model_config = ConfigDict(extra="forbid")

    from_maturity: Maturity | None = Field(
        default=None,
        description="Maturity before the transition; None for the creation event.",
    )
    to_maturity: Maturity = Field(
        description="Maturity after the transition.",
    )
    at: dt.datetime = Field(
        description="Run timestamp when this transition was recorded (see user story 29).",
    )
    reason: str = Field(
        min_length=1,
        description="Why the transition happened, in plain words.",
    )
    trigger_unit_id: str | None = Field(
        default=None,
        description="The incoming unit that caused the transition, if any.",
    )


class Position(BaseModel):
    """A single tracked claim: the living unit the KB accumulates and compares against.

    Create new positions with :meth:`create` (it seeds the status history); load existing
    ones by validating stored JSON. Mutate through the methods — :meth:`add_source` and
    :meth:`record_transition` — rather than by assigning fields, so the invariants below
    hold:

    * ``status_history`` is non-empty (every position has at least its creation event);
    * ``status_history[-1].to_maturity == maturity`` (the flag and the history agree).
    """

    model_config = ConfigDict(extra="forbid")

    position_id: str = Field(
        min_length=1,
        description="Stable id, unique within the topic (the store assigns `{topic}-NNNN`).",
    )
    topic: str = Field(
        min_length=1,
        description="The topic this position belongs to (one of the fixed set in config).",
    )
    statement: str = Field(
        min_length=1,
        description="The canonical statement — the proposition, phrased affirmatively.",
    )
    maturity: Maturity = Field(
        description="Current maturity flag; equals the head of status_history.",
    )
    sources: list[PositionSource] = Field(
        default_factory=list,
        description="Every unit bearing on this position — supporting and, if contested, opposing.",
    )
    status_history: list[StatusEvent] = Field(
        default_factory=list,
        description="Append-only maturity transitions, oldest first; head matches `maturity`.",
    )
    created_at: dt.datetime = Field(
        description="When the position was first opened (run timestamp).",
    )
    updated_at: dt.datetime = Field(
        description="When the position was last mutated (run timestamp).",
    )

    # -- invariants ---------------------------------------------------------

    @model_validator(mode="after")
    def _check_history_consistency(self) -> "Position":
        """Reject a position whose history is empty or disagrees with its maturity flag."""

        if not self.status_history:
            raise ValueError("status_history must have at least the creation event")
        head = self.status_history[-1].to_maturity
        if head is not self.maturity:
            raise ValueError(
                f"maturity ({self.maturity.value}) must equal the last status_history entry "
                f"({head.value}); change maturity only via record_transition()"
            )
        return self

    # -- construction -------------------------------------------------------

    @classmethod
    def create(
        cls,
        *,
        position_id: str,
        topic: str,
        statement: str,
        at: dt.datetime,
        maturity: Maturity = Maturity.open_question,
        first_source: PositionSource | None = None,
        reason: str = "opened as a new position",
    ) -> "Position":
        """Open a fresh position, seeding its status history with the creation event.

        A brand-new position defaults to ``open_question`` (a novel unit becomes a fresh
        open position, per the spec). ``first_source`` is the unit that prompted it, if
        any. The creation :class:`StatusEvent` has ``from_maturity is None``.
        """

        creation = StatusEvent(
            from_maturity=None,
            to_maturity=maturity,
            at=at,
            reason=reason,
            trigger_unit_id=first_source.unit_id if first_source is not None else None,
        )
        return cls(
            position_id=position_id,
            topic=topic,
            statement=statement,
            maturity=maturity,
            sources=[first_source] if first_source is not None else [],
            status_history=[creation],
            created_at=at,
            updated_at=at,
        )

    # -- mutation -----------------------------------------------------------

    def add_source(self, source: PositionSource, *, at: dt.datetime | None = None) -> None:
        """Attach a unit to this position (supporting or opposing).

        This is a pure data mutation: it records the evidence and, when ``at`` is given,
        bumps ``updated_at``. It does **not** change the maturity flag — that is the
        maturity state machine's job (ticket #09), applied via :meth:`record_transition`.
        Adding an ``opposing`` source is what later makes :attr:`is_contested` true.
        """

        self.sources = [*self.sources, source]
        if at is not None:
            self.updated_at = at

    def record_transition(
        self,
        to: Maturity,
        *,
        at: dt.datetime,
        reason: str,
        trigger_unit_id: str | None = None,
    ) -> StatusEvent | None:
        """Move the position to maturity ``to``, appending a status-history entry.

        Append-only and idempotent: if ``to`` equals the current maturity this is a no-op
        (returns ``None``, leaves the history untouched) so the history stays a clean
        record of *actual* transitions — exactly the times the position converged or
        reopened. On a real change it appends one :class:`StatusEvent`, updates
        ``maturity`` and ``updated_at``, and returns the appended event.
        """

        if to is self.maturity:
            return None
        event = StatusEvent(
            from_maturity=self.maturity,
            to_maturity=to,
            at=at,
            reason=reason,
            trigger_unit_id=trigger_unit_id,
        )
        # Keep the flag and the history head in lock-step: append the event, then move
        # `maturity` to match its new head. The `_check_history_consistency` invariant
        # (checked on construction and load) holds again once both lines have run.
        self.status_history = [*self.status_history, event]
        self.maturity = to
        self.updated_at = at
        return event

    # -- derived views (substrate for the maturity machine #09 and the digest #10) ---

    @property
    def supporting_sources(self) -> list[PositionSource]:
        """Sources that back the canonical statement."""
        return [s for s in self.sources if s.alignment is Alignment.supporting]

    @property
    def opposing_sources(self) -> list[PositionSource]:
        """Sources that contradict the canonical statement (the contested stance)."""
        return [s for s in self.sources if s.alignment is Alignment.opposing]

    @property
    def is_contested(self) -> bool:
        """True when the position holds *both* a supporting and an opposing source.

        This is the structural definition of "contested": genuine disagreement, both
        sides present. It is what the digest keys on to quote both stances, and what the
        maturity machine keys on to force ``contested``.
        """
        return bool(self.supporting_sources) and bool(self.opposing_sources)

    @property
    def source_dates(self) -> list[dt.date]:
        """Every source's date, ascending — the time series maturity is computed over."""
        return sorted(s.date for s in self.sources)

    @property
    def earliest_date(self) -> dt.date | None:
        """Date of the oldest source, or None when there are no sources yet."""
        dates = self.source_dates
        return dates[0] if dates else None

    @property
    def latest_date(self) -> dt.date | None:
        """Date of the newest source, or None when there are no sources yet."""
        dates = self.source_dates
        return dates[-1] if dates else None

    @property
    def span_days(self) -> int | None:
        """Days between the oldest and newest source (0 for one source, None for none)."""
        if not self.sources:
            return None
        return (self.latest_date - self.earliest_date).days

    @property
    def distinct_videos(self) -> set[str]:
        """The set of distinct source videos — the "independent sources" maturity counts."""
        return {s.video_id for s in self.sources}

    @property
    def unit_ids(self) -> list[str]:
        """The underlying unit ids this position links to, in attachment order."""
        return [s.unit_id for s in self.sources]
