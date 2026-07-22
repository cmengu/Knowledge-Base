"""The core ingest seam, exercised offline with recorded fixtures + fakes.

Covers the ticket's contract: record shape, dedup no-op (no network on a known
id), the mandatory upload timestamp, and that failures are not persisted (so a
re-run retries them).
"""

from __future__ import annotations

from kb.ingest import ingest
from kb.ingest.fetchers import VideoMetadata
from tests.conftest import (
    KARPATHY_LLM,
    NO_PRIORS,
    ExplodingFetcher,
    FakeMetadataFetcher,
    FakeTranscriptFetcher,
    load_transcript,
)

WATCH = "https://www.youtube.com/watch?v={}"


def _ingest(entries, store, meta, tr, now=lambda: "2026-07-22T00:00:00Z"):
    return ingest(
        entries,
        store=store,
        metadata_fetcher=meta,
        transcript_fetcher=tr,
        now=now,
    )


# --------------------------------------------------------------------------
# Record shape
# --------------------------------------------------------------------------
def test_record_shape(store, metadata_fetcher, transcript_fetcher):
    report = _ingest(
        [WATCH.format(KARPATHY_LLM)], store, metadata_fetcher, transcript_fetcher
    )
    assert report.summary() == "1 ingested, 0 skipped, 0 failed (1 total)"
    [outcome] = report.ingested
    rec = outcome.record

    # Canonical spec fields {id, channel, date, views, transcript, chapters}
    assert rec.id == KARPATHY_LLM
    assert rec.channel == "Andrej Karpathy"
    assert rec.date == "2023-11-23T02:27:48Z"  # mandatory upload timestamp
    assert rec.views == 3895018
    assert rec.transcript == load_transcript(KARPATHY_LLM)
    assert len(rec.chapters) == 21
    assert set(rec.chapters[0]) == {"start", "end", "title"}
    # Additive operational fields
    assert rec.url == WATCH.format(KARPATHY_LLM)
    assert rec.ingested_at == "2026-07-22T00:00:00Z"
    assert rec.title.startswith("[1hr Talk]")

    # Persisted and retrievable
    assert store.get(KARPATHY_LLM) == rec


def test_multiple_videos_ingested(store, metadata_fetcher, transcript_fetcher):
    report = _ingest(
        [WATCH.format(KARPATHY_LLM), f"https://youtu.be/{NO_PRIORS}"],
        store,
        metadata_fetcher,
        transcript_fetcher,
    )
    assert len(report.ingested) == 2
    assert store.count() == 2
    assert {r.id for r in store.all()} == {KARPATHY_LLM, NO_PRIORS}


# --------------------------------------------------------------------------
# Mandatory upload timestamp
# --------------------------------------------------------------------------
def test_every_persisted_record_has_a_timestamp(
    store, metadata_fetcher, transcript_fetcher
):
    _ingest(
        [WATCH.format(KARPATHY_LLM), WATCH.format(NO_PRIORS)],
        store,
        metadata_fetcher,
        transcript_fetcher,
    )
    records = store.all()
    assert records  # non-empty
    assert all(r.date and r.date.strip() for r in records)


def test_missing_timestamp_fails_and_is_not_persisted(store, transcript_fetcher):
    # Metadata with no upload timestamp must never be stored.
    meta = FakeMetadataFetcher(
        {
            KARPATHY_LLM: VideoMetadata(
                id=KARPATHY_LLM,
                channel="Andrej Karpathy",
                upload_timestamp=None,  # the offending field
                views=1,
                title="t",
                chapters=[],
            )
        }
    )
    report = _ingest([WATCH.format(KARPATHY_LLM)], store, meta, transcript_fetcher)
    [failed] = report.failed
    assert failed.video_id == KARPATHY_LLM
    assert "timestamp" in failed.reason
    assert store.count() == 0  # nothing persisted
    # Transcript is never even fetched once metadata is rejected.
    assert transcript_fetcher.calls == []


