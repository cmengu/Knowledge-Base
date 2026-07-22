"""Fixture-bound adjudicator tests: the recorded Opus verdict round-trips against the code.

Uses the committed output of the one live Opus smoke call (``scripts/run_adjudication.py``)
— the recorded (input pair + verbatim response + parsed verdict) — never a live call. Proves
(a) the recorded verdict is schema-valid, (b) replaying the recorded response through the
real :class:`OpusAdjudicator` reproduces that verdict exactly, and (c) on a genuine Opus
call the anti-manufactured-agreement guardrail held: an adversarial verdict quotes *both*
competing claims with their source + date and leaves the disagreement unreconciled.
"""

from __future__ import annotations

import json

from kb.config import FIXTURES_DIR
from kb.extract import Unit
from kb.reconcile import Classification, IncomingUnit, Position, Verdict
from kb.reconcile.adjudicator import OpusAdjudicator
from tests.helpers import FakeLLMClient, load_recorded_verdict, read_recorded_adjudication_raw


def _load_pair(name: str) -> tuple[IncomingUnit, list[Position]]:
    doc = json.loads((FIXTURES_DIR / "adjudications" / f"{name}.input.json").read_text("utf-8"))
    inc = doc["incoming"]
    incoming = IncomingUnit(
        unit=Unit.model_validate(inc["unit"]), video_id=inc["video_id"], date=inc["date"]
    )
    candidates = [Position.model_validate(c) for c in doc["candidates"]]
    return incoming, candidates


def test_recorded_verdict_is_schema_valid(adjudication_name):
    verdict = Verdict.model_validate(load_recorded_verdict(adjudication_name))
    assert verdict.rationale                                   # a real justification was produced


def test_replay_reproduces_recorded_verdict(adjudication_name):
    """Replaying the recorded raw Opus output must reproduce the committed verdict."""

    incoming, candidates = _load_pair(adjudication_name)
    raw = read_recorded_adjudication_raw(adjudication_name)

    reproduced = OpusAdjudicator(FakeLLMClient(raw)).adjudicate(unit=incoming, candidates=candidates)

    expected = Verdict.model_validate(load_recorded_verdict(adjudication_name))
    assert reproduced == expected


def test_recorded_adversarial_verdict_honors_the_guardrail(adjudication_name):
    """On a real Opus call, an adversarial verdict quotes both sides + leaves it open."""

    incoming, candidates = _load_pair(adjudication_name)
    verdict = Verdict.model_validate(load_recorded_verdict(adjudication_name))
    if verdict.classification is not Classification.adversarial:
        return  # the guardrail assertions only apply to adversarial verdicts

    assert verdict.reconciliation is not None
    target = next(c for c in candidates if c.position_id == verdict.target_position_id)
    rationale = verdict.rationale
    # the competing claims are quoted WITH source + date, on both sides (the guardrail)
    assert incoming.video_id in rationale and incoming.date.isoformat() in rationale
    assert target.sources[0].video_id in rationale and target.sources[0].date.isoformat() in rationale
    # "unreconciled — genuinely open" is a first-class outcome, expected here
    assert verdict.reconciliation.is_open
