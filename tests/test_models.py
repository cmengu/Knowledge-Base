"""VideoRecord invariants and serialization."""

from __future__ import annotations

import pytest

from kb.models import VideoRecord

VID = "abcdef12345"


def _record(**over):
    base = dict(
        id=VID,
        channel="Some Channel",
        date="2023-11-23T02:27:48Z",
        views=42,
        transcript=[{"text": "hello", "start": 0.0, "duration": 1.5}],
        chapters=[{"start": 0, "end": 20, "title": "Intro"}],
        title="A talk",
        url=f"https://www.youtube.com/watch?v={VID}",
        ingested_at="2026-07-22T00:00:00Z",
    )
    base.update(over)
    return VideoRecord(**base)


def test_valid_record_constructs():
    rec = _record()
    assert rec.id == VID
    assert rec.date == "2023-11-23T02:27:48Z"


@pytest.mark.parametrize("bad_date", ["", "   ", None])
def test_missing_date_is_rejected(bad_date):
    # The mandatory upload timestamp invariant is enforced at construction.
    with pytest.raises(ValueError, match="mandatory"):
        _record(date=bad_date)


@pytest.mark.parametrize("bad_id", ["", "   ", None])
def test_missing_id_is_rejected(bad_id):
    with pytest.raises(ValueError):
        _record(id=bad_id)


def test_views_may_be_none():
    assert _record(views=None).views is None


def test_to_row_from_row_roundtrip():
    rec = _record()
    rebuilt = VideoRecord.from_row(rec.to_row())
    assert rebuilt == rec


def test_to_row_serializes_nested_as_json_text():
    row = _record().to_row()
    assert isinstance(row["transcript"], str)
    assert isinstance(row["chapters"], str)
    assert "hello" in row["transcript"]


def test_transcript_text_flattens_segments():
    rec = _record(
        transcript=[
            {"text": "hello", "start": 0.0, "duration": 1.0},
            {"text": "world", "start": 1.0, "duration": 1.0},
            {"text": "  ", "start": 2.0, "duration": 1.0},  # blank dropped
        ]
    )
    assert rec.transcript_text() == "hello world"


def test_from_row_handles_empty_nested():
    row = _record().to_row()
    row["transcript"] = ""
    row["chapters"] = ""
    rebuilt = VideoRecord.from_row(row)
    assert rebuilt.transcript == []
    assert rebuilt.chapters == []
