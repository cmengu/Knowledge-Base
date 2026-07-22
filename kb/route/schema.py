"""Schemas for Layer 3 — topic routing (ticket #07).

Routing is additive over Layer 2: it never mutates the fixed :class:`~kb.extract.schema.Unit`
schema, it *overlays* a topic assignment on top of it. Two shapes matter, mirroring the
extract layer's split between the LLM-facing contract and the persisted record:

* :class:`RoutingPayload` — the narrow shape the classifier asks the LLM to return:
  video-level topics plus a ``{unit_id, topics}`` entry per unit. Topic *membership*
  (that every topic is one of the configured set) is enforced by the classifier, not
  here, because the fixed set lives in config and is injected per call.
* :class:`RoutedUnit` / :class:`RoutedVideo` — the persisted routing result. A
  ``RoutedUnit`` composes the original extracted unit with the ≥1 topics it routes to;
  a ``RoutedVideo`` carries the video-level ``topic_tags`` (the field the extract
  schema reserves for exactly this layer) plus the routed units, and can be projected
  back to an :class:`~kb.extract.schema.ExtractedVideo` with its ``topic_tags`` filled.

Multi-topic assignment is first-class: ``topics`` is a list, so a single unit can inform
several topics at once (spec user story 9).
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field

from kb.extract.schema import ExtractedVideo, Unit

__all__ = [
    "UnitRouting",
    "RoutingPayload",
    "RoutedUnit",
    "RoutedVideo",
]


class UnitRouting(BaseModel):
    """The LLM's topic assignment for one unit: its id and the topics it routes to."""

    model_config = ConfigDict(extra="forbid")

    unit_id: str = Field(
        min_length=1,
        description="The `{video_id}#{index}` id of the unit being routed (echoed back).",
    )
    topics: list[str] = Field(
        min_length=1,
        description="One or more topics this unit belongs to (validated against the "
        "configured set by the classifier). Multi-topic is allowed.",
    )


class RoutingPayload(BaseModel):
    """What the LLM is asked to return: video-level topics + a routing per unit.

    Kept deliberately narrow (ids + topics, no unit content echoed) so the model can only
    get the routing wrong, not the unit text. The classifier joins these ids back to the
    real units and enforces that every topic is one of the configured set and that every
    input unit is covered.
    """

    model_config = ConfigDict(extra="forbid")

    video_topics: list[str] = Field(
        min_length=1,
        description="One or more topics the video as a whole belongs to.",
    )
    units: list[UnitRouting] = Field(
        description="Per-unit topic assignments, one entry per input unit.",
    )


class RoutedUnit(BaseModel):
    """One extracted unit overlaid with its topic assignment.

    Composes (does not modify) the fixed :class:`~kb.extract.schema.Unit`, so the routed
    record is a self-sufficient input to reconciliation (ticket #08): each unit arrives
    with both its content and the topics whose knowledge base it should be compared in.
    """

    model_config = ConfigDict(extra="forbid")

    unit: Unit = Field(description="The original extracted unit (Layer 2 schema, unchanged).")
    topics: list[str] = Field(
        min_length=1,
        description="The topics this unit routes to (≥1, all from the configured set).",
    )


class RoutedVideo(BaseModel):
    """The per-video routing result: video-level ``topic_tags`` + routed units.

    ``topic_tags`` is the same field name the extract schema reserves on
    :class:`~kb.extract.schema.ExtractedVideo` ("the Layer 3 router populates it"); a
    ``RoutedVideo`` can be projected straight back to a tagged ``ExtractedVideo`` via
    :meth:`to_extracted_video`.
    """

    model_config = ConfigDict(extra="forbid")

    video_id: str = Field(
        min_length=1,
        description="Source video id; ties the routing back to the ingested video.",
    )
    date: dt.date = Field(description="Upload date, carried through from the extraction.")
    topic_tags: list[str] = Field(
        min_length=1,
        description="Video-level topics (≥1, all from the configured set).",
    )
    units: list[RoutedUnit] = Field(
        description="Each extracted unit with its topic assignment, in transcript order.",
    )

    def to_extracted_video(self) -> ExtractedVideo:
        """Project back to an :class:`ExtractedVideo` with ``topic_tags`` populated.

        Restores the exact Layer 2 record shape — the same units, now carrying the
        video-level topic tags this layer assigned — for any consumer that wants the
        canonical extraction record rather than the routing overlay.
        """

        return ExtractedVideo(
            video_id=self.video_id,
            date=self.date,
            topic_tags=list(self.topic_tags),
            units=[routed.unit for routed in self.units],
        )
