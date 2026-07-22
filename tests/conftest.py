"""Shared test fixtures and offline fakes.

No test touches the network or an LLM. The two ingest dependencies (metadata +
transcript) are replaced by fakes that serve *recorded* fixtures captured from a
one-off live run (``tests/fixtures/*.json``).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kb.ingest.errors import MetadataUnavailableError, TranscriptUnavailableError
from kb.ingest.fetchers import metadata_from_info
from kb.store import VideoStore

FIXTURES = Path(__file__).parent / "fixtures"

# Video ids for which we captured real yt-dlp info + transcript fixtures.
KARPATHY_LLM = "zjkBMFhNj_g"  # "[1hr Talk] Intro to Large Language Models"
NO_PRIORS = "hM_h0UA7upI"  # "No Priors Ep. 80 | With Andrej Karpathy"
KNOWN_IDS = (KARPATHY_LLM, NO_PRIORS)


def load_rawinfo(video_id: str) -> dict:
    return json.loads((FIXTURES / f"{video_id}.rawinfo.json").read_text("utf-8"))


def load_transcript(video_id: str) -> list[dict]:
    return json.loads((FIXTURES / f"{video_id}.transcript.json").read_text("utf-8"))


class FakeMetadataFetcher:
    """Serves recorded :class:`VideoMetadata`; records every call."""

    def __init__(self, metadata_by_id: dict) -> None:
        self.metadata_by_id = dict(metadata_by_id)
        self.calls: list[str] = []

    def fetch(self, video_id: str):
        self.calls.append(video_id)
        if video_id not in self.metadata_by_id:
            raise MetadataUnavailableError(f"no fixture metadata for {video_id}")
        return self.metadata_by_id[video_id]


class FakeTranscriptFetcher:
    """Serves recorded transcripts; records every call."""

    def __init__(self, transcript_by_id: dict) -> None:
        self.transcript_by_id = dict(transcript_by_id)
        self.calls: list[str] = []

    def fetch(self, video_id: str) -> list[dict]:
        self.calls.append(video_id)
        if video_id not in self.transcript_by_id:
            raise TranscriptUnavailableError(f"no fixture transcript for {video_id}")
        return list(self.transcript_by_id[video_id])


class ExplodingFetcher:
    """Fails the test if ``fetch`` is ever called.

    Proves the dedup / bad-input paths make **no** network call.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []

    def fetch(self, video_id: str):
        self.calls.append(video_id)
        raise AssertionError(f"fetch() must not be called (got {video_id!r})")


@pytest.fixture
def recorded_metadata() -> dict:
    """Recorded VideoMetadata for every known id (built from real yt-dlp info)."""
    return {vid: metadata_from_info(load_rawinfo(vid)) for vid in KNOWN_IDS}


@pytest.fixture
def recorded_transcripts() -> dict:
    return {vid: load_transcript(vid) for vid in KNOWN_IDS}


@pytest.fixture
def metadata_fetcher(recorded_metadata) -> FakeMetadataFetcher:
    return FakeMetadataFetcher(recorded_metadata)


@pytest.fixture
def transcript_fetcher(recorded_transcripts) -> FakeTranscriptFetcher:
    return FakeTranscriptFetcher(recorded_transcripts)


@pytest.fixture
def store() -> VideoStore:
    s = VideoStore(":memory:")
    try:
        yield s
    finally:
        s.close()


FIXED_NOW = "2026-07-22T00:00:00Z"


@pytest.fixture
def fixed_now():
    return lambda: FIXED_NOW
