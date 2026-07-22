"""Maturity state-machine tests (ticket #09).

The spec's Testing Decisions call for table-driven tests over the threshold config:
source-count boundaries, time spans, the adversarial-resets rule, and the resulting
status-history entry. :func:`~kb.reconcile.compute_maturity` is a pure function, so these
are plain deterministic value assertions — no LLM, and (bar one read of the committed
sample KB) no disk.

The date arithmetic is anchored on a fixed run clock ``NOW`` so "recent" vs "buried"
contests are exact and reproducible.
"""

from __future__ import annotations

import datetime as dt

import pytest
from pydantic import ValidationError

from kb.config import PROJECT_ROOT
from kb.reconcile import (
    KBStore,
    Maturity,
    MaturityConfig,
    Position,
    PositionSource,
    apply_maturity,
    apply_maturity_batch,
    compute_maturity,
    load_maturity_config,
)

# A fixed run clock. All source dates below are chosen relative to it so the
# recent-vs-buried contest boundary is deterministic.
NOW = dt.datetime(2026, 1, 1, 12, 0)
CREATED = dt.datetime(2025, 5, 1, 9, 0)
CFG = MaturityConfig()  # the spec defaults: 2 / 3 / 90 / 90 / 3 / 5

# A recent same-day date (no opposing sources accompany it in the count tests, so its
# recency is irrelevant there; it just pins span to zero to isolate the source count).
RECENT_DAY = dt.date(2025, 12, 1)


def src(
    video_id: str,
    index: int = 0,
    *,
    date: dt.date | str,
    alignment: str = "supporting",
    stance: str = "affirms",
) -> PositionSource:
    """A minimal :class:`PositionSource`; ``video_id`` is the independent-source identity."""

    return PositionSource(
        unit_id=f"{video_id}#{index}",
        video_id=video_id,
        date=date,
        alignment=alignment,
        stance=stance,
        quote=f"quote from {video_id}",
        statement=f"statement from {video_id}",
    )


def make_position(
    sources: list[PositionSource],
    *,
    maturity: Maturity = Maturity.open_question,
    at: dt.datetime = CREATED,
) -> Position:
    """Build a position carrying ``sources`` (first seeds it, the rest are added)."""

    first = sources[0] if sources else None
    pos = Position.create(
        position_id="evals-0001",
        topic="evals",
        statement="You should build your own task-specific evals.",
        at=at,
        maturity=maturity,
        first_source=first,
    )
    for source in sources[1:]:
        pos.add_source(source)
    return pos


