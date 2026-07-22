#!/usr/bin/env python3
"""Run the first real end-to-end vertical slice of the YouTube-KB pipeline.

Chains all five layers over the committed ``evals`` seed set on the local residential IP,
using the real Agent SDK on the subscription credit and the real BGE-M3 + LanceDB
retriever — no fixtures, no fakes:

    ingest(seed/evals.txt)                     # Layer 1: yt-dlp + youtube-transcript-api
      -> extract (Agent SDK, Sonnet)           # Layer 2: transcript -> validated units
      -> route  (Agent SDK, Haiku->Sonnet)     # Layer 3: units -> topics
      -> filter to the `evals` slice           #          slice gate + claims only
      -> reconcile (BGE-M3 + LanceDB stage 1,  # Layers 4-5: two-stage matcher
                    Opus adjudicator stage 2)
      -> apply maturity (config-driven)        # re-flag the whole KB every batch
      -> render digest -> digests/<date>-evals.html   # the Reader's Digest

This is *glue*, not new logic: every step calls the existing package API. The run date is
injected explicitly (never the wall clock), matching the package convention, so the KB
timestamps and the digest filename are deterministic.

    python scripts/run_slice.py
    python scripts/run_slice.py --seed seed/evals.txt --date 2026-07-22

Videos without an English transcript fail ingest gracefully (recorded, never fatal); a
video whose extraction or routing raises is skipped and the batch continues.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import traceback

from kb.config import DIGESTS_DIR, KB_DATA_DIR, load_topics, load_config
from kb.extract import (
    AgentSDKClient,
    ExtractedVideo,
    TranscriptSegment,
    UnitType,
    extract_units,
    load_extraction_config,
)
from kb.ingest import ingest
from kb.ingest.fetchers import TranscriptApiFetcher, YtDlpMetadataFetcher
from kb.ingest.urls import read_seed_file
from kb.reconcile import (
    AdjudicationConfig,
    IncomingUnit,
    KBStore,
    LocalVectorRetriever,
    OpusAdjudicator,
    apply_maturity_batch,
    load_maturity_config,
    load_reconcile_config,
    reconcile,
)
from kb.route import load_routing_config, route_video, units_for_downstream
from kb.digest import write_digest
from kb.store import VideoStore

# Explicit model ids for this run (the config carries aliases; we pin the exact ids the
# environment research locked so the run is unambiguous about what answered each call).
EXTRACT_MODEL = "claude-sonnet-5"
ROUTE_MODEL = "claude-haiku-4-5-20251001"
ROUTE_FALLBACK_MODEL = "claude-sonnet-5"
ADJUDICATOR_MODEL = "claude-opus-4-8"

SLICE_TOPIC = "evals"


def _log(msg: str) -> None:
    print(msg, flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", default="seed/evals.txt", help="Seed file of YouTube URLs.")
    parser.add_argument("--date", default="2026-07-22", help="Run date (YYYY-MM-DD), injected.")
    parser.add_argument("--db", default="data/knowledge_base.sqlite3", help="SQLite path.")
    parser.add_argument(
        "--lancedb", default="data/lancedb", help="Persistent LanceDB vector-cache dir."
    )
    args = parser.parse_args()

    run_date = dt.date.fromisoformat(args.date)
    run_time = dt.datetime(run_date.year, run_date.month, run_date.day, 9, 0)

    topics = load_topics()
    ingest_cfg = load_config()
    extract_cfg = load_extraction_config().model_copy(update={"model": EXTRACT_MODEL})
    route_cfg = load_routing_config().model_copy(
        update={"model": ROUTE_MODEL, "fallback_model": ROUTE_FALLBACK_MODEL}
    )
    reconcile_cfg = load_reconcile_config()
    maturity_cfg = load_maturity_config()

    llm = AgentSDKClient()

    # ---- Layer 1: ingest --------------------------------------------------
    entries = read_seed_file(args.seed)
    _log(f"[ingest] {len(entries)} seed entries from {args.seed} (local residential IP, no proxy)")
    with VideoStore(args.db) as store:
        report = ingest(
            entries,
            store=store,
            metadata_fetcher=YtDlpMetadataFetcher(proxy_url=ingest_cfg.metadata_proxy_url),
            transcript_fetcher=TranscriptApiFetcher(
                languages=ingest_cfg.languages, proxy=ingest_cfg.proxy
            ),
        )
        for o in report.outcomes:
            mark = {"ingested": "+", "skipped": "=", "failed": "!"}.get(o.status, "?")
            detail = f" — {o.reason}" if o.reason else ""
            _log(f"  [{mark}] {o.status:8} {o.video_id or o.raw}{detail}")
        _log(f"[ingest] {report.summary()}")

        records = store.all()

    # ---- Layers 2+3: extract then route, per video ------------------------
    incoming: list[IncomingUnit] = []
    total_units = 0
    evals_units = 0            # every evals-routed unit (claim + content)
    evals_claims = 0          # evals-routed claims — the ones reconciled
    extract_route_failures: list[tuple[str, str]] = []
    per_video: list[tuple[str, int, int]] = []  # (video_id, units, evals_claims)

    for rec in records:
        try:
            segments = [TranscriptSegment.model_validate(seg) for seg in rec.transcript]
            extracted: ExtractedVideo = extract_units(
                segments=segments, video_id=rec.id, date=rec.date, llm=llm, config=extract_cfg
            )
            _log(f"[extract] {rec.id}: {len(extracted.units)} units "
                 f"({len(extracted.claims)} claims) via {EXTRACT_MODEL}")
            total_units += len(extracted.units)

            routed = route_video(extracted, llm=llm, config=route_cfg, topics=topics)
            slice_units = units_for_downstream(routed, slice_topic=SLICE_TOPIC)
            claims = [ru for ru in slice_units if ru.unit.type is UnitType.claim]
            evals_units += len(slice_units)
            evals_claims += len(claims)
            per_video.append((rec.id, len(extracted.units), len(claims)))
            _log(f"[route]   {rec.id}: video_topics={routed.topic_tags}; "
                 f"{len(slice_units)} evals units ({len(claims)} claims) -> downstream")

            for ru in claims:
                incoming.append(
                    IncomingUnit(unit=ru.unit, video_id=routed.video_id, date=routed.date)
                )
        except Exception as exc:  # one bad video never aborts the batch
            extract_route_failures.append((rec.id, f"{type(exc).__name__}: {exc}"))
            _log(f"[skip]    {rec.id}: extract/route failed — {type(exc).__name__}: {exc}")
            traceback.print_exc()

    _log(f"[reconcile] {len(incoming)} incoming evals claims across "
         f"{len(per_video)} videos -> two-stage matcher")

    # ---- Layers 4+5: reconcile against the (empty) evals KB ---------------
    kb = KBStore.load("evals", root=KB_DATA_DIR)
    before = len(kb)
    retriever = LocalVectorRetriever(db_path=args.lancedb)
    adjudicator = OpusAdjudicator(llm, config=AdjudicationConfig(model=ADJUDICATOR_MODEL))

    updated, deltas = reconcile(
        incoming,
        kb,
        retriever=retriever,
        adjudicator=adjudicator,
        now=run_time,
        config=reconcile_cfg,
        maturity_config=maturity_cfg,
    )

    # ---- re-flag the whole KB every batch (idempotent after the engine's per-unit reflag)
    batch_moves = apply_maturity_batch(updated.positions(), maturity_cfg, run_time)
    _log(f"[maturity] batch reflag over {len(updated)} positions: {len(batch_moves)} extra moves")

    updated.save()
    _log(f"[kb] wrote {len(updated)} positions (was {before}) -> {updated.json_path}")

    # ---- digest -----------------------------------------------------------
    path = write_digest(
        deltas,
        topic=SLICE_TOPIC,
        date=args.date,
        positions=updated,
        previous_date=None,
        out_dir=DIGESTS_DIR,
    )
    _log(f"[digest] {deltas.total_changes()} changes -> {path}")

    # ---- summary ----------------------------------------------------------
    maturity_states: dict[str, int] = {}
    for p in updated.positions():
        maturity_states[p.maturity.value] = maturity_states.get(p.maturity.value, 0) + 1

    _log("\n===== SLICE SUMMARY =====")
    _log(f"videos ingested : {len(report.ingested)}")
    _log(f"videos skipped  : {len(report.skipped)}")
    _log(f"videos failed   : {len(report.failed)}")
    for o in report.failed:
        _log(f"    - {o.video_id or o.raw}: {o.reason}")
    _log(f"extract/route failures: {len(extract_route_failures)}")
    for vid, why in extract_route_failures:
        _log(f"    - {vid}: {why}")
    _log(f"total units extracted : {total_units}")
    _log(f"evals-routed units    : {evals_units} ({evals_claims} claims reconciled)")
    _log(f"positions net-new     : {len(deltas.net_new)}")
    _log(f"positions confirmed   : {len(deltas.newly_confirmed)}")
    _log(f"positions contested   : {len(deltas.newly_contested)}")
    _log(f"maturity transitions  : {len(deltas.maturity_transitions)}")
    _log(f"final KB positions    : {len(updated)}")
    _log(f"maturity states       : {maturity_states}")
    _log(f"digest                : {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
