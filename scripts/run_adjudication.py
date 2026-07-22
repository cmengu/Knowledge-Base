#!/usr/bin/env python3
"""Prototype the stage-2 adjudicator on one fixture pair (makes ONE live Opus call).

Builds a single (incoming unit, candidate positions) pair — an unambiguous *adversarial*
case, the guardrail's hardest path — runs the real :class:`~kb.reconcile.adjudicator.
OpusAdjudicator` against it on the subscription (``model=opus``), and records three
fixtures under ``fixtures/adjudications/``:

  * ``<name>.input.json``   — the pair the adjudicator judged (so the replay is rebuildable).
  * ``<name>.raw.txt``      — Opus's verbatim response (the recorded LLM seam return value).
  * ``<name>.verdict.json`` — the parsed, validated :class:`~kb.reconcile.adjudicator.Verdict`.

The recorded raw response lets the test suite replay this exact adjudication with no live
call (test_adjudicator_fixture.py). Run manually, not in tests:

    python scripts/run_adjudication.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kb.config import FIXTURES_DIR
from kb.extract import AgentSDKClient, Unit
from kb.extract.llm import LLMClient
from kb.reconcile import IncomingUnit, Position, PositionSource
from kb.reconcile.adjudicator import AdjudicationConfig, OpusAdjudicator, build_adjudication_prompt

RUN_TIME = __import__("datetime").datetime(2025, 8, 3, 9, 0)


def build_smoke_pair() -> tuple[str, IncomingUnit, list[Position]]:
    """A deterministic, unambiguous adversarial pair for the smoke call.

    Candidate: a supporting-only position that LLM-as-a-judge is reliable enough to depend
    on (anchored on the real K8LLVi5Xrh8 unit). Incoming: a flat denial from another voice.
    The correct verdict is adversarial + unreconciled — the guardrail's core case.
    """

    candidate = Position.create(
        position_id="evals-0004",
        topic="evals",
        statement="LLM-as-a-judge is reliable enough to depend on for evaluating LLM outputs.",
        at=RUN_TIME,
        first_source=PositionSource(
            unit_id="K8LLVi5Xrh8#28",
            video_id="K8LLVi5Xrh8",
            date="2025-05-11",
            alignment="supporting",
            stance="affirms",
            quote="And it works surprisingly well. Just remember that your LLM judge is like a "
            "small machine learning project in itself and it also requires some tuning and evaluation.",
            statement="LLM-as-a-judge works surprisingly well, but the judge itself is like a "
            "small ML project that requires its own tuning and evaluation.",
        ),
        reason="stated in the ingested evals talk",
    )

    incoming = IncomingUnit(
        unit=Unit(
            type="claim",
            text="LLM-as-a-judge is not reliable and you should not depend on it to evaluate outputs.",
            raw_quote="Do not trust an LLM to grade another LLM — the judge is unreliable and you "
            "should not depend on it.",
            timestamp=142.0,
            stance="denies",
            evidence_offered=["cites judge-calibration failures"],
            unit_id="demo-critic-05#2",
        ),
        video_id="demo-critic-05",
        date="2025-08-03",
    )
    return "llm-judge-adversarial", incoming, [candidate]


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
    parser.add_argument("--model", default="opus", help="Adjudicator model (default: opus)")
    args = parser.parse_args()

    name, incoming, candidates = build_smoke_pair()
    out_dir = FIXTURES_DIR / "adjudications"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Persist the input pair so the replay test can rebuild the exact adjudication.
    input_doc = {
        "name": name,
        "incoming": {
            "unit": incoming.unit.model_dump(mode="json"),
            "video_id": incoming.video_id,
            "date": incoming.date.isoformat(),
        },
        "candidates": [p.model_dump(mode="json") for p in candidates],
    }
    (out_dir / f"{name}.input.json").write_text(
        json.dumps(input_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    # Sanity-print the prompt the model will see (guardrail visible).
    _, user = build_adjudication_prompt(incoming, candidates)
    print(f"Adjudicating {name!r} with model={args.model!r} …")
    print("--- user prompt ---\n" + user + "\n-------------------")

    raw_path = out_dir / f"{name}.raw.txt"
    client = _RecordingClient(AgentSDKClient(), raw_path)
    adjudicator = OpusAdjudicator(client, config=AdjudicationConfig(model=args.model))
    verdict = adjudicator.adjudicate(unit=incoming, candidates=candidates)

    (out_dir / f"{name}.verdict.json").write_text(
        verdict.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    print("\nVerdict:")
    print(f"  classification: {verdict.classification.value}")
    print(f"  target: {verdict.target_position_id}")
    if verdict.reconciliation:
        r = verdict.reconciliation
        print(f"  reconciliation: {r.type.value}, reconciled={r.reconciled}")
        print(f"  explanation: {r.explanation}")
    print(f"  rationale: {verdict.rationale}")
    print(f"\nRecorded raw -> {raw_path}")


if __name__ == "__main__":
    main()
