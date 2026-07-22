"""Position data-model tests (ticket #06).

Covers the three seams the ticket calls out — round-trip serialization, status-history
append semantics, and contested-both-stances integrity — plus the model invariants and
the derived views the maturity machine (#09) and digest (#10) build on. No LLM, no disk:
the model is pure data, so these are plain deterministic value assertions.
"""

from __future__ import annotations

import datetime as dt

import pytest
from pydantic import ValidationError

from kb.extract import Unit
from kb.reconcile import Alignment, Maturity, Position, PositionSource, StatusEvent

T0 = dt.datetime(2025, 5, 11, 9, 0)
T1 = dt.datetime(2025, 6, 1, 9, 0)
T2 = dt.datetime(2025, 8, 20, 9, 0)


def make_source(**overrides) -> PositionSource:
    base = dict(
        unit_id="vidA#1",
        video_id="vidA",
        date="2025-05-11",
        alignment="supporting",
        stance="affirms",
        quote="you need to build your own evals",
        statement="You should build your own task-specific evals.",
    )
    base.update(overrides)
    return PositionSource(**base)


def make_position(**overrides) -> Position:
    base = dict(
        position_id="evals-0001",
        topic="evals",
        statement="You should build your own task-specific evals.",
        at=T0,
        first_source=make_source(),
    )
    base.update(overrides)
    return Position.create(**base)


# --- enums -----------------------------------------------------------------


def test_maturity_string_values_match_spec():
    # The canonical long-form names from the spec's solution statement + ticket #06.
    assert [m.value for m in Maturity] == [
        "open-question",
        "emerging-trend",
        "converging",
        "solved",
        "contested",
    ]


def test_alignment_values():
    assert {a.value for a in Alignment} == {"supporting", "opposing"}


# --- PositionSource --------------------------------------------------------


def test_source_defaults_and_evidence_independent():
    a, b = make_source(), make_source()
    assert a.evidence_offered == []
    a.evidence_offered.append("benchmark")
    assert b.evidence_offered == []          # default_factory, not shared mutable


def test_source_date_coerces_from_iso_string():
    assert make_source(date="2025-05-11").date == dt.date(2025, 5, 11)


def test_source_json_roundtrip_is_identity():
    src = make_source(evidence_offered=["benchmark results"])
    assert PositionSource.model_validate_json(src.model_dump_json()) == src


@pytest.mark.parametrize("field", ["unit_id", "video_id", "quote", "statement"])
def test_source_rejects_blank_required_text(field):
    with pytest.raises(ValidationError):
        make_source(**{field: ""})


def test_source_rejects_extra_fields():
    with pytest.raises(ValidationError):
        make_source(confidence=0.9)


def test_source_rejects_unknown_alignment():
    with pytest.raises(ValidationError):
        make_source(alignment="maybe")


# --- PositionSource.from_unit (reuse of the issue-4 unit schema) ------------


def _unit(**overrides) -> Unit:
    base = dict(
        type="claim",
        text="Small models are now good enough for most tasks.",
        raw_quote="small models are good enough now",
        timestamp=10,
        stance="affirms",
        unit_id="vidC#0",
    )
    base.update(overrides)
    return Unit(**base)


def test_from_unit_projects_unit_fields():
    src = PositionSource.from_unit(_unit(), video_id="vidC", date="2025-07-01", alignment="supporting")
    assert src.unit_id == "vidC#0"
    assert src.video_id == "vidC"
    assert src.date == dt.date(2025, 7, 1)
    assert src.stance.value == "affirms"     # reused straight from the unit
    assert src.quote == "small models are good enough now"   # raw_quote -> quote
    assert src.statement == "Small models are now good enough for most tasks."  # text -> statement
    assert src.alignment is Alignment.supporting


def test_from_unit_opposing_alignment_is_independent_of_unit_stance():
    # A unit that *affirms* its own subject can still be an *opposing* source of a
    # position phrased the other way — alignment and stance are deliberately separate.
    src = PositionSource.from_unit(_unit(stance="affirms"), video_id="v", date="2025-07-01", alignment="opposing")
    assert src.stance is not None and src.alignment is Alignment.opposing


