"""Test doubles and fixture loaders shared across the suite.

The LLM is an injected dependency (spec Testing Decisions): :class:`FakeLLMClient` is the
scripted double used everywhere so no test makes a live network or LLM call.
"""

from __future__ import annotations

import json

from kb.config import FIXTURES_DIR
from kb.extract import TranscriptSegment


class FakeLLMClient:
    """A scripted :class:`~kb.extract.llm.LLMClient` for deterministic tests.

    Returns ``response`` for every ``complete`` call (or raises ``raises``), and records
    the call kwargs so tests can assert *what the extractor sent* (model, transcript)
    without asserting prompt wording.
    """

    def __init__(self, response: str = "", *, raises: Exception | None = None) -> None:
        self.response = response
        self.raises = raises
        self.calls: list[dict[str, str]] = []

    def complete(self, *, system: str, prompt: str, model: str) -> str:
        self.calls.append({"system": system, "prompt": prompt, "model": model})
        if self.raises is not None:
            raise self.raises
        return self.response


class ScriptedLLMClient:
    """A :class:`~kb.extract.llm.LLMClient` that returns a *queue* of responses in order.

    Each item is either a ``str`` (returned) or an ``Exception`` (raised) on the
    corresponding call. This drives multi-call behaviors that :class:`FakeLLMClient`
    (one response for all calls) cannot express — chiefly the routing Haiku->Sonnet
    escalation, where call 1 returns bad output and call 2 returns good output. Every
    call's kwargs are recorded so tests can assert *which model* each attempt used.
    """

    def __init__(self, responses: list) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, str]] = []

    def complete(self, *, system: str, prompt: str, model: str) -> str:
        self.calls.append({"system": system, "prompt": prompt, "model": model})
        if not self._responses:
            raise AssertionError("ScriptedLLMClient exhausted: more calls than scripted responses")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    @property
    def models(self) -> list[str]:
        """The model requested on each call, in order (e.g. ``["haiku", "sonnet"]``)."""
        return [call["model"] for call in self.calls]


def transcript_ids() -> list[str]:
    return sorted(path.stem for path in (FIXTURES_DIR / "transcripts").glob("*.json"))


def load_transcript_document(video_id: str) -> dict:
    path = FIXTURES_DIR / "transcripts" / f"{video_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_segments(video_id: str) -> list[TranscriptSegment]:
    document = load_transcript_document(video_id)
    return [TranscriptSegment.model_validate(seg) for seg in document["segments"]]


def read_recorded_raw(video_id: str) -> str:
    return (FIXTURES_DIR / "llm" / f"{video_id}.raw.txt").read_text(encoding="utf-8")


def load_recorded_extraction(video_id: str) -> dict:
    path = FIXTURES_DIR / "extractions" / f"{video_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


# --- routing fixtures (Layer 3, ticket #07) --------------------------------


def routing_ids() -> list[str]:
    directory = FIXTURES_DIR / "routing"
    if not directory.exists():
        return []
    return sorted(path.stem for path in directory.glob("*.json"))


def load_recorded_routing(video_id: str) -> dict:
    path = FIXTURES_DIR / "routing" / f"{video_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def read_recorded_routing_raw(video_id: str) -> str:
    return (FIXTURES_DIR / "routing" / f"{video_id}.raw.txt").read_text(encoding="utf-8")
