"""Table-driven tests for ``compute_maturity`` — the pure maturity function (spec seam).

Per the spec's Testing Decisions, ``computeMaturity(position, config, now) -> flag`` is a
pure function tested over the threshold config: source-count boundaries, time spans, and
the adversarial-resets-to-open rule. No LLM, no disk — plain value assertions.
"""

from __future__ import annotations

import datetime as dt

import pytest

from kb.reconcile import (
    Maturity,
    MaturityConfig,
    Position,
    PositionSource,
    compute_maturity,
)

NOW = dt.datetime(2025, 12, 1, 9, 0)
BASE = dt.date(2025, 1, 1)


def _source(i: int, *, days: int, alignment: str = "supporting", stance: str = "affirms") -> PositionSource:
    """A source from a distinct video ``vid{i}``, dated ``BASE + days``."""
    return PositionSource(
        unit_id=f"vid{i}#0",
        video_id=f"vid{i}",
        date=(BASE + dt.timedelta(days=days)).isoformat(),
        alignment=alignment,
        stance=stance,
        quote=f"quote {i}",
        statement=f"statement {i}",
    )


def _position(sources: list[PositionSource], *, maturity: Maturity = Maturity.open_question) -> Position:
    """A position seeded with ``sources`` (history left at the creation event)."""
    pos = Position.create(position_id="evals-0001", topic="evals", statement="A claim.", at=NOW, maturity=maturity)
    pos.sources = list(sources)
    return pos


# --- source-count ladder (uncontested, monotonic) --------------------------


def test_zero_or_one_source_is_open():
    assert compute_maturity(_position([]), now=NOW) is Maturity.open_question
    assert compute_maturity(_position([_source(1, days=0)]), now=NOW) is Maturity.open_question


def test_two_independent_sources_is_emerging():
    pos = _position([_source(1, days=0), _source(2, days=10)])
    assert compute_maturity(pos, now=NOW) is Maturity.emerging_trend


def test_two_sources_from_the_same_video_count_as_one():
    # distinct *videos* are the independent sources — two units from one video is still one.
    a = _source(1, days=0)
    b = PositionSource(unit_id="vid1#5", video_id="vid1", date=BASE.isoformat(),
                       alignment="supporting", stance="affirms", quote="q", statement="s")
    assert compute_maturity(_position([a, b]), now=NOW) is Maturity.open_question


def test_three_sources_over_long_span_is_converging():
    pos = _position([_source(1, days=0), _source(2, days=60), _source(3, days=120)])
    assert compute_maturity(pos, now=NOW) is Maturity.converging


def test_three_sources_over_short_span_is_only_emerging():
    # ≥3 sources but span < converging_min_span_days (90) → not yet converging.
    pos = _position([_source(1, days=0), _source(2, days=10), _source(3, days=20)])
    assert compute_maturity(pos, now=NOW) is Maturity.emerging_trend


# --- span boundaries -------------------------------------------------------


@pytest.mark.parametrize(
    "span_days,expected",
    [
        (89, Maturity.emerging_trend),   # just under the 90-day converging span
        (90, Maturity.converging),       # exactly the converging span
        (179, Maturity.converging),      # past converging, just under the solved span
        (180, Maturity.solved),          # exactly the solved span, never contested
    ],
)
def test_span_thresholds_for_three_sources(span_days, expected):
    pos = _position([_source(1, days=0), _source(2, days=span_days // 2), _source(3, days=span_days)])
    assert compute_maturity(pos, now=NOW) is expected


# --- solved is blocked by a prior contest ----------------------------------


def test_solved_requires_never_having_been_contested():
    pos = _position([_source(1, days=0), _source(2, days=90), _source(3, days=180)])
    # Absent any contest history it settles...
    assert compute_maturity(pos, now=NOW) is Maturity.solved
    # ...but once it has ever been contested, the conservative default caps it at converging.
    pos.record_transition(Maturity.contested, at=NOW, reason="was contested once")
    pos.record_transition(Maturity.converging, at=NOW, reason="dissent withdrawn")
    assert compute_maturity(pos, now=NOW) is Maturity.converging


# --- the contested override (adversarial reset) ----------------------------


def test_both_stances_present_forces_contested_regardless_of_counts():
    # Three agreeing sources over a long span would otherwise be converging/solved...
    sources = [_source(1, days=0), _source(2, days=90), _source(3, days=180)]
    # ...but a single opposing source (both stances now present) resets it to contested.
    sources.append(_source(4, days=200, alignment="opposing", stance="denies"))
    assert compute_maturity(_position(sources), now=NOW) is Maturity.contested


def test_opposing_only_is_not_contested():
    # "Contested" needs BOTH sides; a lone opposing source is just one source → open.
    pos = _position([_source(1, days=0, alignment="opposing", stance="denies")])
    assert compute_maturity(pos, now=NOW) is Maturity.open_question


# --- config drives the thresholds ------------------------------------------


def test_config_shifts_the_emerging_boundary():
    strict = MaturityConfig(emerging_min_sources=3)
    two = _position([_source(1, days=0), _source(2, days=10)])
    # two sources is emerging by default, but open under a stricter config
    assert compute_maturity(two, now=NOW) is Maturity.emerging_trend
    assert compute_maturity(two, now=NOW, config=strict) is Maturity.open_question


def test_config_shifts_the_converging_span():
    lenient = MaturityConfig(converging_min_span_days=30)
    pos = _position([_source(1, days=0), _source(2, days=20), _source(3, days=40)])
    # 40-day span is only emerging by default (needs 90) but converges under the lenient span
    assert compute_maturity(pos, now=NOW) is Maturity.emerging_trend
    assert compute_maturity(pos, now=NOW, config=lenient) is Maturity.converging