def test_from_unit_requires_assigned_unit_id():
    with pytest.raises(ValueError):
        PositionSource.from_unit(_unit(unit_id=None), video_id="v", date="2025-07-01", alignment="supporting")


# --- Position.create -------------------------------------------------------


def test_create_defaults_open_and_seeds_creation_event():
    pos = make_position()
    assert pos.maturity is Maturity.open_question
    assert len(pos.status_history) == 1
    seed = pos.status_history[0]
    assert seed.from_maturity is None                 # creation event
    assert seed.to_maturity is Maturity.open_question
    assert seed.trigger_unit_id == "vidA#1"           # from the first source
    assert pos.created_at == T0 and pos.updated_at == T0


def test_create_without_first_source():
    pos = make_position(first_source=None)
    assert pos.sources == []
    assert pos.status_history[0].trigger_unit_id is None


def test_create_with_explicit_maturity_is_head_of_history():
    pos = make_position(maturity=Maturity.emerging_trend)
    assert pos.maturity is Maturity.emerging_trend
    assert pos.status_history[-1].to_maturity is Maturity.emerging_trend


# --- status-history append semantics ---------------------------------------


def test_transition_appends_event_and_moves_flag():
    pos = make_position()
    event = pos.record_transition(Maturity.emerging_trend, at=T1, reason="a second source agreed")
    assert isinstance(event, StatusEvent)
    assert pos.maturity is Maturity.emerging_trend
    assert len(pos.status_history) == 2
    assert pos.status_history[-1] is event
    assert event.from_maturity is Maturity.open_question
    assert event.to_maturity is Maturity.emerging_trend
    assert event.reason == "a second source agreed"
    assert event.at == T1


def test_noop_transition_to_same_maturity_returns_none_and_leaves_history():
    pos = make_position()
    before = list(pos.status_history)
    assert pos.record_transition(Maturity.open_question, at=T1, reason="unchanged") is None
    assert pos.status_history == before               # append-only record of *changes*
    assert pos.maturity is Maturity.open_question


def test_transition_records_trigger_unit_id():
    pos = make_position()
    event = pos.record_transition(
        Maturity.contested, at=T1, reason="adversarial unit", trigger_unit_id="vidB#3"
    )
    assert event.trigger_unit_id == "vidB#3"


def test_transition_bumps_updated_at_not_created_at():
    pos = make_position()
    pos.record_transition(Maturity.emerging_trend, at=T1, reason="grew")
    assert pos.updated_at == T1
    assert pos.created_at == T0                        # creation stamp is immutable


def test_history_is_ordered_and_head_always_matches_maturity():
    pos = make_position()
    pos.record_transition(Maturity.emerging_trend, at=T1, reason="two sources")
    pos.record_transition(Maturity.converging, at=T2, reason="agree over months")
    pos.record_transition(Maturity.contested, at=T2, reason="a dissent reopened it")
    tos = [e.to_maturity for e in pos.status_history]
    assert tos == [
        Maturity.open_question,
        Maturity.emerging_trend,
        Maturity.converging,
        Maturity.contested,
    ]
    # the "when it reopened" audit trail: adjacent from/to chain correctly
    assert [e.from_maturity for e in pos.status_history][1:] == tos[:-1]
    assert pos.status_history[-1].to_maturity is pos.maturity


# --- add_source ------------------------------------------------------------


def test_add_source_appends_and_bumps_updated_at_when_at_given():
    pos = make_position()
    pos.add_source(make_source(unit_id="vidB#2", video_id="vidB", date="2025-06-01"), at=T1)
    assert len(pos.sources) == 2
    assert pos.updated_at == T1


def test_add_source_without_at_leaves_updated_at():
    pos = make_position()
    pos.add_source(make_source(unit_id="vidB#2", video_id="vidB"))
    assert pos.updated_at == T0                        # no timestamp supplied -> unchanged


