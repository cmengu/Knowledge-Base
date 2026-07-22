"""Tests for :class:`IncomingUnit` — the reconciliation input carrier (ticket #08)."""

from __future__ import annotations

import datetime as dt

import pytest

from kb.extract import ExtractedVideo, Unit
from kb.reconcile import Alignment, IncomingUnit


def _unit(text="Small models are good enough.", *, unit_id="vidA#0", type="claim", stance="affirms") -> Unit:
    return Unit(type=type, text=text, raw_quote=text, timestamp=1.0, stance=stance, unit_id=unit_id)


def test_to_source_projects_provenance_and_alignment():
    inc = IncomingUnit(unit=_unit(), video_id="vidA", date="2025-05-01")
    src = inc.to_source(Alignment.supporting)
    assert src.unit_id == "vidA#0" and src.video_id == "vidA"
    assert src.date == dt.date(2025, 5, 1)
    assert src.alignment is Alignment.supporting
    assert src.stance.value == "affirms"                 # the unit's own stance carries over
    assert src.quote == "Small models are good enough."  # raw_quote -> quote


def test_to_source_opposing_alignment_is_independent_of_stance():
    # a unit that affirms its own subject can be an *opposing* source of a position
    inc = IncomingUnit(unit=_unit(stance="affirms"), video_id="v", date="2025-05-01")
    assert inc.to_source("opposing").alignment is Alignment.opposing


def test_unit_id_property_requires_assignment():
    inc = IncomingUnit(unit=_unit(unit_id=None), video_id="v", date="2025-05-01")
    with pytest.raises(ValueError):
        _ = inc.unit_id


def test_iter_from_video_keeps_only_claims_by_default():
    video = ExtractedVideo(
        video_id="vidA", date="2025-05-01",
        units=[_unit(unit_id="vidA#0", type="claim"), _unit(unit_id="vidA#1", type="content", stance="neutral")],
    )
    incoming = list(IncomingUnit.iter_from_video(video))
    assert [i.unit_id for i in incoming] == ["vidA#0"]    # content dropped
    assert all(i.video_id == "vidA" and i.date == dt.date(2025, 5, 1) for i in incoming)


def test_iter_from_video_can_include_content():
    video = ExtractedVideo(
        video_id="vidA", date="2025-05-01",
        units=[_unit(unit_id="vidA#0", type="claim"), _unit(unit_id="vidA#1", type="content", stance="neutral")],
    )
    incoming = list(IncomingUnit.iter_from_video(video, claims_only=False))
    assert [i.unit_id for i in incoming] == ["vidA#0", "vidA#1"]


def test_incoming_unit_rejects_extra_fields():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        IncomingUnit(unit=_unit(), video_id="v", date="2025-05-01", topic="evals")
