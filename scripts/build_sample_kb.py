#!/usr/bin/env python3
"""Build a sample ``evals`` position KB — the prototype artifact to react to (ticket #06).

This is the "prototype the data model to react to" deliverable: a concrete, on-disk KB
that exercises every part of the position model — the maturity ladder (open-question ->
emerging-trend -> converging), a status history that records *when* each transition
happened, and a contested position that keeps *both* stances quoted with source + date.

It is **deterministic and makes no LLM call**. Real sources are the genuine units from
the one ingested video (``fixtures/extractions/K8LLVi5Xrh8.json`` — real quotes, real
unit ids, real 2025-05-11 date), loaded and projected via ``PositionSource.from_unit``.
Because a single video yields only single-source positions, a few **illustrative** cross-
video sources (video ids prefixed ``demo-``, never attributed to a named person) are
added to show the ladder climbing and a genuine disagreement. Deciding which real units
actually support or oppose which position across videos is the reconciliation engine's
job (ticket #08); here it is hand-assembled purely to give the model shape.

Run it to (re)generate ``fixtures/sample-kb/evals/positions.json`` + ``positions.md``:

    python scripts/build_sample_kb.py
"""

from __future__ import annotations

import datetime as dt
import json

from kb.config import FIXTURES_DIR
from kb.extract import Unit
from kb.reconcile import Alignment, KBStore, Maturity, PositionSource

REAL_VIDEO_ID = "K8LLVi5Xrh8"

# The illustrative demo KB is a committed fixture (an artifact to react to), not pipeline
# output — it lives under fixtures/ so kb-data/ carries only the pipeline's own real run.
SAMPLE_KB_DIR = FIXTURES_DIR / "sample-kb"


def _run_time(day: dt.date) -> dt.datetime:
    """A deterministic run timestamp for a source's date (09:00, no wall clock)."""
    return dt.datetime(day.year, day.month, day.day, 9, 0)


def _load_real_units() -> dict[str, tuple[Unit, str, dt.date]]:
    """Load the committed real extraction, keyed by unit id -> (unit, video_id, date)."""

    data = json.loads((FIXTURES_DIR / "extractions" / f"{REAL_VIDEO_ID}.json").read_text("utf-8"))
    video_id = data["video_id"]
    date = dt.date.fromisoformat(data["date"])
    return {u["unit_id"]: (Unit.model_validate(u), video_id, date) for u in data["units"]}


def _demo_source(
    *,
    unit_id: str,
    video_id: str,
    date: str,
    alignment: str,
    stance: str,
    quote: str,
    statement: str,
) -> PositionSource:
    """An illustrative source (loudly non-real: ``demo-`` video id)."""

    return PositionSource(
        unit_id=unit_id,
        video_id=video_id,
        date=date,
        alignment=alignment,
        stance=stance,
        quote=quote,
        statement=statement,
    )