def test_add_source_does_not_touch_maturity():
    pos = make_position()
    pos.add_source(make_source(unit_id="vidB#2", alignment="opposing", stance="denies"))
    assert pos.maturity is Maturity.open_question      # maturity is #09's job, not add_source's


# --- contested-both-stances integrity --------------------------------------


def _contested() -> Position:
    pos = make_position()  # one supporting source
    pos.add_source(
        make_source(
            unit_id="vidB#3",
            video_id="vidB",
            date="2025-06-15",
            alignment="opposing",
            stance="denies",
            quote="public benchmarks are enough on their own",
            statement="Public benchmarks are sufficient.",
        ),
        at=T1,
    )
    return pos


def test_single_side_is_not_contested():
    supporting_only = make_position()
    assert supporting_only.is_contested is False
    opposing_only = make_position(
        first_source=make_source(alignment="opposing", stance="denies")
    )
    assert opposing_only.is_contested is False         # needs *both* sides


def test_contested_requires_both_sides_present():
    pos = _contested()
    assert pos.is_contested is True
    assert len(pos.supporting_sources) == 1
    assert len(pos.opposing_sources) == 1


def test_both_stances_carry_quote_source_and_date():
    pos = _contested()
    support = pos.supporting_sources[0]
    oppose = pos.opposing_sources[0]
    # each side is independently citable: quote + video + date, per the guardrail
    assert support.quote and support.video_id == "vidA" and support.date == dt.date(2025, 5, 11)
    assert oppose.quote and oppose.video_id == "vidB" and oppose.date == dt.date(2025, 6, 15)
    assert support.quote != oppose.quote               # genuinely two different claims


def test_contested_both_stances_survive_json_roundtrip():
    pos = _contested()
    pos.record_transition(Maturity.contested, at=T1, reason="dissent", trigger_unit_id="vidB#3")
    restored = Position.model_validate_json(pos.model_dump_json())
    assert restored == pos
    assert restored.is_contested is True
    assert len(restored.supporting_sources) == 1 and len(restored.opposing_sources) == 1


# --- derived views (substrate for #09 / #10) -------------------------------


def test_source_dates_earliest_latest_and_span():
    pos = _contested()
    assert pos.source_dates == [dt.date(2025, 5, 11), dt.date(2025, 6, 15)]
    assert pos.earliest_date == dt.date(2025, 5, 11)
    assert pos.latest_date == dt.date(2025, 6, 15)
    assert pos.span_days == 35


def test_span_is_zero_for_single_source_and_none_for_empty():
    assert make_position().span_days == 0
    empty = make_position(first_source=None)
    assert empty.span_days is None
    assert empty.earliest_date is None


def test_distinct_videos_and_unit_ids():
    pos = _contested()
    assert pos.distinct_videos == {"vidA", "vidB"}
    assert pos.unit_ids == ["vidA#1", "vidB#3"]


# --- invariants & round-trip -----------------------------------------------


def test_full_position_json_roundtrip_is_identity():
    pos = _contested()
    pos.record_transition(Maturity.emerging_trend, at=T1, reason="grew")
    pos.record_transition(Maturity.contested, at=T2, reason="reopened", trigger_unit_id="vidB#3")
    assert Position.model_validate_json(pos.model_dump_json()) == pos


def test_load_rejects_empty_status_history():
    data = make_position().model_dump(mode="json")
    data["status_history"] = []
    with pytest.raises(ValidationError):
        Position.model_validate(data)


def test_load_rejects_maturity_disagreeing_with_history_head():
    data = make_position().model_dump(mode="json")
    data["maturity"] = "solved"                        # history head is still open-question
    with pytest.raises(ValidationError):
        Position.model_validate(data)


def test_position_rejects_extra_fields():
    data = make_position().model_dump(mode="json")
    data["confidence"] = 0.9
    with pytest.raises(ValidationError):
        Position.model_validate(data)


@pytest.mark.parametrize("field", ["position_id", "topic", "statement"])
def test_position_rejects_blank_required_text(field):
    data = make_position().model_dump(mode="json")
    data[field] = ""
    with pytest.raises(ValidationError):
        Position.model_validate(data)