# --------------------------------------------------------------------------
# Dedup — a known id is a no-op with NO network call
# --------------------------------------------------------------------------
def test_reingest_is_noop_and_makes_no_network_call(
    store, metadata_fetcher, transcript_fetcher
):
    entries = [WATCH.format(KARPATHY_LLM), WATCH.format(NO_PRIORS)]
    first = _ingest(entries, store, metadata_fetcher, transcript_fetcher)
    assert len(first.ingested) == 2

    # Second pass: both ids are known. Use exploding fetchers to prove that
    # NO fetch happens on the dedup path.
    boom_meta, boom_tr = ExplodingFetcher(), ExplodingFetcher()
    second = _ingest(entries, store, boom_meta, boom_tr)
    assert len(second.skipped) == 2
    assert all(o.reason == "already ingested" for o in second.skipped)
    assert boom_meta.calls == [] and boom_tr.calls == []
    assert store.count() == 2  # unchanged


def test_duplicate_within_one_batch_is_deduped(
    store, metadata_fetcher, transcript_fetcher
):
    entries = [WATCH.format(KARPATHY_LLM), f"https://youtu.be/{KARPATHY_LLM}"]
    report = _ingest(entries, store, metadata_fetcher, transcript_fetcher)
    assert len(report.ingested) == 1
    assert len(report.skipped) == 1
    assert store.count() == 1
    # The one metadata fetch happened exactly once for the video.
    assert metadata_fetcher.calls == [KARPATHY_LLM]


# --------------------------------------------------------------------------
# Failures are not persisted and therefore retryable on a later run
# --------------------------------------------------------------------------
def test_transcript_failure_is_not_persisted_then_retryable(
    store, metadata_fetcher, recorded_transcripts
):
    # First run: transcript unavailable for the video → failed, nothing stored.
    empty_tr = FakeTranscriptFetcher({})  # no transcripts → raises
    first = _ingest([WATCH.format(KARPATHY_LLM)], store, metadata_fetcher, empty_tr)
    assert len(first.failed) == 1
    assert "transcript" in first.failed[0].reason
    assert store.count() == 0

    # Second run: transcript now available → it ingests (not dedup-skipped).
    good_tr = FakeTranscriptFetcher(recorded_transcripts)
    meta2 = FakeMetadataFetcher(metadata_fetcher.metadata_by_id)
    second = _ingest([WATCH.format(KARPATHY_LLM)], store, meta2, good_tr)
    assert len(second.ingested) == 1
    assert store.count() == 1


def test_metadata_failure_is_reported_not_persisted(store, transcript_fetcher):
    meta = FakeMetadataFetcher({})  # unknown id → MetadataUnavailableError
    report = _ingest([WATCH.format(KARPATHY_LLM)], store, meta, transcript_fetcher)
    assert len(report.failed) == 1
    assert "metadata" in report.failed[0].reason
    assert store.count() == 0


# --------------------------------------------------------------------------
# Unparseable input
# --------------------------------------------------------------------------
def test_unparseable_url_fails_without_fetching(store):
    boom_meta, boom_tr = ExplodingFetcher(), ExplodingFetcher()
    report = _ingest(["this is not a youtube url"], store, boom_meta, boom_tr)
    [failed] = report.failed
    assert failed.video_id is None
    assert "parse" in failed.reason
    assert boom_meta.calls == [] and boom_tr.calls == []
    assert store.count() == 0


def test_mixed_batch_report_counts(
    store, metadata_fetcher, transcript_fetcher
):
    # 1 good, 1 unparseable, 1 unknown-id (metadata failure).
    entries = [
        WATCH.format(KARPATHY_LLM),
        "garbage",
        WATCH.format("unknownvid0"),
    ]
    report = _ingest(entries, store, metadata_fetcher, transcript_fetcher)
    assert len(report.ingested) == 1
    assert len(report.failed) == 2
    assert store.count() == 1
    assert report.summary() == "1 ingested, 0 skipped, 2 failed (3 total)"
