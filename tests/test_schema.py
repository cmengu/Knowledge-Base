"""Schema validation and round-trip tests for the fixed unit schema (ticket #04)."""

from __future__ import annotations

import datetime as dt

import pytest
from pydantic import ValidationError

from kb.extract import ExtractedVideo, ExtractionPayload, Stance, Unit, UnitType, parse_timestamp


def make_unit(**overrides) -> Unit:
    base = dict(
        type="claim",
        text="LLM-as-judge is reliable enough for production.",
        raw_quote="I'd say LLM as a judge is good enough to ship",
        timestamp=161.0,
        stance="affirms",
    )
    base.update(overrides)
    return Unit(**base)


# --- Unit ------------------------------------------------------------------


def test_unit_minimal_valid_and_defaults():
    unit = make_unit()
    assert unit.type is UnitType.claim
    assert unit.stance is Stance.affirms
    assert unit.evidence_offered == []       # defaults to empty list
    assert unit.unit_id is None              # assigned later by the extractor


def test_unit_json_roundtrip_is_identity():
    unit = make_unit(evidence_offered=["benchmark results"], unit_id="vid#3")
    restored = Unit.model_validate_json(unit.model_dump_json())
    assert restored == unit


def test_unit_evidence_offered_default_is_independent():
    a, b = make_unit(), make_unit()
    a.evidence_offered.append("x")
    assert b.evidence_offered == []          # default_factory, not a shared mutable


@pytest.mark.parametrize("value", ["claim", "content"])
def test_unit_type_accepts_valid(value):
    assert make_unit(type=value).type.value == value


def test_unit_type_rejects_unknown():
    with pytest.raises(ValidationError):
        make_unit(type="thesis")


@pytest.mark.parametrize("value", ["affirms", "denies", "neutral", "mixed"])
def test_stance_accepts_valid(value):
    assert make_unit(stance=value).stance.value == value


def test_stance_rejects_unknown():
    with pytest.raises(ValidationError):
        make_unit(stance="for")


def test_unit_text_is_stripped():
    assert make_unit(text="  spaced out  ").text == "spaced out"


@pytest.mark.parametrize("bad", ["", "   "])
def test_unit_text_rejects_blank(bad):
    with pytest.raises(ValidationError):
        make_unit(text=bad)


def test_unit_raw_quote_required_nonempty():
    with pytest.raises(ValidationError):
        make_unit(raw_quote="")


def test_unit_rejects_extra_fields():
    with pytest.raises(ValidationError):
        make_unit(confidence=0.9)            # extra="forbid": schema is fixed


# --- timestamp coercion ----------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        (161, 161.0),
        (12.5, 12.5),
        ("161", 161.0),
        ("0:19", 19.0),
        ("2:41", 161.0),
        ("1:02:03", 3723.0),
        ("  2:41  ", 161.0),
        (0, 0.0),
    ],
)
def test_timestamp_coercion_valid(raw, expected):
    assert make_unit(timestamp=raw).timestamp == expected
    assert parse_timestamp(raw) == expected


@pytest.mark.parametrize("bad", [-1, "-5", "", "later", True, ":::", "1:2:3:4", None])
def test_timestamp_coercion_invalid(bad):
    with pytest.raises(ValidationError):
        make_unit(timestamp=bad)


# --- ExtractedVideo --------------------------------------------------------


def test_extracted_video_defaults_topic_tags_empty():
    video = ExtractedVideo(video_id="vid", date="2025-05-11")
    assert video.topic_tags == []            # Layer 2 leaves routing to Layer 3
    assert video.units == []


@pytest.mark.parametrize(
    "raw",
    ["2025-05-11", "20250511", dt.date(2025, 5, 11), dt.datetime(2025, 5, 11, 9, 30)],
)
def test_extracted_video_date_coercion(raw):
    assert ExtractedVideo(video_id="vid", date=raw).date == dt.date(2025, 5, 11)


@pytest.mark.parametrize("bad", ["not-a-date", "2025-13-40", 20250511])
def test_extracted_video_date_invalid(bad):
    with pytest.raises(ValidationError):
        ExtractedVideo(video_id="vid", date=bad)


def test_extracted_video_requires_nonempty_id():
    with pytest.raises(ValidationError):
        ExtractedVideo(video_id="", date="2025-05-11")


def test_extracted_video_claim_and_content_partitions():
    video = ExtractedVideo(
        video_id="vid",
        date="2025-05-11",
        units=[make_unit(type="claim"), make_unit(type="content", stance="neutral")],
    )
    assert [u.type for u in video.claims] == [UnitType.claim]
    assert [u.type for u in video.content_units] == [UnitType.content]


def test_extracted_video_json_roundtrip():
    video = ExtractedVideo(
        video_id="vid",
        date="2025-05-11",
        topic_tags=["evals"],
        units=[make_unit(unit_id="vid#0")],
    )
    assert ExtractedVideo.model_validate_json(video.model_dump_json()) == video


def test_extracted_video_rejects_extra_fields():
    with pytest.raises(ValidationError):
        ExtractedVideo(video_id="vid", date="2025-05-11", channel="HF")


def test_extracted_video_rejects_bad_nested_unit():
    with pytest.raises(ValidationError):
        ExtractedVideo(video_id="vid", date="2025-05-11", units=[{"type": "claim"}])


# --- ExtractionPayload (the LLM-facing contract) ---------------------------


def test_extraction_payload_valid_and_empty():
    assert ExtractionPayload(units=[]).units == []
    payload = ExtractionPayload.model_validate({"units": [make_unit().model_dump()]})
    assert len(payload.units) == 1


def test_extraction_payload_rejects_extra_top_level_field():
    with pytest.raises(ValidationError):
        ExtractionPayload.model_validate({"units": [], "topic_tags": []})
