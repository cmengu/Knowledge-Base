"""Fixture-bound routing tests: the committed prototype output round-trips against the code.

These use recorded fixtures (issue-4's committed extraction sample + the real Haiku
response + the routed sample), never a live call. They prove (a) the recorded routing is
valid against the routing schema and the config topic set, (b) it covers exactly the
extracted units, (c) it really contains multi-topic assignments, and (d) replaying the
recorded raw response through the router reproduces the committed sample exactly —
binding extraction-sample -> raw -> routing to the current code.
"""

from __future__ import annotations

from kb.config import load_topics
from kb.extract import ExtractedVideo
from kb.route import RoutedVideo, route_video, units_for_downstream
from tests.helpers import (
    FakeLLMClient,
    load_recorded_extraction,
    load_recorded_routing,
    read_recorded_routing_raw,
)


def test_recorded_routing_is_schema_valid(routing_video_id):
    routed = RoutedVideo.model_validate(load_recorded_routing(routing_video_id))
    assert routed.video_id == routing_video_id
    assert routed.topic_tags, "video-level topic tags must be non-empty"
    assert routed.units, "routing sample should contain routed units"
    assert all(ru.topics for ru in routed.units), "every routed unit has >=1 topic"


def test_recorded_routing_topics_are_a_subset_of_config(routing_video_id):
    routed = RoutedVideo.model_validate(load_recorded_routing(routing_video_id))
    allowed = set(load_topics())
    assert set(routed.topic_tags) <= allowed
    for ru in routed.units:
        assert set(ru.topics) <= allowed, f"{ru.unit.unit_id} has an off-config topic"


def test_recorded_routing_covers_exactly_the_extracted_units(routing_video_id):
    routed = RoutedVideo.model_validate(load_recorded_routing(routing_video_id))
    extracted = ExtractedVideo.model_validate(load_recorded_extraction(routing_video_id))
    assert [ru.unit.unit_id for ru in routed.units] == [u.unit_id for u in extracted.units]


def test_recorded_routing_contains_a_multi_topic_unit(routing_video_id):
    """Proves multi-topic assignment happens on real model output, not just in fakes."""

    routed = RoutedVideo.model_validate(load_recorded_routing(routing_video_id))
    assert any(len(ru.topics) > 1 for ru in routed.units)


def test_recorded_routing_slice_is_consistent(routing_video_id):
    routed = RoutedVideo.model_validate(load_recorded_routing(routing_video_id))
    evals_slice = units_for_downstream(routed, slice_topic="evals")
    assert all("evals" in ru.topics for ru in evals_slice)
    assert all("evals" not in ru.topics for ru in routed.units if ru not in evals_slice)
    assert units_for_downstream(routed, slice_topic=None) == routed.units   # widened = all


def test_replay_reproduces_recorded_routing(routing_video_id):
    """Replaying the recorded raw model output must reproduce the committed routed sample."""

    extracted = ExtractedVideo.model_validate(load_recorded_extraction(routing_video_id))
    recorded_raw = read_recorded_routing_raw(routing_video_id)

    reproduced = route_video(
        extracted,
        llm=FakeLLMClient(recorded_raw),        # replay, no live call
        topics=load_topics(),
    )

    expected = RoutedVideo.model_validate(load_recorded_routing(routing_video_id))
    assert reproduced == expected
