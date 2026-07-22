#!/usr/bin/env python3
"""Prototype the routing step on one extracted video (makes a live Haiku call).

Reads a committed extraction fixture (``fixtures/extractions/<id>.json`` — the Layer 2
output), runs :func:`kb.route.route_video` with the real Agent SDK client (Haiku, on the
subscription credit; escalating to Sonnet only if Haiku's output fails validation), and
writes two fixtures:

  * ``fixtures/routing/<id>.raw.txt``   — the model's verbatim response (the recorded
                                          return value of the LLM seam, for replay tests).
  * ``fixtures/routing/<id>.json``      — the validated RoutedVideo (the sample to react to).

The recorded raw response lets the test suite replay this exact routing with no live call.
Run manually, not in tests:

    python scripts/run_routing.py K8LLVi5Xrh8
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kb.config import FIXTURES_DIR, load_topics
from kb.extract import AgentSDKClient, ExtractedVideo
from kb.extract.llm import LLMClient
from kb.route import RoutedVideo, load_routing_config, route_video


class _RecordingClient:
    """Wraps a real LLMClient, saving each verbatim response as a replay fixture.

    Routing may make two calls (Haiku then a Sonnet escalation); the *last* response is
    the one the returned RoutedVideo was built from, so it is what we record for replay.
    """

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
    parser.add_argument("--model", default=None, help="Override the configured primary model")
    args = parser.parse_args()

    extraction_path = FIXTURES_DIR / "extractions" / f"{args.video_id}.json"
    extracted = ExtractedVideo.model_validate_json(extraction_path.read_text(encoding="utf-8"))

    config = load_routing_config()
    if args.model:
        config = config.model_copy(update={"model": args.model})

    raw_path = FIXTURES_DIR / "routing" / f"{args.video_id}.raw.txt"
    client = _RecordingClient(AgentSDKClient(), raw_path)

    routed: RoutedVideo = route_video(extracted, llm=client, config=config, topics=load_topics())

    out = FIXTURES_DIR / "routing" / f"{args.video_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(routed.model_dump_json(indent=2) + "\n", encoding="utf-8")

    multi = sum(1 for unit in routed.units if len(unit.topics) > 1)
    print(f"Routed {len(routed.units)} units ({multi} multi-topic) -> {out}")
    print(f"Video topics: {routed.topic_tags}")
    print(f"Recorded raw model output -> {raw_path}")


if __name__ == "__main__":
    main()
