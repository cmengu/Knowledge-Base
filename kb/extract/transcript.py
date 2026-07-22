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

__all__ = ["TranscriptSegment", "format_timestamp", "render_transcript", "chunk_segments"]

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
    set, rendering stops once that budget is reached and a truncation marker is appended.
    Very long transcripts are instead split up front by :func:`chunk_segments` (ticket
    #18) so no content is dropped; ``max_chars`` remains the last-resort guard.
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


def _line_length(segment: TranscriptSegment) -> int:
    """Rendered length of one segment's line (``[M:SS] text`` + newline), 0 if empty.

    Mirrors :func:`render_transcript` exactly so the chunker measures against the same
    character budget the prompt body will actually consume.
    """

    cleaned = _clean(segment.text)
    if not cleaned:
        return 0
    return len(f"[{format_timestamp(segment.start)}] {cleaned}") + 1


def chunk_segments(
    segments: list[TranscriptSegment], *, max_chars: int, overlap_chars: int = 0
) -> list[list[TranscriptSegment]]:
    """Split a transcript into consecutive chunks each within a rendered-char budget.

    Long talks overflow the one-turn output-token budget of the extraction call (ticket
    #18): the model cannot emit the JSON for every unit in a single response. Splitting
    the *input* bounds the units-per-call so each chunk's output fits, and the extractor
    merges the per-chunk unit lists.

    A transcript whose full rendered length is within ``max_chars`` is returned as a
    single chunk holding the **original** ``segments`` unchanged — so short transcripts
    keep taking the existing single-call path byte-for-byte. Longer transcripts are cut
    on segment boundaries (never mid-line) into chunks of about ``max_chars`` each, with
    the trailing ~``overlap_chars`` of one chunk repeated at the head of the next so a
    unit that straddles a boundary is still wholly present in at least one chunk.

    ``overlap_chars`` must be smaller than ``max_chars``; a single segment longer than
    ``max_chars`` is emitted as its own oversized chunk rather than dropped.
    """

    total = sum(_line_length(s) for s in segments)
    if total <= max_chars:
        return [list(segments)]

    measured = [(s, _line_length(s)) for s in segments if _line_length(s) > 0]

    chunks: list[list[TranscriptSegment]] = []
    current: list[tuple[TranscriptSegment, int]] = []
    current_len = 0
    has_fresh = False  # current chunk holds ≥1 not-yet-chunked segment (progress guard)

    index = 0
    while index < len(measured):
        segment, length = measured[index]
        if has_fresh and current_len + length > max_chars:
            # Close the chunk, then seed the next with an overlap tail of this one.
            chunks.append([s for s, _ in current])
            overlap: list[tuple[TranscriptSegment, int]] = []
            overlap_len = 0
            for item in reversed(current):
                if overlap and overlap_len + item[1] > overlap_chars:
                    break
                overlap.insert(0, item)
                overlap_len += item[1]
            current = list(overlap)
            current_len = overlap_len
            has_fresh = False
            continue  # re-test the same segment against the freshly seeded chunk
        current.append((segment, length))
        current_len += length
        has_fresh = True
        index += 1

    if current and has_fresh:
        chunks.append([s for s, _ in current])
    return chunks
