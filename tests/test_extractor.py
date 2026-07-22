"""Extraction-step behavior tests, driven by an injected fake LLM (no live calls).

These exercise the deterministic seam of Layer 2: JSON extraction, schema validation,
unit-id assignment, the topic-routing boundary, and the wiring from transcript+config
into the LLM client. LLM *quality* is not asserted here (it is non-deterministic and is
judged against the fixture in test_fixtures.py).
"""

from __future__ import annotations

import json

import pytest

from kb.extract import (
    ExtractedVideo,
    ExtractionConfig,
    ExtractionError,
    UnitType,
    extract_json_object,
    extract_units,
)

UNITS_JSON = json.dumps(
    {
        "units": [
            {
                "type": "claim",
                "text": "You must evaluate your own system, not just the base model.",
                "raw_quote": "you need to test it on the tasks that it is meant to solve",
                "timestamp": "0:40",
                "stance": "affirms",
                "evidence_offered": [],
            },
            {
                "type": "content",
                "text": "Evaluation during early building is mostly for experiments.",
                "raw_quote": "it is often about experiments",
                "timestamp": 77,
                "stance": "neutral",
                "evidence_offered": [],
            },
        ]
    }
)


def run(llm, segments, *, config=None, video_id="vid123", date="2025-05-11") -> ExtractedVideo:
    return extract_units(
        segments=segments, video_id=video_id, date=date, llm=llm, config=config
    )


def test_happy_path_builds_validated_video(sample_segments, fake_llm_factory):
    video = run(fake_llm_factory(UNITS_JSON), sample_segments)
    assert isinstance(video, ExtractedVideo)
    assert video.video_id == "vid123"
    assert str(video.date) == "2025-05-11"
    assert video.topic_tags == []                         # routing left to Layer 3
    assert [u.type for u in video.units] == [UnitType.claim, UnitType.content]
    assert video.units[0].timestamp == 40.0               # "0:40" coerced to seconds


def test_assigns_sequential_unit_ids(sample_segments, fake_llm_factory):
    video = run(fake_llm_factory(UNITS_JSON), sample_segments)
    assert [u.unit_id for u in video.units] == ["vid123#0", "vid123#1"]


def test_strips_code_fences(sample_segments, fake_llm_factory):
    fenced = f"```json\n{UNITS_JSON}\n```"
    assert len(run(fake_llm_factory(fenced), sample_segments).units) == 2


def test_ignores_surrounding_prose(sample_segments, fake_llm_factory):
    noisy = f"Sure! Here are the units:\n{UNITS_JSON}\nLet me know if you need more."
    assert len(run(fake_llm_factory(noisy), sample_segments).units) == 2


def test_raises_on_non_json(sample_segments, fake_llm_factory):
    with pytest.raises(ExtractionError):
        run(fake_llm_factory("I could not find anything to extract."), sample_segments)


def test_raises_on_bad_enum(sample_segments, fake_llm_factory):
    bad = json.dumps({"units": [{"type": "thesis", "text": "x", "raw_quote": "x",
                                 "timestamp": 1, "stance": "affirms"}]})
    with pytest.raises(ExtractionError):
        run(fake_llm_factory(bad), sample_segments)


def test_raises_on_blank_text(sample_segments, fake_llm_factory):
    bad = json.dumps({"units": [{"type": "claim", "text": "   ", "raw_quote": "x",
                                 "timestamp": 1, "stance": "affirms"}]})
    with pytest.raises(ExtractionError):
        run(fake_llm_factory(bad), sample_segments)


def test_raises_on_extra_unit_field(sample_segments, fake_llm_factory):
    bad = json.dumps({"units": [{"type": "claim", "text": "x", "raw_quote": "x",
                                 "timestamp": 1, "stance": "affirms", "confidence": 0.9}]})
    with pytest.raises(ExtractionError):
        run(fake_llm_factory(bad), sample_segments)


def test_propagates_llm_transport_error(sample_segments, fake_llm_factory):
    client = fake_llm_factory(raises=ExtractionError("Agent SDK query failed"))
    with pytest.raises(ExtractionError):
        run(client, sample_segments)


def test_sends_configured_model_and_transcript_to_llm(sample_segments, fake_llm_factory):
    client = fake_llm_factory(UNITS_JSON)
    config = ExtractionConfig(model="haiku")
    run(client, sample_segments, config=config)
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["model"] == "haiku"                       # config drives model routing
    # the transcript text reaches the LLM (behavior, not prompt wording)
    assert "evaluate your own system on its real task" in call["prompt"]
    assert "[0:15]" in call["prompt"]                     # timestamped rendering


def test_default_config_used_when_omitted(sample_segments, fake_llm_factory):
    client = fake_llm_factory(UNITS_JSON)
    run(client, sample_segments)                          # no config passed
    assert client.calls[0]["model"] == "sonnet"           # ExtractionConfig default


def test_truncates_overlong_transcript(fake_llm_factory):
    from kb.extract import TranscriptSegment

    segments = [
        TranscriptSegment(text=f"segment number {i} with some filler words", start=float(i))
        for i in range(500)
    ]
    client = fake_llm_factory(UNITS_JSON)
    run(client, segments, config=ExtractionConfig(max_transcript_chars=300))
    prompt = client.calls[0]["prompt"]
    assert "[transcript truncated for length]" in prompt
    # rendered body stays near the budget (prompt = preamble + <=budget transcript)
    assert len(prompt) < 600


def test_is_deterministic(sample_segments, fake_llm_factory):
    first = run(fake_llm_factory(UNITS_JSON), sample_segments)
    second = run(fake_llm_factory(UNITS_JSON), sample_segments)
    assert first == second


# --- extract_json_object helper -------------------------------------------


def test_json_object_plain():
    assert extract_json_object('{"units": []}') == '{"units": []}'


def test_json_object_from_fence():
    assert extract_json_object('```json\n{"a": 1}\n```') == '{"a": 1}'


def test_json_object_handles_braces_inside_strings():
    text = 'noise {"text": "a } b { c"} tail'
    assert extract_json_object(text) == '{"text": "a } b { c"}'


def test_json_object_handles_escaped_quote_in_string():
    text = r'{"text": "he said \"hi\" } there"}'
    assert extract_json_object(text) == text


def test_json_object_missing_raises():
    with pytest.raises(ExtractionError):
        extract_json_object("no json here")


def test_json_object_unterminated_raises():
    with pytest.raises(ExtractionError):
        extract_json_object('{"units": [')
