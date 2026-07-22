"""Configuration for the extraction step (loaded from ``config/extraction.yaml``)."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

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


def load_extraction_config(path: str | Path | None = None) -> ExtractionConfig:
    """Load :class:`ExtractionConfig` from YAML (defaults when the file is absent)."""

    path = Path(path) if path is not None else CONFIG_DIR / "extraction.yaml"
    if not path.exists():
        return ExtractionConfig()
    return ExtractionConfig.model_validate(load_yaml(path) or {})