def supporting_over(span_days: int, *, count: int = 3) -> list[PositionSource]:
    """``count`` distinct supporting videos whose oldest→newest span is ``span_days``.

    The newest is pinned five days before ``NOW`` so nothing is future-dated.
    """

    newest = NOW.date() - dt.timedelta(days=5)
    oldest = newest - dt.timedelta(days=span_days)
    dates = [oldest, newest] if count == 2 else (
        [oldest]
        + [oldest + dt.timedelta(days=span_days * i // (count - 1)) for i in range(1, count - 1)]
        + [newest]
    )
    return [src(f"v{i}", date=d) for i, d in enumerate(dates)]


# --- source-count boundaries -----------------------------------------------


@pytest.mark.parametrize(
    "n_videos, expected",
    [
        (0, Maturity.open_question),   # no evidence
        (1, Maturity.open_question),   # <2 independent sources
        (2, Maturity.emerging_trend),  # crosses the emerging threshold
        (3, Maturity.emerging_trend),  # enough sources, but span 0 (< converging span)
        (5, Maturity.emerging_trend),  # still emerging until the time gate opens
    ],
)
def test_source_count_boundary_open_to_emerging(n_videos, expected):
    # All same-day (span 0) so the time gate never fires — this isolates the count.
    sources = [src(f"v{i}", date=RECENT_DAY) for i in range(n_videos)]
    assert compute_maturity(make_position(sources), CFG, NOW) is expected


def test_two_units_one_video_count_as_one_independent_source():
    # Mirrors sample position evals-0003: two units, one video -> one source -> open.
    sources = [src("v1", 0, date=RECENT_DAY), src("v1", 1, date=RECENT_DAY)]
    pos = make_position(sources)
    assert pos.distinct_videos == {"v1"}
    assert compute_maturity(pos, CFG, NOW) is Maturity.open_question


# --- time-span boundary (emerging -> converging) ---------------------------


@pytest.mark.parametrize(
    "span_days, expected",
    [
        (0, Maturity.emerging_trend),   # 3 sources, same day
        (89, Maturity.emerging_trend),  # just under the ~3-month gate
        (90, Maturity.converging),      # boundary day counts as converging
        (200, Maturity.converging),     # comfortably over
    ],
)
def test_span_boundary_emerging_to_converging(span_days, expected):
    # Three distinct supporting videos, uncontested; only the span varies.
    pos = make_position(supporting_over(span_days, count=3))
    assert compute_maturity(pos, CFG, NOW) is expected


# --- solved: the clean-window (count) gate ---------------------------------


@pytest.mark.parametrize("count", [3, 4])
def test_converging_not_solved_until_window_is_full(count):
    # Enough sources + span for converging, but fewer than solved_clean_window (5)
    # distinct videos, so `solved` is not yet earned. Matches sample evals-0001.
    pos = make_position(supporting_over(200, count=count))
    assert compute_maturity(pos, CFG, NOW) is Maturity.converging


@pytest.mark.parametrize("count", [5, 6])
def test_solved_once_a_full_clean_window_of_sources_agrees(count):
    pos = make_position(supporting_over(200, count=count))
    assert compute_maturity(pos, CFG, NOW) is Maturity.solved


def test_buried_contest_inside_the_window_blocks_solved():
    # Five distinct videos, all old (no recent contest), one of them opposing and among
    # the most-recent five -> the clean window is dirtied -> converging, not solved.
    sources = [
        src("v1", date=dt.date(2025, 1, 1)),
        src("v2", date=dt.date(2025, 2, 1)),
        src("v3", date=dt.date(2025, 3, 1)),
        src("v4", date=dt.date(2025, 4, 1)),
        src("vX", date=dt.date(2025, 6, 1), alignment="opposing", stance="denies"),
    ]
    pos = make_position(sources)
    # the contest is 214 days before NOW -> buried, so no adversarial reset...
    assert compute_maturity(pos, CFG, NOW) is Maturity.converging


def test_buried_contest_outside_the_window_allows_solved():
    # Five supporting videos form a clean recent window; a much older opposing source sits
    # outside that window -> the count-based clean streak holds -> solved. This is what
    # distinguishes solved's count window from converging's calendar window.
    supporting = [
        src("s1", date=dt.date(2025, 6, 1)),
        src("s2", date=dt.date(2025, 7, 1)),
        src("s3", date=dt.date(2025, 8, 1)),
        src("s4", date=dt.date(2025, 9, 1)),
        src("s5", date=dt.date(2025, 10, 1)),
    ]
    ancient_contest = src("vX", date=dt.date(2025, 1, 1), alignment="opposing", stance="denies")
    pos = make_position(supporting + [ancient_contest])
    assert compute_maturity(pos, CFG, NOW) is Maturity.solved


# --- the adversarial reset rule --------------------------------------------


@pytest.mark.parametrize(
    "contest_age_days, expected",
    [
        (0, Maturity.contested),     # dated on the run day
        (45, Maturity.contested),    # comfortably recent
        (90, Maturity.contested),    # boundary: within the window
        (91, Maturity.converging),   # buried: the agreement ladder resumes
    ],
)
def test_adversarial_reset_is_recency_gated(contest_age_days, expected):
    # Three supporting videos over 122 days would be converging on their own; a *recent*
    # opposing source knocks that back to contested, a *buried* one no longer does.
    supporting = [
        src("v1", date=dt.date(2025, 6, 1)),
        src("v2", date=dt.date(2025, 8, 1)),
        src("v3", date=dt.date(2025, 10, 1)),
    ]
    contest_date = NOW.date() - dt.timedelta(days=contest_age_days)
    opposing = src("vX", date=contest_date, alignment="opposing", stance="denies")
    pos = make_position(supporting + [opposing])
    assert compute_maturity(pos, CFG, NOW) is expected


def test_any_adversarial_unit_resets_even_a_solved_position():
    # A settled (solved) position is reopened by a single credible dissent — the spec's
    # "any adversarial unit knocks the position back", overriding the ratchet.
    pos = make_position(supporting_over(200, count=5))
    assert compute_maturity(pos, CFG, NOW) is Maturity.solved  # settled first...
    pos.add_source(src("vX", date=NOW.date(), alignment="opposing", stance="denies"))
    assert compute_maturity(pos, CFG, NOW) is Maturity.contested  # ...then reset


def test_adversarial_reset_falls_to_open_when_no_support_remains():
    # "contested / open": a recent adversarial source with no supporting side at all is not
    # a two-sided contest — the statement has no backing, so it reopens as a question.
    pos = make_position([src("vX", date=NOW.date(), alignment="opposing", stance="denies")])
    assert pos.is_contested is False
    assert compute_maturity(pos, CFG, NOW) is Maturity.open_question


# --- config drives every boundary ------------------------------------------


def test_source_threshold_is_config_driven():
    two = [src("v1", date=RECENT_DAY), src("v2", date=RECENT_DAY)]
    pos = make_position(two)
    assert compute_maturity(pos, MaturityConfig(), NOW) is Maturity.emerging_trend
    stricter = MaturityConfig(emerging_min_sources=3, converging_min_sources=3, solved_min_sources=3)
    assert compute_maturity(pos, stricter, NOW) is Maturity.open_question


def test_span_threshold_is_config_driven():
    pos = make_position(supporting_over(30, count=3))  # 30-day span
    assert compute_maturity(pos, MaturityConfig(), NOW) is Maturity.emerging_trend  # 30 < 90
    lenient = MaturityConfig(converging_min_span_days=30)
    assert compute_maturity(pos, lenient, NOW) is Maturity.converging  # 30 >= 30


def test_recent_contest_window_is_config_driven():
    supporting = [
        src("v1", date=dt.date(2025, 6, 1)),
        src("v2", date=dt.date(2025, 8, 1)),
        src("v3", date=dt.date(2025, 10, 1)),
    ]
    contest = src("vX", date=dt.date(2025, 10, 15), alignment="opposing", stance="denies")  # 78d before NOW
    pos = make_position(supporting + [contest])
    assert compute_maturity(pos, MaturityConfig(), NOW) is Maturity.contested  # 78 <= 90 -> recent
    narrowed = MaturityConfig(recent_contest_days=30)
    assert compute_maturity(pos, narrowed, NOW) is Maturity.converging  # 78 > 30 -> buried


def test_solved_window_is_config_driven():
    pos = make_position(supporting_over(200, count=5))
    assert compute_maturity(pos, MaturityConfig(), NOW) is Maturity.solved  # window 5, 5 videos
    wider = MaturityConfig(solved_clean_window=6)
    assert compute_maturity(pos, wider, NOW) is Maturity.converging  # only 5 videos < 6


# --- MaturityConfig validation & loading -----------------------------------


def test_config_defaults_match_the_spec():
    cfg = MaturityConfig()
    assert (cfg.emerging_min_sources, cfg.converging_min_sources, cfg.solved_min_sources) == (2, 3, 3)
    assert cfg.converging_min_span_days == 90
    assert cfg.recent_contest_days == 90
    assert cfg.solved_clean_window == 5


@pytest.mark.parametrize(
    "kwargs",
    [
        {"emerging_min_sources": 3, "converging_min_sources": 2},  # emerging > converging
        {"converging_min_sources": 5, "solved_min_sources": 4},    # converging > solved
    ],
)
def test_config_rejects_inverted_source_ladder(kwargs):
    with pytest.raises(ValidationError):
        MaturityConfig(**kwargs)


def test_config_rejects_unknown_key():
    with pytest.raises(ValidationError):
        MaturityConfig(mystery_knob=1)


def test_load_maturity_config_falls_back_to_defaults_when_absent(tmp_path):
    assert load_maturity_config(tmp_path / "missing.yaml") == MaturityConfig()


def test_committed_config_file_parses_to_the_documented_defaults():
    # Guards config/maturity.yaml against a typo drifting from the documented defaults.
    assert load_maturity_config() == MaturityConfig()


# --- apply_maturity: the status-history entry ------------------------------


def test_apply_records_a_transition_with_stamp_reason_and_trigger():
    pos = make_position([src("v1", date=RECENT_DAY), src("v2", date=RECENT_DAY)])  # -> emerging
    assert pos.maturity is Maturity.open_question
    event = apply_maturity(pos, CFG, NOW, trigger_unit_id="v2#0")
    assert event is not None
    assert (event.from_maturity, event.to_maturity) == (Maturity.open_question, Maturity.emerging_trend)
    assert pos.maturity is Maturity.emerging_trend
    assert pos.status_history[-1] is event
    assert event.at == NOW
    assert event.trigger_unit_id == "v2#0"
    assert event.reason  # a non-empty audit note is always written


def test_apply_is_a_noop_when_the_flag_is_unchanged():
    pos = make_position(
        [src("v1", date=RECENT_DAY), src("v2", date=RECENT_DAY)],
        maturity=Maturity.emerging_trend,
    )
    before = len(pos.status_history)
    assert apply_maturity(pos, CFG, NOW) is None  # recompute == current -> no entry
    assert len(pos.status_history) == before
    assert pos.maturity is Maturity.emerging_trend


def test_apply_records_the_full_lifecycle_including_reopen_and_reconverge():
    # The audit trail the spec asks for: see *when* a position converged and reopened.
    pos = make_position([src("v1", date=dt.date(2025, 6, 1))])  # 1 source -> open
    assert apply_maturity(pos, CFG, dt.datetime(2025, 6, 1, 9, 0)) is None  # stays open

    pos.add_source(src("v2", date=dt.date(2025, 7, 1)))
    e2 = apply_maturity(pos, CFG, dt.datetime(2025, 7, 1, 9, 0))
    assert e2.to_maturity is Maturity.emerging_trend  # 2 sources / 30 days

    pos.add_source(src("v3", date=dt.date(2025, 10, 1)))
    e3 = apply_maturity(pos, CFG, dt.datetime(2025, 10, 1, 9, 0))
    assert e3.to_maturity is Maturity.converging  # 3 sources / 122 days

    pos.add_source(src("vX", date=dt.date(2025, 10, 15), alignment="opposing", stance="denies"))
    e4 = apply_maturity(pos, CFG, dt.datetime(2025, 10, 20, 9, 0), trigger_unit_id="vX#0")
    assert e4.to_maturity is Maturity.contested  # a recent dissent reopens it

    e5 = apply_maturity(pos, CFG, dt.datetime(2026, 2, 1, 9, 0))  # contest now buried
    assert e5.to_maturity is Maturity.converging  # re-converges on a later run

    assert [e.to_maturity for e in pos.status_history] == [
        Maturity.open_question,
        Maturity.emerging_trend,
        Maturity.converging,
        Maturity.contested,
        Maturity.converging,
    ]
    # from/to chain is contiguous — the history reads as an audit trail
    tos = [e.to_maturity for e in pos.status_history]
    assert [e.from_maturity for e in pos.status_history][1:] == tos[:-1]


# --- apply_maturity_batch: the every-batch KB refresh ----------------------


def test_batch_flags_every_position_and_returns_only_the_changed_ones():
    open_pos = make_position([src("v1", date=RECENT_DAY)])  # 1 source -> stays open
    emerging_pos = make_position(  # 2 sources -> should transition to emerging
        [src("w1", date=RECENT_DAY), src("w2", date=RECENT_DAY)]
    )
    emerging_pos.position_id = "evals-0002"

    transitions = apply_maturity_batch([open_pos, emerging_pos], CFG, NOW)

    # Only the position whose flag actually changed is reported.
    assert [p.position_id for p, _ in transitions] == ["evals-0002"]
    changed, event = transitions[0]
    assert changed is emerging_pos
    assert event.to_maturity is Maturity.emerging_trend
    assert emerging_pos.maturity is Maturity.emerging_trend
    assert open_pos.maturity is Maturity.open_question  # unchanged, no history churn


def test_batch_is_idempotent_within_a_run():
    positions = [make_position(supporting_over(200, count=5))]  # -> solved on first pass
    first = apply_maturity_batch(positions, CFG, NOW)
    assert [e.to_maturity for _, e in first] == [Maturity.solved]
    # Re-running the same batch changes nothing and appends no history.
    assert apply_maturity_batch(positions, CFG, NOW) == []
    assert len(positions[0].status_history) == 2  # creation + the one solved transition


# --- cross-check against the committed sample KB (#06 artifact) -------------


def test_machine_reproduces_the_sample_kb_labels():
    # The hand-authored sample positions (ticket #06) double as an oracle: run the machine
    # over them and it must reproduce every hand-assigned flag. `now` is the latest run
    # recorded in that KB. Deterministic disk read, no network/LLM.
    store = KBStore.load("evals", root=PROJECT_ROOT / "kb-data")
    now = dt.datetime(2025, 9, 20, 9, 0)
    cfg = load_maturity_config()
    labelled = {p.position_id: p.maturity for p in store.positions()}
    assert labelled  # guard: the sample KB is present and non-empty
    for position in store.positions():
        assert compute_maturity(position, cfg, now) is position.maturity, position.position_id
