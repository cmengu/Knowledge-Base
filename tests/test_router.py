"""Routing-step behavior tests, driven by an injected fake LLM (no live calls).

These exercise the deterministic seam of Layer 3: the JSON/schema validation, the
config-driven topic set, multi-topic assignment plumbing, unit coverage, the Haiku->Sonnet
escalation, and the slice gate. LLM *quality* is not asserted here (it is non-deterministic
and is judged against the recorded fixture in test_route_fixtures.py).
"""

from __future__ import annotations

import json

import pytest

from kb.extract import ExtractedVideo, Unit
from kb.route import (
    RoutedVideo,
    RoutingConfig,
    RoutingError,
    route_video,
    units_for_downstream,
)
from tests.helpers import FakeLLMClient, ScriptedLLMClient

# A default topic set passed explicitly so these tests never depend on config/topics.yaml.
TOPICS = ["evals", "small-models", "open-source", "harness", "enterprise", "swe-practices"]


def make_units(*specs: tuple[str, str]) -> list[Unit]:
    """Build units from ``(unit_id, text)`` pairs (type/stance are irrelevant to routing)."""

    return [
        Unit(type="claim", text=text, raw_quote=text, timestamp=float(i), stance="affirms", unit_id=uid)
        for i, (uid, text) in enumerate(specs)
    ]


def make_video(units: list[Unit], *, video_id: str = "vid", date: str = "2025-05-11") -> ExtractedVideo:
    return ExtractedVideo(video_id=video_id, date=date, units=units)


def routing_json(video_topics: list[str], unit_topics: dict[str, list[str]]) -> str:
    return json.dumps(
        {
            "video_topics": video_topics,
            "units": [{"unit_id": uid, "topics": topics} for uid, topics in unit_topics.items()],
        }
    )


VIDEO = make_video(make_units(("vid#0", "on evaluation harnesses"), ("vid#1", "on small models")))
VALID = routing_json(["evals"], {"vid#0": ["evals", "harness"], "vid#1": ["small-models"]})


def route(llm, video=VIDEO, *, config=None, topics=TOPICS) -> RoutedVideo:
    return route_video(video, llm=llm, config=config, topics=topics)


# --- happy path & shape ----------------------------------------------------


def test_happy_path_builds_routed_video():
    routed = route(FakeLLMClient(VALID))
    assert isinstance(routed, RoutedVideo)
    assert routed.video_id == "vid"
    assert str(routed.date) == "2025-05-11"
    assert routed.topic_tags == ["evals"]
    assert [ru.unit.unit_id for ru in routed.units] == ["vid#0", "vid#1"]


def test_multi_topic_assignment_plumbing():
    """A unit can carry >1 topic end-to-end (spec: multi-topic assignment per unit)."""

    routed = route(FakeLLMClient(VALID))
    assert routed.units[0].topics == ["evals", "harness"]   # both topics survive
    assert routed.units[1].topics == ["small-models"]


def test_every_unit_gets_an_assignment():
    routed = route(FakeLLMClient(VALID))
    assert all(ru.topics for ru in routed.units)
    assert len(routed.units) == len(VIDEO.units)


def test_to_extracted_video_populates_topic_tags():
    routed = route(FakeLLMClient(VALID))
    extracted = routed.to_extracted_video()
    assert isinstance(extracted, ExtractedVideo)
    assert extracted.topic_tags == ["evals"]                # the field extract reserved
    assert [u.unit_id for u in extracted.units] == ["vid#0", "vid#1"]


def test_original_units_are_preserved_unmodified():
    routed = route(FakeLLMClient(VALID))
    assert routed.units[0].unit is VIDEO.units[0]           # overlay, not a copy/mutation


def test_is_deterministic():
    assert route(FakeLLMClient(VALID)) == route(FakeLLMClient(VALID))


def test_topic_order_and_duplicates_are_normalized():
    dupes = routing_json(["evals", "evals"], {"vid#0": ["harness", "harness"], "vid#1": ["evals"]})
    routed = route(FakeLLMClient(dupes))
    assert routed.topic_tags == ["evals"]                   # deduped, order preserved
    assert routed.units[0].topics == ["harness"]


