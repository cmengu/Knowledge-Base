"""Fixture-bound tests: the committed prototype output round-trips against the code.

These use recorded fixtures (a real transcript + the real model's verbatim response +
the sample extraction), never a live call. They prove (a) the recorded sample is valid
against the fixed schema, and (b) replaying the recorded LLM response through the
extractor reproduces that sample exactly — binding transcript -> raw -> extraction to
the current code.
"""

from __future__ import annotations

from kb.extract import ExtractedVideo, TranscriptSegment, extract_units
from tests.helpers import (
    FakeLLMClient,
    load_recorded_extraction,
    load_segments,
    load_transcript_document,
    read_recorded_raw,
)


def test_transcript_fixture_is_valid(fixture_video_id):
    document = load_transcript_document(fixture_video_id)
    assert document["video_id"] == fixture_video_id
    assert document["segments"], "transcript fixture must have segments"
    segments = [TranscriptSegment.model_validate(seg) for seg in document["segments"]]
    assert all(seg.start >= 0 for seg in segments)
    # date is present and coercible by the schema
    assert ExtractedVideo(video_id=fixture_video_id, date=document["date"]).date is not None


def test_recorded_extraction_is_schema_valid(fixture_video_id):
    data = load_recorded_extraction(fixture_video_id)
    video = ExtractedVideo.model_validate(data)           # recorded sample is schema-valid
    assert video.video_id == fixture_video_id
    assert video.units, "sample extraction should contain units"
    assert video.topic_tags == []                         # Layer 2 output leaves routing empty
    assert video.claims, "the evals talk should yield at least one claim"
    # unit ids follow the extractor's contract
    assert [u.unit_id for u in video.units] == [f"{fixture_video_id}#{i}" for i in range(len(video.units))]


def test_replay_reproduces_recorded_extraction(fixture_video_id):
    """Replaying the recorded raw LLM output must reproduce the committed sample."""

    segments = load_segments(fixture_video_id)
    document = load_transcript_document(fixture_video_id)
    recorded_raw = read_recorded_raw(fixture_video_id)

    reproduced = extract_units(
        segments=segments,
        video_id=fixture_video_id,
        date=document["date"],
        llm=FakeLLMClient(recorded_raw),                  # replay, no live call
    )

    expected = ExtractedVideo.model_validate(load_recorded_extraction(fixture_video_id))
    assert reproduced == expected
