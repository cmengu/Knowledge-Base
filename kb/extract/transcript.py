"""Transcript representation consumed by the extraction step.

Layer 1 ingest (ticket #03) owns fetching; this module defines only the minimal shape
the extractor needs — timestamped text segments — plus the rendering that turns them
into the ``[MM:SS] text`` prompt body the LLM reads. Keeping the segment model here
lets the extract layer be tested from a recorded transcript fixture with no dependency
on ingest or the network.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["TranscriptSegment", "format_timestamp", "render_transcript"]

_WHITESPACE = re.compile(r"\s+")  # collapses \xa0, newlines and runs of spaces


class TranscriptSegment(BaseModel):
    """One timestamped transcript snippet (the youtube-transcript-api shape)."""

    model_config = ConfigDict(extra="ignore")

    text: str
    start: float = Field(ge=0, description="Start time in seconds from video start.")
    duration: float = Field(default=0.0, ge=0)


def format_timestamp(seconds: float) -> str:
    """Render seconds as ``M:SS`` (or ``H:MM:SS`` past an hour) for prompts and display."""

    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _clean(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip()


def render_transcript(segments: Iterable[TranscriptSegment], *, max_chars: int | None = None) -> str:
    """Render segments as timestamped lines for the LLM.

    Each line is ``[M:SS] cleaned text`` so the model can attach an accurate start time
    to every unit's raw quote. Whitespace artifacts (non-breaking spaces, mid-caption
    newlines) are collapsed so the model quotes clean text back. When ``max_chars`` is
    set, rendering stops once that budget is reached and a truncation marker is appended
    — this keeps one video to a single LLM call (chunking long videos is future work).
    """

    lines: list[str] = []
    used = 0
    truncated = False
    for segment in segments:
        cleaned = _clean(segment.text)
        if not cleaned:
            continue
        line = f"[{format_timestamp(segment.start)}] {cleaned}"
        if max_chars is not None and used + len(line) + 1 > max_chars:
            truncated = True
            break
        lines.append(line)
        used += len(line) + 1
    if truncated:
        lines.append("[transcript truncated for length]")
    return "\n".join(lines)
