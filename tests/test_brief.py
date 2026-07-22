"""Narrative topic-brief tests (issue #19).

The brief is the LLM-written lede atop each digest. Its LLM is an injected dependency, so —
like every other model seam in this repo — these tests run entirely offline with a scripted
fake and never make a live call. They pin the two things that matter:

* **The prompt carries the contradictions.** ``build_brief_prompt`` must embed every
  contested position's competing quotes with their source + date, so the "lead with
  contradictions" instruction has concrete material to lead with. Prompt *wording* is not
  otherwise asserted (that's non-deterministic model territory).
* **The word-count guard behaves.** A too-short/too-long first draft triggers exactly one
  corrective retry; whatever the retry returns is then accepted.

The HTML *placement* of the brief (first section; the position list collapsed beneath it;
the untouched ``brief=None`` path) is tested in ``test_digest.py`` alongside the renderer.
"""

from __future__ import annotations

import datetime as dt
import json

import pytest

from kb.config import FIXTURES_DIR
from kb.digest.brief import (
    BRIEF_MODEL,
    MAX_WORDS,
    MIN_WORDS,
    TopicBriefer,
    build_brief_prompt,
    word_count,
)
from kb.reconcile import (
    Citation,
    ContestedDelta,
    Deltas,
    Position,
    Reconciliation,
    ReconciliationType,
)

from tests.helpers import FakeLLMClient, ScriptedLLMClient

SAMPLE_DIR = FIXTURES_DIR / "reconcile-sample" / "evals"


@pytest.fixture
def sample_deltas() -> Deltas:
    return Deltas.model_validate(json.loads((SAMPLE_DIR / "deltas.json").read_text("utf-8")))


@pytest.fixture
def sample_positions() -> list[Position]:
    doc = json.loads((SAMPLE_DIR / "positions.json").read_text("utf-8"))
    return [Position.model_validate(p) for p in doc["positions"]]


def _prose(words: int) -> str:
    """A canned prose blob of exactly ``words`` words (the fake model's 'output')."""
    return " ".join(["word"] * words)


# --- prompt content ---------------------------------------------------------


def test_prompt_embeds_this_runs_contested_claims_with_sources(sample_deltas, sample_positions):
    _system, user = build_brief_prompt("evals", sample_positions, sample_deltas)
    contested = sample_deltas.newly_contested[0]
    # both competing quotes are in the prompt, each with its video id + date
    assert contested.supporting.quote.strip() in user
    assert contested.opposing.quote.strip() in user
    assert contested.supporting.video_id in user
    assert contested.opposing.video_id in user
    assert contested.supporting.date.isoformat() in user
    assert contested.opposing.date.isoformat() in user
    # and the typed reconciliation outcome is handed over, not hidden
    assert contested.reconciliation.type.value in user


def test_prompt_embeds_standing_contested_positions_both_stances(sample_positions):
    """Positions already contested in the KB must be surfaced for the brief to lead with,
    even on a run that added no new contest."""
    standing = [p for p in sample_positions if p.is_contested]
    assert standing, "sample KB should have standing contested positions"
    _system, user = build_brief_prompt("evals", sample_positions, Deltas())
    for p in standing:
        assert p.statement in user
        # each contested position contributes both a supporting and an opposing quote
        assert p.supporting_sources[0].quote.strip() in user
        assert p.opposing_sources[0].quote.strip() in user


def test_system_prompt_orders_contradictions_first():
    system, _user = build_brief_prompt("evals", None, Deltas())
    assert "LEAD WITH CONTRADICTIONS" in system
    # the unresolved outcome is named as a valid, expected answer (anti-manufactured-consensus)
    assert "UNRESOLVED" in system or "unresolved" in system


def test_prompt_lists_current_state_and_run_changes():
    deltas = Deltas(
        newly_contested=[
            ContestedDelta(
                position_id="evals-0001",
                position_statement="System eval beats model eval.",
                supporting=Citation(
                    unit_id="a#0", video_id="vidA", date=dt.date(2025, 5, 1),
                    quote="measure the whole system", statement="system",
                ),
                opposing=Citation(
                    unit_id="b#0", video_id="vidB", date=dt.date(2025, 6, 1),
                    quote="model-level metrics are enough", statement="model",
                ),
                reconciliation=Reconciliation(
                    type=ReconciliationType.empirical, reconciled=False,
                    explanation="they disagree on what to measure",
                ),
                became_contested=True,
            )
        ],
    )
    _system, user = build_brief_prompt("evals", None, deltas)
    assert "measure the whole system" in user
    assert "model-level metrics are enough" in user
    assert "vidA" in user and "vidB" in user


# --- the briefer: happy path + word-count guard -----------------------------


def test_briefer_returns_prose_and_uses_opus(sample_deltas, sample_positions):
    canned = _prose(600)
    client = FakeLLMClient(response=canned)
    briefer = TopicBriefer(client)
    out = briefer.brief(topic="evals", positions=sample_positions, deltas=sample_deltas)
    assert out == canned
    assert len(client.calls) == 1                       # in-range → no retry
    assert client.calls[0]["model"] == BRIEF_MODEL == "claude-opus-4-8"


def test_briefer_retries_once_when_too_short_then_accepts_good(sample_positions):
    short, good = _prose(MIN_WORDS - 50), _prose(700)
    client = ScriptedLLMClient([short, good])
    out = TopicBriefer(client).brief(topic="evals", positions=sample_positions, deltas=Deltas())
    assert out == good
    assert len(client.calls) == 2                       # exactly one corrective retry
    # the retry prompt carries a corrective instruction that the first did not
    assert "too short" in client.calls[1]["prompt"]
    assert "too short" not in client.calls[0]["prompt"]


def test_briefer_retries_once_when_too_long(sample_positions):
    long, good = _prose(MAX_WORDS + 100), _prose(650)
    client = ScriptedLLMClient([long, good])
    out = TopicBriefer(client).brief(topic="evals", positions=sample_positions, deltas=Deltas())
    assert out == good
    assert len(client.calls) == 2
    assert "too long" in client.calls[1]["prompt"]


def test_briefer_accepts_still_bad_output_after_one_retry(caplog, sample_positions):
    """Guard is best-effort: after one retry, whatever came back is returned (with a warning),
    never a failure — a slightly off-length brief beats a run with no brief."""
    short1, short2 = _prose(100), _prose(120)
    client = ScriptedLLMClient([short1, short2])
    with caplog.at_level("WARNING"):
        out = TopicBriefer(client).brief(topic="evals", positions=sample_positions, deltas=Deltas())
    assert out == short2
    assert len(client.calls) == 2                       # only one retry, then accept
    assert any("outside" in r.message or "outside" in r.getMessage() for r in caplog.records)


def test_word_count_is_whitespace_delimited():
    assert word_count("one two three") == 3
    assert word_count("  padded   words  here ") == 3
    assert word_count("") == 0
