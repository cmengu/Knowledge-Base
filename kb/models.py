"""Domain models shared across pipeline layers.

Layer 1 produces exactly one :class:`VideoRecord` per successfully ingested
video. The record is faithful to the spec's canonical shape
``{id, channel, date, views, transcript, chapters}`` and adds a few purely
additive operational fields (``title``, ``url``, ``ingested_at``) that never
alter that contract.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

# A transcript is a list of timestamped segments as returned by
# youtube-transcript-api's ``to_raw_data()``: {"text", "start", "duration"}.
TranscriptSegment = dict[str, Any]
# A chapter is a normalized {"start", "end", "title"} mapping.
Chapter = dict[str, Any]


@dataclass(frozen=True)
class VideoRecord:
    """One ingested YouTube video.

    ``date`` is the upload timestamp and is **mandatory**: all downstream trend
    logic is time-series, so a record may never exist without it. The invariant
    is enforced here at construction time.
    """

    id: str
    channel: str
    date: str  # ISO 8601 upload timestamp (UTC); MANDATORY, never empty
    views: int | None
    transcript: list[TranscriptSegment] = field(default_factory=list)
    chapters: list[Chapter] = field(default_factory=list)
    # Additive operational metadata (not part of the canonical comparison shape):
    title: str | None = None
    url: str | None = None
    ingested_at: str | None = None  # ISO 8601 moment this row was written

    def __post_init__(self) -> None:
        if not self.id or not str(self.id).strip():
            raise ValueError("VideoRecord.id must be a non-empty string")
        if not self.date or not str(self.date).strip():
            raise ValueError(
                f"VideoRecord.date (upload timestamp) is mandatory and must be "
                f"non-empty; got {self.date!r} for id={self.id!r}"
            )

    def transcript_text(self) -> str:
        """Flatten the segmented transcript into plain text."""
        return " ".join(
            str(seg.get("text", "")).strip()
            for seg in self.transcript
            if str(seg.get("text", "")).strip()
        )

    def to_row(self) -> dict[str, Any]:
        """Serialize to a SQLite-friendly row (nested fields as JSON text)."""
        return {
            "id": self.id,
            "channel": self.channel,
            "date": self.date,
            "views": self.views,
            "transcript": json.dumps(self.transcript, ensure_ascii=False),
            "chapters": json.dumps(self.chapters, ensure_ascii=False),
            "title": self.title,
            "url": self.url,
            "ingested_at": self.ingested_at,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "VideoRecord":
        """Rebuild a record from a stored SQLite row."""
        return cls(
            id=row["id"],
            channel=row["channel"],
            date=row["date"],
            views=row["views"],
            transcript=json.loads(row["transcript"]) if row["transcript"] else [],
            chapters=json.loads(row["chapters"]) if row["chapters"] else [],
            title=row["title"],
            url=row["url"],
            ingested_at=row["ingested_at"],
        )
