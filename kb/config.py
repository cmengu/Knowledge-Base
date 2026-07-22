"""Shared config helpers and repo paths.

Config lives in ``config/*.yaml`` (spec: config-driven, extensible). This module owns
the paths and the cross-layer ``topics`` list; per-layer config models live with their
layer (e.g. :class:`kb.extract.config.ExtractionConfig`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

__all__ = [
    "PROJECT_ROOT",
    "CONFIG_DIR",
    "FIXTURES_DIR",
    "FIXED_TOPICS",
    "load_yaml",
    "load_topics",
]

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
FIXTURES_DIR = PROJECT_ROOT / "fixtures"

# Fallback mirror of config/topics.yaml, so a caller without the file (or before it is
# created) still sees the spec's six-topic set. config/topics.yaml is the source of truth.
FIXED_TOPICS: tuple[str, ...] = (
    "evals",
    "small-models",
    "open-source",
    "harness",
    "enterprise",
    "swe-practices",
)


def load_yaml(path: str | Path) -> Any:
    """Parse a YAML file."""

    with Path(path).open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_topics(path: str | Path | None = None) -> list[str]:
    """Load the fixed topic set from ``config/topics.yaml`` (falls back to FIXED_TOPICS)."""

    path = Path(path) if path is not None else CONFIG_DIR / "topics.yaml"
    if not path.exists():
        return list(FIXED_TOPICS)
    data = load_yaml(path) or {}
    topics = data.get("topics")
    if not topics:
        return list(FIXED_TOPICS)
    return [str(topic) for topic in topics]
