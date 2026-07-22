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

from datetime import date

from pydantic import ValidationError

from kb.extract.config import ExtractionConfig
from kb.extract.llm import ExtractionError, LLMClient
from kb.extract.prompt import build_prompt
from kb.extract.schema import ExtractedVideo, ExtractionPayload
from kb.extract.transcript import TranscriptSegment

__all__ = ["extract_units", "extract_json_object"]


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

    system, prompt = build_prompt(segments, max_chars=config.max_transcript_chars)
    raw = llm.complete(system=system, prompt=prompt, model=config.model)

    payload_json = extract_json_object(raw)
    try:
        payload = ExtractionPayload.model_validate_json(payload_json)
    except ValidationError as exc:
        raise ExtractionError(f"LLM output did not match the unit schema: {exc}") from exc

    for index, unit in enumerate(payload.units):
        unit.unit_id = f"{video_id}#{index}"

    return ExtractedVideo(
        video_id=video_id,
        date=date,
        topic_tags=[],  # populated by Layer 3 routing (ticket #07)
        units=payload.units,
    )
