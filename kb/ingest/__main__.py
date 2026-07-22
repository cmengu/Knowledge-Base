"""CLI for Layer 1 ingest.

    python -m kb.ingest seed/evals.txt
    python -m kb.ingest seed/evals.txt --config config/ingest.yaml --db data/kb.sqlite3

Reads a file of YouTube URLs/ids, ingests each into SQLite, and prints a
per-entry report. Safe to re-run: known ids are skipped without any network
call. Runs on the local residential IP unless the Webshare proxy is enabled in
config.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..config import ConfigError, IngestConfig, load_config
from ..store import VideoStore
from . import IngestReport, ingest
from .fetchers import TranscriptApiFetcher, YtDlpMetadataFetcher
from .urls import read_seed_file


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m kb.ingest",
        description="Ingest YouTube videos into the knowledge-base SQLite store.",
    )
    parser.add_argument(
        "seed_file",
        help="path to a file of YouTube URLs/ids (one per line; # comments ok)",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="path to ingest config YAML (default: config/ingest.yaml if present)",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="SQLite path (overrides 'database' in config)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="print only the summary line, not per-entry outcomes",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero if any entry failed",
    )
    return parser


def _render(report: IngestReport, quiet: bool) -> None:
    if not quiet:
        for outcome in report.outcomes:
            marker = {"ingested": "+", "skipped": "=", "failed": "!"}.get(
                outcome.status, "?"
            )
            ident = outcome.video_id or outcome.raw
            detail = f" — {outcome.reason}" if outcome.reason else ""
            print(f"  [{marker}] {outcome.status:8} {ident}{detail}")
    print(report.summary())


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        config: IngestConfig = load_config(args.config)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    seed_path = Path(args.seed_file)
    if not seed_path.exists():
        print(f"seed file not found: {seed_path}", file=sys.stderr)
        return 2

    entries = read_seed_file(seed_path)
    if not entries:
        print(f"no URLs found in {seed_path}", file=sys.stderr)
        return 0

    database = args.db or config.database
    metadata_fetcher = YtDlpMetadataFetcher(proxy_url=config.metadata_proxy_url)
    transcript_fetcher = TranscriptApiFetcher(
        languages=config.languages, proxy=config.proxy
    )

    if config.proxy.enabled:
        print("proxy: Webshare rotating-residential proxy ENABLED", file=sys.stderr)

    with VideoStore(database) as store:
        report = ingest(
            entries,
            store=store,
            metadata_fetcher=metadata_fetcher,
            transcript_fetcher=transcript_fetcher,
        )

    _render(report, quiet=args.quiet)

    if args.strict and report.failed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