# --- config-driven topic set ----------------------------------------------


def test_topics_come_from_injected_set():
    """A topic set injected via `topics=` (not hard-coded six) is what's accepted."""

    custom = routing_json(["robotics"], {"vid#0": ["robotics"], "vid#1": ["evals"]})
    routed = route(FakeLLMClient(custom), topics=["evals", "robotics"])
    assert routed.topic_tags == ["robotics"]
    assert routed.units[0].topics == ["robotics"]


def test_rejects_topic_outside_configured_set():
    off_set = routing_json(["evals"], {"vid#0": ["robotics"], "vid#1": ["evals"]})
    with pytest.raises(RoutingError, match="unknown topic"):
        route(FakeLLMClient(off_set))                       # 'robotics' not in TOPICS


def test_default_topic_set_loaded_from_config():
    """With no `topics=`, the six-topic config set is used: 'evals' ok, 'robotics' rejected."""

    ok = route_video(VIDEO, llm=FakeLLMClient(VALID))       # topics default -> config
    assert ok.topic_tags == ["evals"]
    bad = routing_json(["robotics"], {"vid#0": ["evals"], "vid#1": ["evals"]})
    with pytest.raises(RoutingError):
        route_video(VIDEO, llm=FakeLLMClient(bad), config=RoutingConfig(fallback_model="haiku"))


@pytest.mark.parametrize("returned", ["Small Models", "small_models", " small-models "])
def test_topic_normalization_folds_formatting_drift(returned):
    drifted = routing_json(["evals"], {"vid#0": ["evals"], "vid#1": [returned]})
    routed = route(FakeLLMClient(drifted))
    assert routed.units[1].topics == ["small-models"]       # mapped to the canonical key


# --- escalation (Haiku -> Sonnet) -----------------------------------------


def test_no_escalation_when_primary_output_valid():
    client = FakeLLMClient(VALID)
    route(client, config=RoutingConfig(model="haiku", fallback_model="sonnet"))
    assert [c["model"] for c in client.calls] == ["haiku"]  # one call, primary only


def test_escalates_to_fallback_on_invalid_output():
    client = ScriptedLLMClient(["not json", VALID])         # haiku fails, sonnet ok
    routed = route(client, config=RoutingConfig(model="haiku", fallback_model="sonnet"))
    assert routed.topic_tags == ["evals"]
    assert client.models == ["haiku", "sonnet"]             # escalated exactly once


def test_raises_when_all_models_fail_validation():
    client = ScriptedLLMClient(["not json", "still not json"])
    with pytest.raises(RoutingError):
        route(client, config=RoutingConfig(model="haiku", fallback_model="sonnet"))
    assert client.models == ["haiku", "sonnet"]             # both tiers were tried


def test_no_escalation_when_fallback_equals_primary():
    client = ScriptedLLMClient(["not json"])
    with pytest.raises(RoutingError):
        route(client, config=RoutingConfig(model="haiku", fallback_model="haiku"))
    assert client.models == ["haiku"]                       # escalation disabled -> single try


def test_empty_fallback_disables_escalation():
    client = ScriptedLLMClient(["not json"])
    with pytest.raises(RoutingError):
        route(client, config=RoutingConfig(model="haiku", fallback_model=""))
    assert client.models == ["haiku"]


def test_transport_error_is_not_escalated():
    """A client/transport failure is not a validation failure -> propagates, no retry."""

    boom = RuntimeError("Agent SDK transport died")
    client = ScriptedLLMClient([boom, VALID])
    with pytest.raises(RuntimeError):
        route(client, config=RoutingConfig(model="haiku", fallback_model="sonnet"))
    assert client.models == ["haiku"]                       # did not fall through to sonnet


def test_uses_configured_models():
    client = ScriptedLLMClient(["not json", VALID])
    route(client, config=RoutingConfig(model="sonnet", fallback_model="opus"))
    assert client.models == ["sonnet", "opus"]              # config drives both tiers


# --- output validation failures (each triggers escalation, then RoutingError) ----


