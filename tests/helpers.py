"""Test doubles and fixture loaders shared across the suite.

Every non-deterministic dependency is injected (spec Testing Decisions), so the whole
suite runs with scripted doubles and never makes a live network or LLM call:

* :class:`FakeLLMClient`   — the extraction/adjudication LLM seam.
* :class:`FakeRetriever`   — stage-1 candidate retrieval (no embedding model / LanceDB).
* :class:`FakeAdjudicator` — stage-2 judgment (no Opus), returning scripted verdicts.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from kb.config import FIXTURES_DIR
from kb.extract import TranscriptSegment
from kb.reconcile import Candidate, IncomingUnit, Position, Verdict


class FakeLLMClient:
    """A scripted :class:`~kb.extract.llm.LLMClient` for deterministic tests.

    Returns ``response`` for every ``complete`` call (or raises ``raises``), and records
    the call kwargs so tests can assert *what the caller sent* (model, prompt) without
    asserting prompt wording.
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
class FakeRetriever:
    """A scripted stage-1 :class:`~kb.reconcile.retrieval.CandidateRetriever`.

    Returns candidates without any embedding model or vector database. ``ids_by_text`` maps
    an incoming unit's query text to the candidate position ids to return; when a query is
    absent, ``default_ids`` decides (``None`` → every current position, ``[]`` → none). All
    calls are recorded so a test can assert the two-stage wiring — that the adjudicator was
    handed exactly what stage 1 retrieved.
    """

    def __init__(
        self,
        ids_by_text: dict[str, list[str]] | None = None,
        *,
        default_ids: list[str] | None = None,
        score: float = 0.9,
    ) -> None:
        self.ids_by_text = ids_by_text or {}
        self.default_ids = default_ids
        self.score = score
        self.calls: list[str] = []

    def top_k(
        self, *, query_text: str, positions: Sequence[Position], k: int, min_score: float
    ) -> list[Candidate]:
        self.calls.append(query_text)
        by_id = {p.position_id: p for p in positions}
        if query_text in self.ids_by_text:
            ids = self.ids_by_text[query_text]
        elif self.default_ids is not None:
            ids = self.default_ids
        else:
            ids = [p.position_id for p in positions]
        candidates = [Candidate(position=by_id[i], score=self.score) for i in ids if i in by_id]
        return candidates[:k]


class FakeAdjudicator:
    """A scripted stage-2 :class:`~kb.reconcile.adjudicator.Adjudicator`.

    Returns a pre-scripted :class:`~kb.reconcile.adjudicator.Verdict` per incoming unit
    (keyed by ``unit_id``), or a ``default`` (a verdict or a ``callable(unit, candidates)``)
    when none is scripted. Records each call as ``(unit_id, [candidate_ids])`` so tests can
    assert the adjudicator saw the retrieved candidates.
    """

    def __init__(
        self,
        verdicts_by_unit: dict[str, Verdict] | None = None,
        *,
        default=None,
    ) -> None:
        self.verdicts_by_unit = verdicts_by_unit or {}
        self.default = default
        self.calls: list[tuple[str, list[str]]] = []

    def adjudicate(self, *, unit: IncomingUnit, candidates: Sequence[Position]) -> Verdict:
        self.calls.append((unit.unit_id, [c.position_id for c in candidates]))
        if unit.unit_id in self.verdicts_by_unit:
            return self.verdicts_by_unit[unit.unit_id]
        if callable(self.default):
            return self.default(unit, candidates)
        if self.default is not None:
            return self.default
        raise AssertionError(f"FakeAdjudicator has no scripted verdict for {unit.unit_id!r}")


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
def adjudication_names() -> list[str]:
    directory = FIXTURES_DIR / "adjudications"
    if not directory.exists():
        return []
    return sorted(path.name[: -len(".raw.txt")] for path in directory.glob("*.raw.txt"))


def read_recorded_adjudication_raw(name: str) -> str:
    return (FIXTURES_DIR / "adjudications" / f"{name}.raw.txt").read_text(encoding="utf-8")


def load_recorded_verdict(name: str) -> dict:
    path = FIXTURES_DIR / "adjudications" / f"{name}.verdict.json"
    return json.loads(path.read_text(encoding="utf-8"))
