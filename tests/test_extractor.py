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
    TranscriptSegment,
    UnitType,
    chunk_segments,
    extract_json_object,
    extract_units,
    merge_units,
)
from kb.extract.schema import Unit
from tests.helpers import ScriptedLLMClient

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


# --- chunking of long transcripts (ticket #18) ----------------------------


def _units_response(texts: list[str]) -> str:
    """A scripted extraction response carrying one claim per statement in ``texts``."""
    return json.dumps(
        {
            "units": [
                {
                    "type": "claim",
                    "text": t,
                    "raw_quote": t,
                    "timestamp": i,
                    "stance": "affirms",
                    "evidence_offered": [],
                }
                for i, t in enumerate(texts)
            ]
        }
    )


def _long_segments(count: int) -> list[TranscriptSegment]:
    return [
        TranscriptSegment(text=f"point number {i} stated plainly here", start=float(i))
        for i in range(count)
    ]


CHUNKY = ExtractionConfig(chunk_max_chars=250, chunk_overlap_chars=40)


def test_short_transcript_stays_single_call(sample_segments, fake_llm_factory):
    # The two-segment sample renders well under the chunk budget → one call, unchanged.
    client = fake_llm_factory(UNITS_JSON)
    run(client, sample_segments, config=CHUNKY)
    assert len(client.calls) == 1


def test_long_transcript_fans_out_one_call_per_chunk():
    segments = _long_segments(40)
    chunks = chunk_segments(segments, max_chars=250, overlap_chars=40)
    assert len(chunks) >= 2  # this transcript really is split

    # Script a distinct unit per chunk so nothing dedupes away.
    responses = [_units_response([f"claim from chunk {i}"]) for i in range(len(chunks))]
    client = ScriptedLLMClient(responses)
    video = run(client, segments, config=CHUNKY)

    assert len(client.calls) == len(chunks)                 # one call per chunk
    assert len(video.units) == len(chunks)                  # all merged in
    assert [u.unit_id for u in video.units] == [
        f"vid123#{i}" for i in range(len(chunks))
    ]                                                        # ids re-sequenced post-merge


def test_merge_dedupes_units_repeated_across_chunk_overlap():
    segments = _long_segments(24)
    two_chunk = ExtractionConfig(chunk_max_chars=600, chunk_overlap_chars=40)
    chunks = chunk_segments(segments, max_chars=600, overlap_chars=40)
    assert len(chunks) == 2  # keep the merge assertion concrete

    # The overlap makes the boundary unit appear in both chunks; it must merge to one.
    client = ScriptedLLMClient(
        [
            _units_response(["alpha point", "shared boundary point"]),
            _units_response(["Shared boundary point.", "gamma point"]),
        ]
    )
    video = run(client, segments, config=two_chunk)

    assert [u.text for u in video.units] == [
        "alpha point",
        "shared boundary point",
        "gamma point",
    ]
    assert [u.unit_id for u in video.units] == ["vid123#0", "vid123#1", "vid123#2"]


def test_chunk_segments_short_returns_original_single_chunk():
    segments = _long_segments(3)
    chunks = chunk_segments(segments, max_chars=100_000, overlap_chars=2_000)
    assert chunks == [segments]  # same objects, single chunk


def test_chunk_segments_overlaps_the_boundary():
    segments = _long_segments(30)
    chunks = chunk_segments(segments, max_chars=250, overlap_chars=60)
    assert len(chunks) >= 2
    # consecutive chunks share at least one boundary segment (the overlap)
    first_starts = {s.start for s in chunks[0]}
    second_starts = {s.start for s in chunks[1]}
    assert first_starts & second_starts
    # every original non-empty segment is covered by some chunk
    covered = {s.start for chunk in chunks for s in chunk}
    assert covered == {s.start for s in segments}


def test_merge_units_keeps_first_and_drops_near_duplicates():
    def u(text: str) -> Unit:
        return Unit(type="claim", text=text, raw_quote=text, timestamp=0, stance="affirms")

    merged = merge_units([[u("A point"), u("B point")], [u("a  point!!"), u("C point")]])
    assert [m.text for m in merged] == ["A point", "B point", "C point"]


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
