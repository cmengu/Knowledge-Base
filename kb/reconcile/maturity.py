"""The maturity state machine — the policy that drives every position's flag (ticket #09).

Ticket #06 gave positions a :class:`~kb.reconcile.schema.Maturity` flag and a
``record_transition`` mechanism but no *policy* for when the flag should change. This
module is that policy: a small, config-driven state machine the reconciliation engine
(ticket #08) re-runs over **every** position on **every** batch — not once — so tuning a
threshold in ``config/maturity.yaml`` re-flags the whole KB on the next run.

Two entry points, mirroring the spec's Testing Decisions:

* :func:`compute_maturity` — a **pure** function ``(position, config, now) -> Maturity``.
  It reads a position's sources and returns the flag it *should* hold, mutating nothing.
  This is the deterministic seam the table-driven tests exercise.
* :func:`apply_maturity` — the imperative wrapper the engine calls: it computes the flag
  and, when it differs from the current one, appends a :class:`StatusEvent` to the
  position's status history (via the model's idempotent ``record_transition``). Running it
  every batch is safe — an unchanged flag is a no-op, so the history stays a clean record
  of *actual* transitions (exactly when a position converged or reopened).

The rules, from the spec's "Maturity state machine" decision (all thresholds tunable):

* ``open``        — fewer than ``emerging_min_sources`` independent sources.
* ``emerging``    — at least ``emerging_min_sources`` independent sources, one direction,
  but either still short of ``converging_min_sources`` or not yet spanning
  ``converging_min_span_days``.
* ``converging``  — at least ``converging_min_sources`` independent sources agreeing over
  at least ``converging_min_span_days``, with **no recent contest**.
* ``solved``      — a converging position that has also gone a full clean window: at least
  ``solved_min_sources`` independent sources and none of the last ``solved_clean_window``
  source videos opposing it.
* ``contested``   — **any** adversarial (opposing) source dated within
  ``recent_contest_days`` of the run knocks the position back here regardless of how far
  it had climbed; if such a reset leaves the statement with no support at all it falls to
  ``open`` instead — the "contested / open" of the spec.

Two interpretation calls the pure signature forces, both recorded in the PR:

* **"Independent sources" are counted as distinct videos**, not units — two units from one
  video count once (matching :attr:`Position.distinct_videos`). The sample KB proves this:
  a position with two units from a single video is hand-labelled ``open``.
* **"The last N videos"** is read *position-locally* — the N most recent distinct videos
  among *this position's* sources — because :func:`compute_maturity` is pure over one
  position and cannot see the global ingest stream.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from kb.config import CONFIG_DIR, load_yaml
from kb.reconcile.schema import Maturity, Position, PositionSource, StatusEvent

__all__ = [
    "MaturityConfig",
    "load_maturity_config",
    "compute_maturity",
    "apply_maturity",
    "apply_maturity_batch",
]


class MaturityConfig(BaseModel):
    """Thresholds that drive the maturity state machine (loaded from ``config/maturity.yaml``).

    Every knob is a plain integer so the whole policy is legible and git-diffable. The
    defaults encode the spec's recommended rules (``open`` <2 sources; ``emerging`` ≥2 one
    direction spanning <3 months; ``converging`` ≥3 over >3 months uncontested; ``solved``
    ≥3 with a clean recent window). "Sources" everywhere means *independent* sources —
    distinct videos.
    """

    model_config = ConfigDict(extra="forbid")

    emerging_min_sources: int = Field(
        default=2,
        ge=1,
        description="Independent sources (distinct videos) needed to leave `open`.",
    )
    converging_min_sources: int = Field(
        default=3,
        ge=1,
        description="Independent sources needed to reach `converging`.",
    )
    converging_min_span_days: int = Field(
        default=90,
        ge=0,
        description="Min days between the oldest and newest supporting source for "
        "`converging` (the spec's '>3 months'; the boundary day counts as converging).",
    )
    recent_contest_days: int = Field(
        default=90,
        ge=0,
        description="An opposing source dated within this many days of the run is a "
        "'recent contest': it forces `contested` and blocks `converging`. Older contests "
        "are 'buried' and let the position re-climb (its history records both turns).",
    )
    solved_min_sources: int = Field(
        default=3,
        ge=1,
        description="Independent sources needed to reach `solved` (the spec's '≥3').",
    )
    solved_clean_window: int = Field(
        default=5,
        ge=1,
        description="`solved` also requires a full clean streak: at least this many "
        "distinct source videos exist and none of the most recent this-many opposes the "
        "position. A count-based window, stricter than converging's calendar window.",
    )

    @model_validator(mode="after")
    def _check_monotonic(self) -> "MaturityConfig":
        """Reject an inverted ladder so a mistuned config fails loudly, not silently."""

        if not (self.emerging_min_sources <= self.converging_min_sources <= self.solved_min_sources):
            raise ValueError(
                "source thresholds must be monotonic: emerging_min_sources "
                f"({self.emerging_min_sources}) <= converging_min_sources "
                f"({self.converging_min_sources}) <= solved_min_sources "
                f"({self.solved_min_sources})"
            )
        return self


def load_maturity_config(path: str | Path | None = None) -> MaturityConfig:
    """Load :class:`MaturityConfig` from YAML (defaults when the file is absent)."""

    path = Path(path) if path is not None else CONFIG_DIR / "maturity.yaml"
    if not path.exists():
        return MaturityConfig()
    return MaturityConfig.model_validate(load_yaml(path) or {})


# -- the pure state machine -------------------------------------------------


def compute_maturity(
    position: Position,
    config: MaturityConfig,
    now: dt.datetime,
) -> Maturity:
    """Return the maturity flag ``position`` *should* hold as of ``now``. Pure — mutates nothing.

    ``now`` is the run timestamp; only its date is used, to decide which contests count as
    "recent". The rules are applied in priority order — a recent adversarial source
    overrides the whole agreement ladder — matching the spec's "any adversarial unit knocks
    the position back" over the "ratchets as evidence accumulates" default.
    """

    today = now.date()
    supporting = position.supporting_sources
    opposing = position.opposing_sources

    # 1) Adversarial reset (highest priority). A *recent* opposing source reopens the
    #    question no matter how settled it looked. Both stances present -> `contested`;
    #    a statement left with no support at all falls to `open` (the spec's "/open").
    if _has_recent_contest(opposing, config, today):
        return Maturity.contested if supporting else Maturity.open_question

    # 2) The agreement ladder. Below here there is no recent contest, so the supporting
    #    sources are effectively "one direction". Independent sources = distinct videos.
    n_sources = _distinct_video_count(supporting)
    if n_sources < config.emerging_min_sources:
        return Maturity.open_question
    if n_sources < config.converging_min_sources:
        return Maturity.emerging_trend

    # ≥ converging_min_sources agreeing sources: converging needs them spread over time.
    span = _supporting_span_days(supporting)
    if span is None or span < config.converging_min_span_days:
        return Maturity.emerging_trend

    # ≥ converging_min_sources, spanning the window, uncontested: at least `converging`.
    if _is_solved(position, config):
        return Maturity.solved
    return Maturity.converging


def apply_maturity(
    position: Position,
    config: MaturityConfig,
    now: dt.datetime,
    *,
    trigger_unit_id: str | None = None,
) -> StatusEvent | None:
    """Recompute ``position``'s flag and record a transition if it changed.

    The imperative half of the machine, meant to run over every position every batch.
    Delegates the actual flag to :func:`compute_maturity`, then calls the model's
    idempotent ``record_transition``: on a real change it appends one :class:`StatusEvent`
    (stamped ``now``, with a human ``reason`` and the optional ``trigger_unit_id``) and
    returns it; when the flag is unchanged it is a no-op and returns ``None``. Nothing is
    persisted — the caller saves the store when the batch is done.
    """

    flag = compute_maturity(position, config, now)
    return position.record_transition(
        flag,
        at=now,
        reason=_transition_reason(position, config, now, flag),
        trigger_unit_id=trigger_unit_id,
    )


def apply_maturity_batch(
    positions: Iterable[Position],
    config: MaturityConfig,
    now: dt.datetime,
) -> list[tuple[Position, StatusEvent]]:
    """Re-run the machine over every position — the "applied every batch, not one-time" step.

    This is the hook the reconciliation engine (ticket #08) calls once per run, after it
    has attached the batch's new units: it re-flags the *whole* KB against the current
    config so a threshold change (or merely time passing, which buries an old contest)
    ratchets or reopens positions on the next run. Returns only the positions that actually
    changed, paired with the :class:`StatusEvent` recorded — the "maturity transitions since
    last run" the digest (ticket #10) reports. Idempotent: a second call in the same run
    finds nothing to change and returns an empty list.
    """

    transitions: list[tuple[Position, StatusEvent]] = []
    for position in positions:
        event = apply_maturity(position, config, now)
        if event is not None:
            transitions.append((position, event))
    return transitions


# -- internals --------------------------------------------------------------


def _distinct_video_count(sources: list[PositionSource]) -> int:
    """Independent-source count: distinct videos among ``sources`` (units collapse per video)."""

    return len({s.video_id for s in sources})


def _supporting_span_days(supporting: list[PositionSource]) -> int | None:
    """Days between the oldest and newest *supporting* source (0 for one, None for none).

    Deliberately over supporting sources only: converging is about the agreeing sources
    spanning months, so a buried opposing source must not stretch (or shrink) the span.
    """

    if not supporting:
        return None
    dates = [s.date for s in supporting]
    return (max(dates) - min(dates)).days


def _has_recent_contest(
    opposing: list[PositionSource],
    config: MaturityConfig,
    today: dt.date,
) -> bool:
    """True when any opposing source is dated within ``recent_contest_days`` of ``today``.

    A source dated on or after ``today`` (same-run or clock skew) counts as recent.
    """

    return any((today - s.date).days <= config.recent_contest_days for s in opposing)


def _video_dates(sources: list[PositionSource]) -> dict[str, dt.date]:
    """Map each source video to its date (units of one video share the upload date)."""

    dates: dict[str, dt.date] = {}
    for source in sources:
        # Defensive against inconsistent per-unit dates: keep the latest seen.
        existing = dates.get(source.video_id)
        if existing is None or source.date > existing:
            dates[source.video_id] = source.date
    return dates


def _recent_videos(sources: list[PositionSource], window: int) -> set[str]:
    """The ``window`` most recent distinct source videos, newest first (ties break by id)."""

    ordered = sorted(_video_dates(sources).items(), key=lambda kv: (kv[1], kv[0]), reverse=True)
    return {video_id for video_id, _ in ordered[:window]}


def _is_solved(position: Position, config: MaturityConfig) -> bool:
    """Whether a converging position has also earned ``solved``.

    Beyond converging's conditions (already checked by the caller), ``solved`` needs a full
    clean window: at least ``solved_min_sources`` supporting videos, at least
    ``solved_clean_window`` distinct source videos in all, and none of those most-recent
    ``solved_clean_window`` videos opposing the position. Requiring the window to be *full*
    is what keeps a freshly-converged position (e.g. three agreeing sources) out of
    ``solved`` — matching the sample KB, where such a position is labelled ``converging``.
    """

    if _distinct_video_count(position.supporting_sources) < config.solved_min_sources:
        return False
    recent_videos = _recent_videos(position.sources, config.solved_clean_window)
    if len(recent_videos) < config.solved_clean_window:
        return False  # not enough accumulated history to declare it settled
    opposing_videos = {s.video_id for s in position.opposing_sources}
    return not (opposing_videos & recent_videos)


def _transition_reason(
    position: Position,
    config: MaturityConfig,
    now: dt.datetime,
    flag: Maturity,
) -> str:
    """A short, human explanation for the status-history audit trail.

    Kept descriptive (counts + span), never asserted verbatim in tests — the tests check
    *that* a transition was recorded, not its wording.
    """

    n = _distinct_video_count(position.supporting_sources)
    span = _supporting_span_days(position.supporting_sources)
    span_text = "no span" if span is None else f"{span}-day span"

    if flag is Maturity.contested:
        return f"adversarial source within {config.recent_contest_days} days resets to contested"
    if flag is Maturity.open_question:
        if _has_recent_contest(position.opposing_sources, config, now.date()):
            return "adversarial source with no remaining support resets to open"
        return f"{n} independent source(s), below the {config.emerging_min_sources}-source emerging threshold"
    if flag is Maturity.emerging_trend:
        return f"{n} independent source(s) over {span_text}, one direction"
    if flag is Maturity.converging:
        return f"{n} independent sources agree over {span_text} with no recent contest"
    if flag is Maturity.solved:
        return (
            f"{n} independent sources, clean over the last {config.solved_clean_window} "
            "videos with no recent contest"
        )
    return flag.value
