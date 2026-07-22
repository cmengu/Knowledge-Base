"""Configuration for the extraction step (loaded from ``config/extraction.yaml``)."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from kb.config import CONFIG_DIR, load_yaml

__all__ = ["ExtractionConfig", "load_extraction_config"]


class ExtractionConfig(BaseModel):
    """Knobs for turning a transcript into units."""

    model_config = ConfigDict(extra="forbid")

    model: str = Field(
        default="sonnet",
        description="Agent SDK model alias/id for extraction (Sonnet tier per the spec).",
    )
    max_transcript_chars: int = Field(
        default=200_000,
        gt=0,
        description="Character budget for the rendered transcript; longer is truncated.",
    )
    chunk_max_chars: int = Field(
        default=45_000,
        gt=0,
        description="Per-chunk rendered-transcript budget (ticket #18). A transcript "
        "whose rendered body exceeds this is split into multiple extraction calls whose "
        "unit lists are merged; shorter transcripts keep the single-call path unchanged. "
        "Set from the seed-set overflow point: the shortest talk that busted the "
        "one-turn output budget rendered ~21k chars, so 45k splits only the clear "
        "outliers while leaving the working majority single-call.",
    )
    chunk_overlap_chars: int = Field(
        default=2_000,
        ge=0,
        description="Characters of transcript repeated at each chunk boundary so a unit "
        "spanning the cut is still wholly present in one chunk. Must be < chunk_max_chars.",
    )

    @model_validator(mode="after")
    def _overlap_below_chunk(self) -> "ExtractionConfig":
        if self.chunk_overlap_chars >= self.chunk_max_chars:
            raise ValueError("chunk_overlap_chars must be smaller than chunk_max_chars")
        return self


def load_extraction_config(path: str | Path | None = None) -> ExtractionConfig:
    """Load :class:`ExtractionConfig` from YAML (defaults when the file is absent)."""

    path = Path(path) if path is not None else CONFIG_DIR / "extraction.yaml"
    if not path.exists():
        return ExtractionConfig()
    return ExtractionConfig.model_validate(load_yaml(path) or {})
