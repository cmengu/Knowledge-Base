"""Failure signals raised at the fetcher boundary.

The core :func:`kb.ingest.ingest` loop catches these to turn one video's
failure into a reported outcome without aborting the batch. Tests raise them
from injected fake fetchers to exercise the failure paths deterministically.
"""

from __future__ import annotations


class IngestError(Exception):
    """Base class for recoverable, per-video ingest failures."""


class MetadataUnavailableError(IngestError):
    """yt-dlp could not return metadata for the video."""


class TranscriptUnavailableError(IngestError):
    """No transcript could be retrieved (disabled, none in wanted languages,
    blocked, or the video is unavailable)."""
