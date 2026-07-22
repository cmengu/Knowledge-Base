"""Pytest fixtures. Shared doubles and loaders live in ``tests/helpers.py``."""

from __future__ import annotations

import pytest

from kb.extract import TranscriptSegment
from tests.helpers import FakeLLMClient, transcript_ids


@pytest.fixture
def fake_llm_factory():
    """Factory so a test can mint a FakeLLMClient with a chosen scripted response."""

    def _make(response: str = "", *, raises: Exception | None = None) -> FakeLLMClient:
        return FakeLLMClient(response, raises=raises)

    return _make


@pytest.fixture(params=transcript_ids())
def fixture_video_id(request) -> str:
    """Parametrizes over every committed transcript fixture (currently one)."""

    return request.param


@pytest.fixture
def sample_segments() -> list[TranscriptSegment]:
    """A short, hand-built transcript for extractor wiring tests."""

    return [
        TranscriptSegment(text="Public benchmarks measure general model skill.", start=12.0, duration=3.0),
        TranscriptSegment(text="But you must evaluate your own system on its real task.", start=15.0, duration=4.0),
    ]
