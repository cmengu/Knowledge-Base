"""Layer 1 — ingest.

Turn curator-supplied YouTube URLs into one persisted :class:`VideoRecord`
each. No LLM is involved. The single public seam is :func:`ingest`, whose two
network dependencies (metadata + transcript) are injected so the whole layer is
testable offline with recorded fixtures.

Contract enforced here:
  * video id is the dedup key — a known id is skipped **before** any network
    call (a true re-run no-op);
  * every persisted record carries the mandatory upload timestamp — a video
    without one is failed, never stored;
  * a failed video (bad metadata, missing timestamp, no transcript) is not
    persisted, so a later re-run retries it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Iterable

from ..models import VideoRecord
from ..store import VideoStore
from .errors import MetadataUnavailableError, TranscriptUnavailableError
from .fetchers import (
    MetadataFetcher,
    TranscriptFetcher,
    VideoMetadata,
    YtDlpMetadataFetcher,
    TranscriptApiFetcher,
)
from .urls import canonical_watch_url, parse_video_id, read_seed_file

__all__ = [
    "ingest",
    "IngestOutcome",
    "IngestReport",
    "MetadataFetcher",
    "TranscriptFetcher",
    "VideoMetadata",
    "YtDlpMetadataFetcher",
    "TranscriptApiFetcher",
    "parse_video_id",
    "read_seed_file",
]

# Outcome statuses.
INGESTED = "ingested"
SKIPPED = "skipped"
FAILED = "failed"


@dataclass(frozen=True)
class IngestOutcome:
    """What happened to one input entry."""

    raw: str
    video_id: str | None
    status: str  # INGESTED | SKIPPED | FAILED
    reason: str | None = None
    record: VideoRecord | None = None


@dataclass
class IngestReport:
    """Aggregate result of an ingest run."""

    outcomes: list[IngestOutcome] = field(default_factory=list)

    @property
    def ingested(self) -> list[IngestOutcome]:
        return [o for o in self.outcomes if o.status == INGESTED]

    @property
    def skipped(self) -> list[IngestOutcome]:
        return [o for o in self.outcomes if o.status == SKIPPED]

    @property
    def failed(self) -> list[IngestOutcome]:
        return [o for o in self.outcomes if o.status == FAILED]

    def summary(self) -> str:
        return (
            f"{len(self.ingested)} ingested, "
            f"{len(self.skipped)} skipped, "
            f"{len(self.failed)} failed "
            f"({len(self.outcomes)} total)"
        )


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def ingest(
    entries: Iterable[str],
    *,
    store: VideoStore,
    metadata_fetcher: MetadataFetcher,
    transcript_fetcher: TranscriptFetcher,
    now: Callable[[], str] = _utcnow_iso,
) -> IngestReport:
    """Ingest ``entries`` (URLs or bare ids) into ``store``.

    Deterministic given its injected dependencies. Per-entry failures are
    captured in the returned :class:`IngestReport` rather than raised, so one
    bad video never aborts the batch.
    """
    report = IngestReport()

    for raw in entries:
        video_id = parse_video_id(raw)
        if video_id is None:
            report.outcomes.append(
                IngestOutcome(
                    raw=raw,
                    video_id=None,
                    status=FAILED,
                    reason="could not parse a YouTube video id",
                )
            )
            continue

        # Dedup: a known id is a no-op — no network call is made.
        if store.exists(video_id):
            report.outcomes.append(
                IngestOutcome(
                    raw=raw,
                    video_id=video_id,
                    status=SKIPPED,
                    reason="already ingested",
                )
            )
            continue

        outcome = _ingest_one(
            raw, video_id, store, metadata_fetcher, transcript_fetcher, now
        )
        report.outcomes.append(outcome)

    return report


def _ingest_one(
    raw: str,
    video_id: str,
    store: VideoStore,
    metadata_fetcher: MetadataFetcher,
    transcript_fetcher: TranscriptFetcher,
    now: Callable[[], str],
) -> IngestOutcome:
    # 1. metadata (yt-dlp)
    try:
        meta: VideoMetadata = metadata_fetcher.fetch(video_id)
    except MetadataUnavailableError as exc:
        return IngestOutcome(raw, video_id, FAILED, f"metadata unavailable: {exc}")

    # 2. enforce the mandatory upload timestamp — never store a record without it
    if not meta.upload_timestamp:
        return IngestOutcome(
            raw, video_id, FAILED, "no upload timestamp in metadata"
        )

    # 3. transcript (youtube-transcript-api)
    try:
        transcript = transcript_fetcher.fetch(video_id)
    except TranscriptUnavailableError as exc:
        return IngestOutcome(raw, video_id, FAILED, f"transcript unavailable: {exc}")

    # 4. build the record (the model re-asserts the mandatory-date invariant)
    try:
        record = VideoRecord(
            id=video_id,
            channel=meta.channel or "",
            date=meta.upload_timestamp,
            views=meta.views,
            transcript=list(transcript),
            chapters=list(meta.chapters),
            title=meta.title,
            url=canonical_watch_url(video_id),
            ingested_at=now(),
        )
    except ValueError as exc:  # invariant violation, defensive
        return IngestOutcome(raw, video_id, FAILED, f"invalid record: {exc}")

    # 5. persist (store.add dedups by id as a backstop to the exists check above)
    added = store.add(record)
    if added:
        return IngestOutcome(raw, video_id, INGESTED, None, record)
    return IngestOutcome(
        raw, video_id, SKIPPED, "already ingested (concurrent)", record
    )
