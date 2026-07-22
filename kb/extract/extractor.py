"""The extraction step: transcript -> validated :class:`ExtractedVideo`.

This is the deterministic seam of Layer 2. Everything non-deterministic is behind the
injected :class:`~kb.extract.llm.LLMClient`; given a client, ``extract_units`` is a pure
function of its inputs. The flow:

    segments --render+prompt--> LLM.complete --extract JSON--> validate(ExtractionPayload)
             --assign unit ids--> ExtractedVideo(video_id, date, topic_tags=[], units)

Any failure to obtain schema-valid units (non-JSON, or JSON that violates the fixed
schema) raises :class:`~kb.extract.llm.ExtractionError`.
"""

from __future__ import annotations

import re
from datetime import date

from pydantic import ValidationError

from kb.extract.config import ExtractionConfig
from kb.extract.llm import ExtractionError, LLMClient
from kb.extract.prompt import build_prompt
from kb.extract.schema import ExtractedVideo, ExtractionPayload, Unit
from kb.extract.transcript import TranscriptSegment, chunk_segments

__all__ = ["extract_units", "extract_json_object", "merge_units"]

_NORMALIZE = re.compile(r"[^a-z0-9]+")


def _dedupe_key(unit: Unit) -> str:
    """A normalized form of a unit's statement for near-duplicate detection.

    Chunk overlap (ticket #18) means a unit near a boundary can be extracted by two
    adjacent chunks. Lower-casing and collapsing every non-alphanumeric run to a single
    space folds those re-statements together (minor whitespace/punctuation differences)
    without merging genuinely distinct points.
    """

    return _NORMALIZE.sub(" ", unit.text.lower()).strip()


def merge_units(unit_lists: list[list[Unit]]) -> list[Unit]:
    """Concatenate per-chunk unit lists into one, dropping near-identical restatements.

    Units are kept in first-seen order (transcript order across chunks); the first unit
    with a given normalized statement wins and later duplicates — the artifact of chunk
    overlap — are dropped. ``unit_id`` is assigned by the caller after the merge, so it
    plays no part here.
    """

    merged: list[Unit] = []
    seen: set[str] = set()
    for units in unit_lists:
        for unit in units:
            key = _dedupe_key(unit)
            if key and key in seen:
                continue
            seen.add(key)
            merged.append(unit)
    return merged


def extract_json_object(text: str) -> str:
    """Pull the single JSON object out of a raw LLM response.

    The output contract asks for bare JSON, but real models occasionally wrap it in
    ```json fences or add a stray sentence. This returns the substring from the first
    ``{`` to its matching ``}`` (tracking string literals and escapes so braces inside
    quotes don't fool the scan). Raises :class:`ExtractionError` if no object is found.
    """

    start = text.find("{")
    if start == -1:
        raise ExtractionError("LLM response contained no JSON object")

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise ExtractionError("LLM response had an unterminated JSON object")


def extract_units(
    *,
    segments: list[TranscriptSegment],
    video_id: str,
    date: date | str,
    llm: LLMClient,
    config: ExtractionConfig | None = None,
) -> ExtractedVideo:
    """Extract validated units from a transcript.

    Parameters
    ----------
    segments:
        The video's timestamped transcript (Layer 1 output shape).
    video_id, date:
        Provenance the model never sees; supplied by the pipeline. ``date`` accepts a
        :class:`datetime.date` or any string :class:`ExtractedVideo` can coerce (ISO or
        yt-dlp ``YYYYMMDD``).
    llm:
        The injected LLM client (real in production, a fake/replay in tests).
    config:
        Extraction knobs; defaults are used when omitted.
    """

    config = config or ExtractionConfig()

    chunks = chunk_segments(
        segments,
        max_chars=config.chunk_max_chars,
        overlap_chars=config.chunk_overlap_chars,
    )

    # Short transcript (one chunk): the existing single-call path, unchanged — the whole
    # transcript is rendered under the same truncation guard as before. Long transcripts
    # fan out to one call per chunk and the unit lists are merged (ticket #18).
    per_chunk: list[list[Unit]] = []
    for chunk in chunks:
        max_chars = config.max_transcript_chars if len(chunks) == 1 else None
        system, prompt = build_prompt(chunk, max_chars=max_chars)
        raw = llm.complete(system=system, prompt=prompt, model=config.model)
        per_chunk.append(_parse_units(raw))

    units = per_chunk[0] if len(chunks) == 1 else merge_units(per_chunk)

    for index, unit in enumerate(units):
        unit.unit_id = f"{video_id}#{index}"

    return ExtractedVideo(
        video_id=video_id,
        date=date,
        topic_tags=[],  # populated by Layer 3 routing (ticket #07)
        units=units,
    )


def _parse_units(raw: str) -> list[Unit]:
    """Pull the ``units`` array out of one LLM response, validated against the schema."""

    payload_json = extract_json_object(raw)
    try:
        payload = ExtractionPayload.model_validate_json(payload_json)
    except ValidationError as exc:
        raise ExtractionError(f"LLM output did not match the unit schema: {exc}") from exc
    return payload.units
