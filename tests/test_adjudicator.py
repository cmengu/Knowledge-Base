"""Stage-2 adjudicator tests: verdict schema, parsing, wiring, and the baked-in guardrail.

The real :class:`OpusAdjudicator` is exercised over a :class:`FakeLLMClient` (no live
call); LLM *judgment quality* is not asserted here (it is non-deterministic — validated
against the recorded fixture in test_adjudicator_fixture.py). What is asserted: the verdict
schema's cross-field rules, tolerant JSON parsing, model routing, target validation, and
that the anti-manufactured-agreement guardrail is present in the prompt (a ticket #08
design requirement).
"""

from __future__ import annotations

import datetime as dt
import json

import pytest
from pydantic import ValidationError

from kb.extract import Unit
from kb.reconcile import (
    Classification,
    IncomingUnit,
    Position,
    PositionSource,
    Reconciliation,
    Verdict,
    parse_verdict,
)
from kb.reconcile.adjudicator import (
    SYSTEM_PROMPT,
    AdjudicationConfig,
    AdjudicationError,
    OpusAdjudicator,
    build_adjudication_prompt,
)
from tests.helpers import FakeLLMClient

NOW = dt.datetime(2025, 6, 1, 9, 0)


def _incoming(text="Small models are good enough.", *, unit_id="vidA#0", video_id="vidA", date="2025-05-01") -> IncomingUnit:
    unit = Unit(type="claim", text=text, raw_quote=text, timestamp=1.0, stance="affirms", unit_id=unit_id)
    return IncomingUnit(unit=unit, video_id=video_id, date=date)


def _candidate(position_id="evals-0001", statement="You should build your own evals.") -> Position:
    src = PositionSource(
        unit_id="seed#0", video_id="seed", date="2025-01-01", alignment="supporting",
        stance="affirms", quote="build your own evals", statement=statement,
    )
    return Position.create(position_id=position_id, topic="evals", statement=statement, at=NOW, first_source=src)


# --- Verdict cross-field validation ----------------------------------------


def test_confirming_requires_target_and_kind():
    with pytest.raises(ValidationError):
        Verdict(classification="confirming", rationale="x")            # no target/kind
    with pytest.raises(ValidationError):
        Verdict(classification="confirming", target_position_id="evals-0001", rationale="x")  # no kind
    ok = Verdict(classification="confirming", target_position_id="evals-0001", confirming_kind="redundant", rationale="x")
    assert ok.classification is Classification.confirming


def test_confirming_must_not_carry_reconciliation():
    with pytest.raises(ValidationError):
        Verdict(
            classification="confirming", target_position_id="evals-0001", confirming_kind="new-evidence",
            reconciliation=Reconciliation(type="empirical", reconciled=False, explanation="x"), rationale="x",
        )


def test_adversarial_requires_target_and_reconciliation():
    with pytest.raises(ValidationError):
        Verdict(classification="adversarial", target_position_id="evals-0001", rationale="x")  # no reconciliation
    with pytest.raises(ValidationError):
        Verdict(  # no target
            classification="adversarial",
            reconciliation=Reconciliation(type="empirical", reconciled=False, explanation="x"), rationale="x",
        )
    ok = Verdict(
        classification="adversarial", target_position_id="evals-0001",
        reconciliation=Reconciliation(type="definitional", reconciled=False, explanation="x"), rationale="x",
    )
    assert ok.reconciliation.is_open


def test_novel_forbids_target_kind_and_reconciliation():
    with pytest.raises(ValidationError):
        Verdict(classification="novel", target_position_id="evals-0001", rationale="x")
    ok = Verdict(classification="novel", canonical_statement="A fresh claim.", rationale="x")
    assert ok.target_position_id is None


def test_verdict_rejects_blank_rationale_and_extra_fields():
    with pytest.raises(ValidationError):
        Verdict(classification="novel", rationale="")
    with pytest.raises(ValidationError):
        Verdict(classification="novel", rationale="x", confidence=0.9)


