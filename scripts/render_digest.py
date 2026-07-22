#!/usr/bin/env python3
"""Render the HTML "Reader's Digest" from a reconciliation run's deltas (ticket #10).

This is the pipeline's final step and its primary output surface. It consumes the typed
:class:`~kb.reconcile.deltas.Deltas` a run emits (here, the committed sample under
``fixtures/reconcile-sample/evals/``) together with the current KB positions, and writes a
single self-contained HTML briefing to ``digests/YYYY-MM-DD-<topic>.html``.

No live model or network is involved — rendering is pure and free, so the digest can be
produced on *every* run (spec: never an empty file). The run ``date`` is passed in, not
read from the wall clock, so the output path and contents are deterministic.

    python scripts/render_digest.py                 # write digests/<date>-evals.html
    python scripts/render_digest.py --date 2025-10-15
    python scripts/render_digest.py --fixtures       # also refresh the committed eyeball samples
"""

from __future__ import annotations

import argparse
import datetime as dt
import json

from kb.config import DIGESTS_DIR, FIXTURES_DIR
from kb.digest import write_digest
from kb.reconcile import Deltas, Position

SAMPLE_DIR = FIXTURES_DIR / "reconcile-sample" / "evals"
SAMPLE_OUT = FIXTURES_DIR / "digest-sample"

# The sample run's dates (matching the illustrative demo batch in scripts/run_reconcile.py).
RUN_DATE = dt.date(2025, 10, 15)
PREV_DATE = dt.date(2025, 9, 20)
# A later, quiet run: same KB, nothing new — exercises the never-empty no-changes page.
CALM_DATE = dt.date(2025, 10, 22)


def _load_deltas() -> Deltas:
    return Deltas.model_validate(json.loads((SAMPLE_DIR / "deltas.json").read_text("utf-8")))


def _load_positions() -> list[Position]:
    doc = json.loads((SAMPLE_DIR / "positions.json").read_text("utf-8"))
    return [Position.model_validate(p) for p in doc["positions"]]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", default="evals", help="Topic the digest covers.")
    parser.add_argument("--date", default=RUN_DATE.isoformat(), help="Run date (YYYY-MM-DD).")
    parser.add_argument("--out", default=str(DIGESTS_DIR), help="Output directory.")
    parser.add_argument(
        "--fixtures",
        action="store_true",
        help="Also (re)write the committed eyeball samples under fixtures/digest-sample/.",
    )
    args = parser.parse_args()

    deltas = _load_deltas()
    positions = _load_positions()

    path = write_digest(
        deltas,
        topic=args.topic,
        date=args.date,
        positions=positions,
        previous_date=PREV_DATE,
        out_dir=args.out,
    )
    print(f"Wrote digest ({deltas.total_changes()} changes) -> {path}")

    if args.fixtures:
        SAMPLE_OUT.mkdir(parents=True, exist_ok=True)
        changed = write_digest(
            deltas, topic=args.topic, date=RUN_DATE, positions=positions,
            previous_date=PREV_DATE, out_dir=SAMPLE_OUT,
        )
        calm = write_digest(
            Deltas(), topic=args.topic, date=CALM_DATE, positions=positions,
            previous_date=RUN_DATE, out_dir=SAMPLE_OUT,
        )
        print(f"Wrote sample (changed)    -> {changed}")
        print(f"Wrote sample (no-changes) -> {calm}")


if __name__ == "__main__":
    main()
