"""Layer 2 — unit extraction (ticket #04).

Owns the fixed per-video unit schema and the transcript -> validated-units step. Public
surface:

    from kb.extract import (
        Unit, ExtractedVideo, UnitType, Stance,   # the fixed schema
        extract_units,                            # the extraction step
        LLMClient, AgentSDKClient, ExtractionError,  # the injected LLM seam
        TranscriptSegment, ExtractionConfig,
    )
"""

from __future__ import annotations

from kb.extract.config import ExtractionConfig, load_extraction_config
from kb.extract.extractor import extract_json_object, extract_units, merge_units
from kb.extract.llm import AgentSDKClient, ExtractionError, LLMClient
from kb.extract.prompt import SYSTEM_PROMPT, build_prompt, build_user_prompt
from kb.extract.schema import (
    ExtractedVideo,
    ExtractionPayload,
    Stance,
    Unit,
    UnitType,
    parse_timestamp,
)
from kb.extract.transcript import (
    TranscriptSegment,
    chunk_segments,
    format_timestamp,
    render_transcript,
)

__all__ = [
    # schema
    "Unit",
    "ExtractedVideo",
    "ExtractionPayload",
    "UnitType",
    "Stance",
    "parse_timestamp",
    # transcript
    "TranscriptSegment",
    "render_transcript",
    "format_timestamp",
    "chunk_segments",
    # prompt
    "SYSTEM_PROMPT",
    "build_prompt",
    "build_user_prompt",
    # extraction step
    "extract_units",
    "extract_json_object",
    "merge_units",
    # llm seam
    "LLMClient",
    "AgentSDKClient",
    "ExtractionError",
    # config
    "ExtractionConfig",
    "load_extraction_config",
]
