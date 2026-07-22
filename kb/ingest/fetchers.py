"""The ingest network boundary.

Two dependencies the core loop talks to through :class:`MetadataFetcher` and
:class:`TranscriptFetcher` protocols. Real implementations wrap yt-dlp and
youtube-transcript-api; tests inject fakes returning recorded fixtures, so no
network is ever touched under pytest.

The heavy third-party libraries are imported lazily inside the real fetchers so
that importing this module (and unit-testing the pure helpers below) never
requires them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from ..config import ProxyConfig
from ..models import Chapter, TranscriptSegment
from .errors import MetadataUnavailableError, TranscriptUnavailableError
from .urls import canonical_watch_url


@dataclass(frozen=True)
class VideoMetadata:
    """Normalized subset of yt-dlp's info dict that ingest actually uses.

    ``upload_timestamp`` is already normalized to an ISO 8601 string (or
    ``None`` when yt-dlp exposed no upload time at all — the core loop treats
    that as a hard failure because the timestamp is mandatory).
    """

    id: str
    channel: str | None
    upload_timestamp: str | None
    views: int | None
    title: str | None
    chapters: list[Chapter] = field(default_factory=list)


@runtime_checkable
class MetadataFetcher(Protocol):
    def fetch(self, video_id: str) -> VideoMetadata:
        """Return metadata for ``video_id`` or raise
        :class:`MetadataUnavailableError`."""
        ...


@runtime_checkable
class TranscriptFetcher(Protocol):
    def fetch(self, video_id: str) -> list[TranscriptSegment]:
        """Return the transcript segments for ``video_id`` or raise
        :class:`TranscriptUnavailableError`."""
        ...


# --------------------------------------------------------------------------
# Pure normalization helpers (deterministic, unit-tested, no network)
# --------------------------------------------------------------------------
def normalize_upload_timestamp(
    timestamp: int | float | None, upload_date: str | None
) -> str | None:
    """Normalize yt-dlp's upload fields into one ISO 8601 UTC string.

    Prefers the precise Unix ``timestamp`` (epoch seconds) when present; else
    falls back to the ``upload_date`` (``YYYYMMDD``) at 00:00:00 UTC. Returns
    ``None`` when neither is usable — the caller enforces mandatoriness.
    """
    if timestamp is not None:
        try:
            return (
                datetime.fromtimestamp(float(timestamp), tz=timezone.utc)
                .isoformat()
                .replace("+00:00", "Z")
            )
        except (ValueError, OverflowError, OSError):
            pass  # fall through to upload_date

    if upload_date:
        digits = str(upload_date).strip()
        if len(digits) == 8 and digits.isdigit():
            try:
                return (
                    datetime(
                        int(digits[0:4]),
                        int(digits[4:6]),
                        int(digits[6:8]),
                        tzinfo=timezone.utc,
                    )
                    .isoformat()
                    .replace("+00:00", "Z")
                )
            except ValueError:
                return None
    return None


def normalize_chapters(raw: Any) -> list[Chapter]:
    """Normalize yt-dlp chapters into ``{start, end, title}`` mappings.

    Missing/None chapters become an empty list (most videos have none).
    """
    if not raw:
        return []
    chapters: list[Chapter] = []
    for ch in raw:
        if not isinstance(ch, dict):
            continue
        chapters.append(
            {
                "start": ch.get("start_time"),
                "end": ch.get("end_time"),
                "title": ch.get("title", ""),
            }
        )
    return chapters


def metadata_from_info(info: dict[str, Any]) -> VideoMetadata:
    """Build :class:`VideoMetadata` from a yt-dlp info dict."""
    views = info.get("view_count")
    return VideoMetadata(
        id=info.get("id", ""),
        channel=info.get("channel") or info.get("uploader"),
        upload_timestamp=normalize_upload_timestamp(
            info.get("timestamp"), info.get("upload_date")
        ),
        views=int(views) if isinstance(views, (int, float)) else None,
        title=info.get("title"),
        chapters=normalize_chapters(info.get("chapters")),
    )


# --------------------------------------------------------------------------
# Real implementations (wrap the third-party libraries; lazy imports)
# --------------------------------------------------------------------------
class YtDlpMetadataFetcher:
    """Fetch metadata with yt-dlp, on the local IP by default."""

    def __init__(self, proxy_url: str = "") -> None:
        self._proxy_url = proxy_url or ""

    def fetch(self, video_id: str) -> VideoMetadata:
        import yt_dlp  # lazy: only needed for real fetches

        # YoutubeDLError is the base of DownloadError, ExtractorError,
        # GeoRestrictedError, UnavailableVideoError, … — catch all of them so
        # one bad video is reported, never propagated to abort the batch.
        from yt_dlp.utils import YoutubeDLError

        opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "extract_flat": False,
        }
        if self._proxy_url:
            opts["proxy"] = self._proxy_url

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(
                    canonical_watch_url(video_id), download=False
                )
                info = ydl.sanitize_info(info)
        except YoutubeDLError as exc:
            raise MetadataUnavailableError(
                f"yt-dlp could not fetch metadata for {video_id}: {exc}"
            ) from exc
        if not info:
            raise MetadataUnavailableError(
                f"yt-dlp returned no metadata for {video_id}"
            )
        return metadata_from_info(info)


class TranscriptApiFetcher:
    """Fetch transcripts with youtube-transcript-api (no API key).

    When ``proxy`` is enabled the fetcher routes through youtube-transcript-api's
    native Webshare rotating-residential-proxy support; otherwise it uses the
    local IP directly.
    """

    def __init__(
        self,
        languages: tuple[str, ...] = ("en",),
        proxy: ProxyConfig | None = None,
    ) -> None:
        self._languages = tuple(languages) or ("en",)
        self._proxy = proxy

    def _build_api(self):
        from youtube_transcript_api import YouTubeTranscriptApi

        proxy_config = None
        if self._proxy is not None and self._proxy.enabled:
            from youtube_transcript_api.proxies import WebshareProxyConfig

            proxy_config = WebshareProxyConfig(
                proxy_username=self._proxy.webshare_proxy_username,
                proxy_password=self._proxy.webshare_proxy_password,
            )
        return YouTubeTranscriptApi(proxy_config=proxy_config)

    def fetch(self, video_id: str) -> list[TranscriptSegment]:
        from youtube_transcript_api._errors import CouldNotRetrieveTranscript

        api = self._build_api()
        try:
            fetched = api.fetch(video_id, languages=list(self._languages))
        except CouldNotRetrieveTranscript as exc:
            raise TranscriptUnavailableError(
                f"no transcript for {video_id}: {exc}"
            ) from exc
        # to_raw_data() -> [{"text", "start", "duration"}, ...]
        return list(fetched.to_raw_data())