# --- parse_verdict (tolerant JSON extraction) ------------------------------


def test_parse_verdict_plain():
    raw = json.dumps({"classification": "novel", "canonical_statement": "X.", "rationale": "no match"})
    assert parse_verdict(raw).classification is Classification.novel


def test_parse_verdict_from_code_fence_and_prose():
    payload = {"classification": "confirming", "target_position_id": "evals-0001",
               "confirming_kind": "new-evidence", "rationale": "same"}
    fenced = f"Here is my verdict:\n```json\n{json.dumps(payload)}\n```\nDone."
    v = parse_verdict(fenced)
    assert v.classification is Classification.confirming and v.target_position_id == "evals-0001"


def test_parse_verdict_non_json_raises():
    with pytest.raises(AdjudicationError):
        parse_verdict("I cannot decide.")


def test_parse_verdict_schema_invalid_raises():
    # confirming without a kind violates the verdict schema
    bad = json.dumps({"classification": "confirming", "target_position_id": "evals-0001", "rationale": "x"})
    with pytest.raises(AdjudicationError):
        parse_verdict(bad)


# --- OpusAdjudicator over a fake LLM ---------------------------------------


def test_opus_adjudicator_routes_to_opus_and_returns_parsed_verdict():
    raw = json.dumps({"classification": "confirming", "target_position_id": "evals-0001",
                      "confirming_kind": "new-evidence", "rationale": "same claim"})
    llm = FakeLLMClient(raw)
    adj = OpusAdjudicator(llm)
    verdict = adj.adjudicate(unit=_incoming(), candidates=[_candidate()])
    assert verdict.classification is Classification.confirming
    assert llm.calls[0]["model"] == "opus"                 # strongest tier for adjudication


def test_opus_adjudicator_honors_configured_model():
    raw = json.dumps({"classification": "novel", "canonical_statement": "X.", "rationale": "x"})
    llm = FakeLLMClient(raw)
    adj = OpusAdjudicator(llm, config=AdjudicationConfig(model="sonnet"))
    adj.adjudicate(unit=_incoming(), candidates=[_candidate()])
    assert llm.calls[0]["model"] == "sonnet"               # dev-tier override


def test_opus_adjudicator_rejects_target_outside_candidates():
    raw = json.dumps({"classification": "confirming", "target_position_id": "evals-9999",
                      "confirming_kind": "redundant", "rationale": "x"})
    adj = OpusAdjudicator(FakeLLMClient(raw))
    with pytest.raises(AdjudicationError):
        adj.adjudicate(unit=_incoming(), candidates=[_candidate("evals-0001")])


def test_opus_adjudicator_propagates_llm_error():
    from kb.extract import ExtractionError

    adj = OpusAdjudicator(FakeLLMClient(raises=ExtractionError("Agent SDK query failed")))
    with pytest.raises(ExtractionError):
        adj.adjudicate(unit=_incoming(), candidates=[_candidate()])


# --- the prompt: guardrail baked in, competing claims present --------------


def test_prompt_includes_incoming_unit_and_candidate_sources_with_dates():
    unit = _incoming(text="Evals are a waste of time.", video_id="vidC", date="2025-04-01")
    candidate = _candidate()
    _, user = build_adjudication_prompt(unit, [candidate])
    # the incoming unit is quoted and dated
    assert "Evals are a waste of time." in user
    assert "vidC" in user and "2025-04-01" in user
    # the candidate position and its source (with date) are present to weigh
    assert candidate.statement in user
    assert "build your own evals" in user and "2025-01-01" in user


def test_system_prompt_bakes_in_the_anti_manufactured_agreement_guardrail():
    text = SYSTEM_PROMPT.lower()
    # must force quoting competing claims with source + date
    assert "quote" in text and "date" in text
    # must make "unreconciled — genuinely open" a first-class, common outcome
    assert "unreconciled" in text
    # must forbid merging a claim with its negation
    assert "negation" in text or "never merge" in text
    # the three reconciliation types
    assert "empirical" in text and "definitional" in text and "contextual" in text