def build() -> KBStore:
    real = _load_real_units()

    def real_source(unit_id: str, alignment: str = "supporting") -> PositionSource:
        unit, video_id, date = real[unit_id]
        return PositionSource.from_unit(unit, video_id=video_id, date=date, alignment=alignment)

    store = KBStore("evals", root=SAMPLE_KB_DIR)

    # -- evals-0001: converging (real anchor + two illustrative later sources) --------
    d1 = dt.date(2025, 5, 11)
    p1 = store.create_position(
        statement="Evaluating an LLM system is different from evaluating an LLM model — you must "
        "evaluate your own system on the task it is meant to solve, not just the base model.",
        at=_run_time(d1),
        first_source=real_source("K8LLVi5Xrh8#0"),
        reason="first stated in the ingested evals talk",
    )
    p1.add_source(real_source("K8LLVi5Xrh8#2"), at=_run_time(d1))
    s2 = dt.date(2025, 7, 8)
    p1.add_source(
        _demo_source(
            unit_id="demo-eval-talk-02#4", video_id="demo-eval-talk-02", date=s2.isoformat(),
            alignment="supporting", stance="affirms",
            quote="[illustrative] benchmarks tell you about the model, evals tell you about your product",
            statement="[illustrative] System-level evaluation matters more than model benchmarks.",
        ),
        at=_run_time(s2),
    )
    p1.record_transition(Maturity.emerging_trend, at=_run_time(s2), reason="a second, independent voice agreed",
                         trigger_unit_id="demo-eval-talk-02#4")
    s3 = dt.date(2025, 9, 20)
    p1.add_source(
        _demo_source(
            unit_id="demo-eval-talk-03#7", video_id="demo-eval-talk-03", date=s3.isoformat(),
            alignment="supporting", stance="affirms",
            quote="[illustrative] stop shipping on vibes; measure the system you actually built",
            statement="[illustrative] Teams should evaluate their assembled system, not the raw model.",
        ),
        at=_run_time(s3),
    )
    p1.record_transition(Maturity.converging, at=_run_time(s3),
                         reason="three independent sources agreeing over >3 months, no contest",
                         trigger_unit_id="demo-eval-talk-03#7")

    # -- evals-0002: emerging trend (real anchor + one illustrative source) -----------
    p2 = store.create_position(
        statement="For a specialized system (e.g. RAG), build your own evaluation rather than "
        "reaching for an off-the-shelf public benchmark.",
        at=_run_time(d1),
        first_source=real_source("K8LLVi5Xrh8#3"),
        reason="stated in the ingested evals talk",
    )
    p2.add_source(
        _demo_source(
            unit_id="demo-eval-talk-02#9", video_id="demo-eval-talk-02", date=s2.isoformat(),
            alignment="supporting", stance="affirms",
            quote="[illustrative] a generic RAG leaderboard won't tell you if YOUR retrieval works",
            statement="[illustrative] Custom evals beat generic benchmarks for retrieval systems.",
        ),
        at=_run_time(s2),
    )
    p2.record_transition(Maturity.emerging_trend, at=_run_time(s2),
                         reason="a second source agreed within three months",
                         trigger_unit_id="demo-eval-talk-02#9")

    # -- evals-0003: open question (a single real source) -----------------------------
    store.create_position(
        statement="Manual evaluation is the right place to start; automation scales human "
        "judgment but does not replace it.",
        at=_run_time(d1),
        first_source=real_source("K8LLVi5Xrh8#16"),
        reason="single source so far — genuinely open",
    ).add_source(real_source("K8LLVi5Xrh8#19"), at=_run_time(d1))

    # -- evals-0004: contested (real support + one illustrative dissent) --------------
    p4 = store.create_position(
        statement="LLM-as-a-judge is reliable enough to depend on for evaluating LLM outputs.",
        at=_run_time(d1),
        first_source=real_source("K8LLVi5Xrh8#28"),
        reason="stated (with a caveat) in the ingested evals talk",
    )
    s4 = dt.date(2025, 8, 3)
    p4.add_source(
        _demo_source(
            unit_id="demo-critic-05#2", video_id="demo-critic-05", date=s4.isoformat(),
            alignment="opposing", stance="denies",
            quote="[illustrative] an uncalibrated LLM judge is confidently wrong; don't trust it raw",
            statement="[illustrative] LLM-as-a-judge is NOT reliable without heavy calibration.",
        ),
        at=_run_time(s4),
    )
    p4.record_transition(Maturity.contested, at=_run_time(s4),
                         reason="a credible dissent — both stances now kept side by side",
                         trigger_unit_id="demo-critic-05#2")

    return store


def main() -> None:
    store = build()
    store.save()
    contested = sum(1 for p in store if p.is_contested)
    print(f"Wrote {len(store)} positions ({contested} contested) for topic {store.topic!r}")
    print(f"  canonical: {store.json_path}")
    print(f"  rendered:  {store.md_path}")


if __name__ == "__main__":
    main()
