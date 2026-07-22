"""Pure yt-dlp field normalization — deterministic, no network."""

from __future__ import annotations

import pytest

from kb.ingest.fetchers import (
    metadata_from_info,
    normalize_chapters,
    normalize_upload_timestamp,
)
from tests.conftest import KARPATHY_LLM, load_rawinfo


def test_epoch_timestamp_to_iso():
    # 1700706468 == 2023-11-23T02:27:48Z
    assert normalize_upload_timestamp(1700706468, None) == "2023-11-23T02:27:48Z"


def test_upload_date_fallback_to_midnight_utc():
    assert normalize_upload_timestamp(None, "20231123") == "2023-11-23T00:00:00Z"


def test_epoch_preferred_over_upload_date():
    # Precise epoch wins over the date-only field.
    assert normalize_upload_timestamp(1700706468, "19990101") == "2023-11-23T02:27:48Z"


def test_no_timestamp_returns_none():
    assert normalize_upload_timestamp(None, None) is None


def test_bad_upload_date_returns_none():
    assert normalize_upload_timestamp(None, "not-a-date") is None
    assert normalize_upload_timestamp(None, "2023") is None


def test_bad_epoch_falls_back_to_upload_date():
    huge = 10**20  # out of range for fromtimestamp
    assert normalize_upload_timestamp(huge, "20231123") == "2023-11-23T00:00:00Z"


def test_normalize_chapters_none_is_empty():
    assert normalize_chapters(None) == []
    assert normalize_chapters([]) == []


def test_normalize_chapters_maps_yt_dlp_shape():
    out = normalize_chapters(
        [{"start_time": 0, "end_time": 20, "title": "Intro"}, "junk", {"bad": 1}]
    )
    assert out[0] == {"start": 0, "end": 20, "title": "Intro"}
    # non-dict entries skipped; dict without keys still normalized with defaults
    assert {"start": None, "end": None, "title": ""} in out
    assert len(out) == 2


def test_metadata_from_recorded_info():
    info = load_rawinfo(KARPATHY_LLM)
    meta = metadata_from_info(info)
    assert meta.id == KARPATHY_LLM
    assert meta.channel == "Andrej Karpathy"
    assert meta.upload_timestamp == "2023-11-23T02:27:48Z"
    assert meta.views == 3895018
    assert meta.title.startswith("[1hr Talk]")
    assert len(meta.chapters) == 21
    assert set(meta.chapters[0]) == {"start", "end", "title"}


def test_metadata_channel_falls_back_to_uploader():
    meta = metadata_from_info(
        {"id": "x" * 11, "uploader": "Only Uploader", "timestamp": 1700706468}
    )
    assert meta.channel == "Only Uploader"


def test_metadata_missing_timestamp_is_none():
    meta = metadata_from_info({"id": "x" * 11, "channel": "C"})
    assert meta.upload_timestamp is None
