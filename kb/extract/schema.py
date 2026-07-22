"""The fixed per-video unit-extraction schema (Layer 2, ticket #04).

A *unit* is any content unit from a video, not only a thesis. When the speaker makes
an assertion it is captured as a ``claim`` (with a stance and any evidence offered);
otherwise it is captured as ``content`` — value-adding material that isn't phrased as
an assertion. The schema is *fixed* on purpose: an identical shape across every video
is what makes cross-video comparison (routing, reconciliation, the digest) possible.

Structure forked from the UncleTony78/Youtube-Transcript-Analyzer-Langchain analyzer
(Pydantic model -> structured LLM output), with its generic summary schema replaced by
this domain schema. We do not use LangChain — the Agent SDK returns structured JSON
directly (see ``kb.extract.llm``).

Two containers matter:

* :class:`Unit` / :class:`ExtractedVideo` — the persisted, cross-video comparison atom.
* :class:`ExtractionPayload` — the narrower shape the LLM is asked to return (``units``
  only). The extractor wraps it into an :class:`ExtractedVideo`, supplying ``video_id``
  and ``date`` (which the model never sees) and leaving ``topic_tags`` for Layer 3.
"""

from __future__ import annotations

import datetime as dt
import re
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "UnitType",
    "Stance",
    "Unit",
    "ExtractedVideo",
    "ExtractionPayload",
    "parse_timestamp",
]

_YYYYMMDD = re.compile(r"\A\d{8}\Z")  # yt-dlp `upload_date` format, e.g. "20250511"


class UnitType(str, Enum):
    """What kind of content unit this is.

    Prefer ``claim`` whenever the speaker asserts something; fall back to ``content``
    for value-adding material that is not phrased as an assertion (definitions,
    walkthroughs, examples, framing).
    """

    claim = "claim"
    content = "content"


class Stance(str, Enum):
    """The speaker's polarity toward the subject of the unit's ``text``.

    Stance carries the *direction* of a unit so reconciliation (ticket #08) can tell a
    claim apart from its negation even when their ``text`` embeds alike:

    * ``affirms``  — the speaker asserts the proposition is true / holds / is good.
    * ``denies``   — the speaker asserts the proposition is false / does not hold / is bad.
    * ``neutral``  — descriptive, no side taken (the usual stance for ``content`` units).
    * ``mixed``    — the speaker holds both sides (it depends / true here, false there).
    """

    affirms = "affirms"
    denies = "denies"
    neutral = "neutral"
    mixed = "mixed"


def parse_timestamp(value: object) -> float:
    """Coerce a timestamp to seconds (float, >= 0).

    Accepts a number of seconds, a plain numeric string, or a clock string
    ``"SS"`` / ``"MM:SS"`` / ``"HH:MM:SS"``. This tolerance matters because the LLM sees
    ``[MM:SS]``-prefixed transcript lines and may echo a clock string back rather than a
    raw second count; storing canonical seconds keeps units sortable and citable.
    """

    if isinstance(value, bool):  # bool is an int subclass — reject explicitly
        raise ValueError("timestamp must be a number or clock string, not a bool")
    if isinstance(value, (int, float)):
        seconds = float(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("timestamp string is empty")
        if ":" in text:
            parts = text.split(":")
            if not 1 <= len(parts) <= 3:
                raise ValueError(f"unparseable clock timestamp: {value!r}")
            seconds = 0.0
            for part in parts:
                seconds = seconds * 60 + float(part)
        else:
            seconds = float(text)
    else:
        raise ValueError(f"timestamp must be a number or string, got {type(value).__name__}")
    if seconds < 0:
        raise ValueError("timestamp must be >= 0")
    return seconds


class Unit(BaseModel):
    """One comparison atom extracted from a video."""

    model_config = ConfigDict(extra="forbid")

    type: UnitType = Field(
        description="`claim` when the speaker asserts something, else `content`.",
    )
    text: str = Field(
        min_length=1,
        description="Normalized, self-contained statement of the point (the LLM's own words).",
    )
    raw_quote: str = Field(
        min_length=1,
        description="Verbatim quote from the transcript that this unit is drawn from.",
    )
    timestamp: float = Field(
        ge=0,
        description="Start time of the raw quote, in seconds from the video start.",
    )
    stance: Stance = Field(
        description="Speaker's polarity toward the unit's subject (see Stance).",
    )
    evidence_offered: list[str] = Field(
        default_factory=list,
        description="Concise phrases naming each piece of backing the speaker offers "
        "(benchmark, paper, anecdote, demonstration, ...); empty when none is given.",
    )
    unit_id: str | None = Field(
        default=None,
        description="Stable identity within its video, assigned by the extractor as "
        "`{video_id}#{index}`. Not produced by the LLM; downstream layers link to it.",
    )

    @field_validator("timestamp", mode="before")
    @classmethod
    def _coerce_timestamp(cls, value: object) -> float:
        return parse_timestamp(value)

    @field_validator("text")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("text must not be blank")
        return stripped


class ExtractedVideo(BaseModel):
    """The fixed per-video extraction record: ``{topic_tags, units, date}`` + provenance.

    ``video_id`` is carried alongside the spec's stated ``{topic_tags, units, date}`` so
    every unit stays traceable to its source video — the position KB (ticket #06) links
    positions back to underlying units, and the digest cites the source.
    """

    model_config = ConfigDict(extra="forbid")

    video_id: str = Field(
        min_length=1,
        description="Source video id (the ingest dedup key); ties units back to the video.",
    )
    date: dt.date = Field(
        description="Upload date of the video. Time-series anchor for all trend logic.",
    )
    topic_tags: list[str] = Field(
        default_factory=list,
        description="Topics this video belongs to. Left empty by Layer 2; the Layer 3 "
        "router (#07) populates it from the fixed set in config/topics.yaml.",
    )
    units: list[Unit] = Field(
        default_factory=list,
        description="The content units extracted from this video, in transcript order.",
    )

    @field_validator("date", mode="before")
    @classmethod
    def _coerce_date(cls, value: object) -> dt.date:
        if isinstance(value, dt.datetime):
            return value.date()
        if isinstance(value, dt.date):
            return value
        if isinstance(value, str):
            text = value.strip()
            if _YYYYMMDD.match(text):  # yt-dlp upload_date, e.g. "20250511"
                return dt.date(int(text[0:4]), int(text[4:6]), int(text[6:8]))
            try:
                return dt.date.fromisoformat(text)
            except ValueError:
                return dt.datetime.fromisoformat(text).date()
        raise ValueError(f"date must be a date/datetime/ISO string, got {type(value).__name__}")

    @property
    def claims(self) -> list[Unit]:
        """The units that are assertions (``type == claim``)."""
        return [unit for unit in self.units if unit.type is UnitType.claim]

    @property
    def content_units(self) -> list[Unit]:
        """The units that are value-add, not assertions (``type == content``)."""
        return [unit for unit in self.units if unit.type is UnitType.content]


class ExtractionPayload(BaseModel):
    """What the LLM is asked to return: the ``units`` array, and nothing else.

    ``video_id``/``date`` are supplied by the pipeline (the model never sees them) and
    ``topic_tags`` is Layer 3's job, so keeping the model's contract this narrow shrinks
    what it can get wrong and keeps the extraction seam clean.
    """

    model_config = ConfigDict(extra="forbid")

    units: list[Unit]
