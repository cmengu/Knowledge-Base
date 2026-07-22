"""The reconciliation input: an extracted unit plus the provenance it needs to be cited.

The reconciliation engine (ticket #08) compares each incoming unit against a topic's
positions. A bare :class:`~kb.extract.Unit` cannot become a :class:`~kb.reconcile.schema.
PositionSource` on its own: a source must carry the ``video_id`` and upload ``date`` that
live on the unit's enclosing :class:`~kb.extract.ExtractedVideo`, not on the unit itself.
:class:`IncomingUnit` is the small carrier that pairs a unit with that provenance so the
engine can project it into a source and cite it with source + date.

Routing (Layer 3, ticket #07) is a *separate* layer: it decides which topic(s) a unit
belongs to. ``reconcile`` does not route — it reconciles whatever units it is handed
against one topic's KB. :meth:`IncomingUnit.iter_from_video` is the convenience the
pipeline uses to flatten an :class:`~kb.extract.ExtractedVideo` into incoming units;
by default it keeps only ``claim`` units, because positions track assertions and
``content`` units are value-adding material, not claims to reconcile.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator

from pydantic import BaseModel, ConfigDict, Field

from kb.extract import ExtractedVideo, Unit, UnitType
from kb.reconcile.schema import Alignment, PositionSource

__all__ = ["IncomingUnit"]


class IncomingUnit(BaseModel):
    """One unit to reconcile, carrying the video id + date needed to cite it.

    ``unit`` must already have its ``unit_id`` assigned (the extractor does this); an
    un-linked unit cannot become a position source. ``video_id`` and ``date`` are the
    provenance projected onto every source this unit produces.
    """

    model_config = ConfigDict(extra="forbid")

    unit: Unit = Field(description="The extracted comparison atom (with its unit_id set).")
    video_id: str = Field(
        min_length=1,
        description="Source video id — the dedup key and the source's citation anchor.",
    )
    date: dt.date = Field(
        description="Upload date of the source video; the time-series anchor for maturity.",
    )

    @property
    def unit_id(self) -> str:
        """The underlying unit's id (raises if the unit was never linked)."""
        if not self.unit.unit_id:
            raise ValueError("incoming unit has no unit_id; assign one via the extractor first")
        return self.unit.unit_id

    def to_source(self, alignment: Alignment | str) -> PositionSource:
        """Project this incoming unit into a :class:`PositionSource` with ``alignment``.

        ``alignment`` is the unit's relationship to the *position's* statement
        (``supporting`` for a confirming unit, ``opposing`` for an adversarial one) — a
        decision the adjudicator makes, deliberately independent of the unit's own stance.
        """

        return PositionSource.from_unit(
            self.unit, video_id=self.video_id, date=self.date, alignment=alignment
        )

    @classmethod
    def iter_from_video(
        cls, video: ExtractedVideo, *, claims_only: bool = True
    ) -> Iterator["IncomingUnit"]:
        """Yield the video's units as :class:`IncomingUnit`, in transcript order.

        Routing/topic selection is the caller's concern (Layer 3); this simply pairs each
        unit with the video's ``video_id`` and ``date``. With ``claims_only`` (the
        default) only ``claim`` units are yielded — ``content`` units add value but are
        not assertions the position KB tracks.
        """

        for unit in video.units:
            if claims_only and unit.type is not UnitType.claim:
                continue
            yield cls(unit=unit, video_id=video.video_id, date=video.date)
