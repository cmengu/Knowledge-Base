#!/usr/bin/env python3
"""Prototype a full reconciliation run on the seed KB (real retriever; Opus optional).

Wires the whole two-stage matcher end to end against the committed ``evals`` seed KB:

  stage 1 — the REAL LocalVectorRetriever (local BGE-M3 embeddings + LanceDB), and
  stage 2 — the REAL OpusAdjudicator on the subscription (``--live``), or a dry run that
            stops after retrieval (default) so stage 1 can be validated without any LLM call.

A small, clearly-illustrative batch (``demo-`` video ids) is reconciled to exercise all
three outcomes — confirming, novel, adversarial. With ``--live`` the resulting typed
:class:`~kb.reconcile.deltas.Deltas` and the updated KB are written under
``fixtures/reconcile-sample/`` as a sample for the digest (ticket #10) to render. The seed
KB on disk is never modified.

    python scripts/run_reconcile.py            # dry: stage-1 retrieval only, no LLM
    python scripts/run_reconcile.py --live     # full: real Opus adjudication (few calls)
"""

from __future__ import annotations

import argparse
import datetime as dt

from kb.config import FIXTURES_DIR, KB_DATA_DIR
from kb.extract import AgentSDKClient, Unit
from kb.reconcile import (
    AdjudicationConfig,
    IncomingUnit,
    KBStore,
    LocalVectorRetriever,
    OpusAdjudicator,
    load_reconcile_config,
    reconcile,
)

RUN_TIME = dt.datetime(2025, 10, 15, 9, 0)
SAMPLE_ROOT = FIXTURES_DIR / "reconcile-sample"


def _demo_unit(index: int, text: str, raw_quote: str, stance: str) -> IncomingUnit:
    """One illustrative incoming unit from a fictional new talk (loudly ``demo-``)."""
    return IncomingUnit(
        unit=Unit(
            type="claim", text=text, raw_quote=raw_quote, timestamp=float(60 * index),
            stance=stance, unit_id=f"demo-eval-talk-06#{index}",
        ),
        video_id="demo-eval-talk-06",
        date="2025-10-15",
    )


def build_batch() -> list[IncomingUnit]:
    return [
        # expected: confirming evals-0001 (system eval, not model eval)
        _demo_unit(
            0,
            "You have to evaluate the whole system you assembled, not just the raw base model.",
            "[illustrative] test the system you actually built, not the model in isolation",
            "affirms",
        ),
        # expected: novel (no existing position about version-controlling evals)
        _demo_unit(
            1,
            "Your eval datasets should be version-controlled alongside your application code.",
            "[illustrative] keep your evals in git next to the code they test",
            "affirms",
        ),
        # expected: adversarial vs evals-0003 (manual-first)
        _demo_unit(
            2,
            "Skip manual evaluation entirely and automate grading from day one.",
            "[illustrative] don't waste time reading outputs by hand — automate from the start",
            "denies",
        ),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Run the real Opus adjudicator.")
    parser.add_argument("--model", default=None, help="Override the adjudicator model.")
    args = parser.parse_args()

    config = load_reconcile_config()
    store = KBStore.load("evals", root=KB_DATA_DIR)
    batch = build_batch()
    retriever = LocalVectorRetriever()

    print(f"Seed KB: {len(store)} positions. Reconciling {len(batch)} illustrative units.\n")

    # Stage 1 preview (always) — proves the real BGE-M3 + LanceDB retriever works.
    for inc in batch:
        candidates = retriever.top_k(
            query_text=inc.unit.text, positions=store.positions(),
            k=config.top_k, min_score=config.min_score,
        )
        print(f"[stage 1] {inc.unit_id}: {inc.unit.text!r}")
        for c in candidates:
            print(f"    -> {c.position.position_id}  score={c.score:.3f}  {c.position.statement[:70]}…")
        if not candidates:
            print("    -> (no candidate cleared the floor — novel by construction)")
    print()

    if not args.live:
        print("Dry run complete (stage 1 only). Re-run with --live for full Opus adjudication.")
        return

    model = args.model or config.adjudicator_model
    adjudicator = OpusAdjudicator(AgentSDKClient(), config=AdjudicationConfig(model=model))
    updated, deltas = reconcile(
        batch, store, retriever=retriever, adjudicator=adjudicator, now=RUN_TIME, config=config
    )

    print("=== DELTAS ===")
    print(f"  net-new:            {len(deltas.net_new)}")
    for d in deltas.net_new:
        print(f"    + {d.position_id}: {d.statement}")
    print(f"  newly confirmed:    {len(deltas.newly_confirmed)}")
    for d in deltas.newly_confirmed:
        print(f"    ~ {d.position_id} ({d.kind.value}): {d.citation.statement}")
    print(f"  newly contested:    {len(deltas.newly_contested)}")
    for d in deltas.newly_contested:
        r = d.reconciliation
        print(f"    ! {d.position_id} [{r.type.value}, reconciled={r.reconciled}]")
        print(f"        supporting: \"{d.supporting.quote}\" — {d.supporting.video_id} · {d.supporting.date}")
        print(f"        opposing:   \"{d.opposing.quote}\" — {d.opposing.video_id} · {d.opposing.date}")
    print(f"  maturity moves:     {len(deltas.maturity_transitions)}")
    for d in deltas.maturity_transitions:
        print(f"    → {d.position_id}: {d.from_maturity} → {d.to_maturity} ({d.reason})")

    # Persist the run as a sample for the digest (#10); the seed KB is left untouched.
    sample = KBStore("evals", root=SAMPLE_ROOT, positions=updated.positions())
    sample.save()
    deltas_path = SAMPLE_ROOT / "evals" / "deltas.json"
    deltas_path.write_text(deltas.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote sample KB -> {sample.json_path}")
    print(f"Wrote sample deltas -> {deltas_path}")


if __name__ == "__main__":
    main()
