#!/usr/bin/env python3
"""Prototype the extraction step on one real transcript (makes a live Sonnet call).

Reads a transcript fixture, runs :func:`kb.extract.extract_units` with the real Agent
SDK client (Sonnet, on the subscription credit), and writes two fixtures:

  * ``fixtures/llm/<id>.raw.txt``        — the model's verbatim response (the recorded
                                           return value of the LLM seam).
  * ``fixtures/extractions/<id>.json``   — the validated ExtractedVideo (the sample to
                                           react to).

The recorded raw response lets the test suite replay this exact extraction with no live
call. Run manually, not in tests:

    python scripts/run_extraction.py K8LLVi5Xrh8
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kb.config import FIXTURES_DIR
from kb.extract import (
    AgentSDKClient,
    ExtractedVideo,
    TranscriptSegment,
    extract_units,
    load_extraction_config,
)
from kb.extract.llm import LLMClient


class _RecordingClient:
    """Wraps a real LLMClient, saving the verbatim response as a replay fixture."""

    def __init__(self, inner: LLMClient, raw_path: Path) -> None:
        self._inner = inner
        self._raw_path = raw_path

    def complete(self, *, system: str, prompt: str, model: str) -> str:
        raw = self._inner.complete(system=system, prompt=prompt, model=model)
        self._raw_path.parent.mkdir(parents=True, exist_ok=True)
        self._raw_path.write_text(raw, encoding="utf-8")
        return raw


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video_id")
    parser.add_argument("--model", default=None, help="Override the configured model")
    args = parser.parse_args()

    transcript_path = FIXTURES_DIR / "transcripts" / f"{args.video_id}.json"
    document = json.loads(transcript_path.read_text(encoding="utf-8"))
    segments = [TranscriptSegment.model_validate(seg) for seg in document["segments"]]

    config = load_extraction_config()
    if args.model:
        config = config.model_copy(update={"model": args.model})

    raw_path = FIXTURES_DIR / "llm" / f"{args.video_id}.raw.txt"
    client = _RecordingClient(AgentSDKClient(), raw_path)

    result: ExtractedVideo = extract_units(
        segments=segments,
        video_id=args.video_id,
        date=document["date"],
        llm=client,
        config=config,
    )

    out = FIXTURES_DIR / "extractions" / f"{args.video_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"Extracted {len(result.units)} units ({len(result.claims)} claims) -> {out}")
    print(f"Recorded raw model output -> {raw_path}")


if __name__ == "__main__":
    main()