def test_missing_unit_assignment_raises():
    incomplete = routing_json(["evals"], {"vid#0": ["evals"]})   # vid#1 omitted
    with pytest.raises(RoutingError, match="missing an assignment"):
        route(FakeLLMClient(incomplete))


def test_unknown_unit_id_raises():
    extra = routing_json(["evals"], {"vid#0": ["evals"], "vid#1": ["evals"], "vid#9": ["evals"]})
    with pytest.raises(RoutingError, match="unknown unit ids"):
        route(FakeLLMClient(extra))


def test_duplicate_unit_id_raises():
    dup = json.dumps({"video_topics": ["evals"], "units": [
        {"unit_id": "vid#0", "topics": ["evals"]},
        {"unit_id": "vid#0", "topics": ["harness"]},
        {"unit_id": "vid#1", "topics": ["evals"]}]})
    with pytest.raises(RoutingError, match="duplicate unit id"):
        route(FakeLLMClient(dup))


def test_zero_topics_for_a_unit_raises():
    empty = json.dumps({"video_topics": ["evals"], "units": [
        {"unit_id": "vid#0", "topics": []},                 # violates min_length=1
        {"unit_id": "vid#1", "topics": ["evals"]}]})
    with pytest.raises(RoutingError):
        route(FakeLLMClient(empty))


def test_empty_video_topics_raises():
    bad = json.dumps({"video_topics": [], "units": [
        {"unit_id": "vid#0", "topics": ["evals"]},
        {"unit_id": "vid#1", "topics": ["evals"]}]})
    with pytest.raises(RoutingError):
        route(FakeLLMClient(bad))


def test_non_json_raises():
    with pytest.raises(RoutingError):
        route(FakeLLMClient("I could not classify these."))


def test_extra_top_level_field_raises():
    bad = json.dumps({"video_topics": ["evals"], "note": "hi", "units": [
        {"unit_id": "vid#0", "topics": ["evals"]},
        {"unit_id": "vid#1", "topics": ["evals"]}]})
    with pytest.raises(RoutingError):
        route(FakeLLMClient(bad))


def test_strips_code_fences_and_prose():
    fenced = f"Here you go:\n```json\n{VALID}\n```\nHope that helps!"
    routed = route(FakeLLMClient(fenced))                   # reuses extract_json_object scan
    assert routed.topic_tags == ["evals"]


# --- empty-unit video (degenerate) ----------------------------------------


def test_empty_video_routes_without_an_llm_call():
    client = FakeLLMClient(VALID)
    routed = route_video(make_video([]), llm=client, topics=TOPICS)
    assert routed.units == []
    assert routed.topic_tags == TOPICS                      # tagged with the whole set
    assert client.calls == []                               # no LLM call spent on zero units


# --- slice gate (units_for_downstream) ------------------------------------


@pytest.fixture
def mixed_routed() -> RoutedVideo:
    units = make_units(
        ("vid#0", "evals point"),
        ("vid#1", "small-models point"),
        ("vid#2", "evals + harness point"),
    )
    payload = routing_json(
        ["evals", "small-models", "harness"],
        {"vid#0": ["evals"], "vid#1": ["small-models"], "vid#2": ["evals", "harness"]},
    )
    return route_video(make_video(units), llm=FakeLLMClient(payload), topics=TOPICS)


def test_slice_passes_only_units_routed_to_the_topic(mixed_routed):
    passed = units_for_downstream(mixed_routed, slice_topic="evals")
    assert [ru.unit.unit_id for ru in passed] == ["vid#0", "vid#2"]   # vid#1 filtered out


def test_slice_includes_multi_topic_unit(mixed_routed):
    passed = units_for_downstream(mixed_routed, slice_topic="harness")
    assert [ru.unit.unit_id for ru in passed] == ["vid#2"]            # matched via its 2nd topic


def test_slice_none_widens_to_all_units(mixed_routed):
    passed = units_for_downstream(mixed_routed, slice_topic=None)
    assert [ru.unit.unit_id for ru in passed] == ["vid#0", "vid#1", "vid#2"]


def test_slice_unmatched_topic_yields_nothing(mixed_routed):
    assert units_for_downstream(mixed_routed, slice_topic="enterprise") == []
