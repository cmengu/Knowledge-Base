"""The reconciliation engine — the single highest-value seam (ticket #08, spec).

    reconcile(incoming_units, topic_kb) -> (updated_kb, deltas)

Both matcher stages are injected fakes (a scripted retriever + a scripted adjudicator), so
these tests are fully deterministic and make no embedding-model, vector-DB, or LLM call.
They assert *external behavior*: the classification outcomes, the new/updated positions,
the contested-both-stances capture, and the emitted deltas — never prompt wording or model
internals.
"""

from __future__ import annotations

import datetime as dt

import pytest

from kb.extract import Unit
from kb.reconcile import (
    ConfirmingKind,
    IncomingUnit,
    KBStore,
    Maturity,
    PositionSource,
    Reconciliation,
    ReconciliationType,
    ReconcileError,
    Verdict,
    reconcile,
)
from tests.helpers import FakeAdjudicator, FakeRetriever

NOW = dt.datetime(2025, 6, 1, 9, 0)


# --- builders --------------------------------------------------------------


def make_unit(text: str, *, unit_id: str, stance: str = "affirms", type: str = "claim") -> Unit:
    return Unit(
        type=type, text=text, raw_quote=text, timestamp=1.0, stance=stance, unit_id=unit_id
    )


def make_incoming(
    text: str, *, video_id: str, date: str, index: int = 0, unit_id: str | None = None, **kw
) -> IncomingUnit:
    uid = unit_id or f"{video_id}#{index}"
    return IncomingUnit(unit=make_unit(text, unit_id=uid, **kw), video_id=video_id, date=date)


def novel(statement: str | None = None, *, rationale: str = "no match") -> Verdict:
    return Verdict(classification="novel", canonical_statement=statement, rationale=rationale)


def confirming(target: str, *, kind: str = "new-evidence", rationale: str = "same claim") -> Verdict:
    return Verdict(
        classification="confirming", target_position_id=target, confirming_kind=kind, rationale=rationale
    )


def adversarial(
    target: str,
    *,
    type: str = "empirical",
    reconciled: bool = False,
    explanation: str = "they measured different things",
    rationale: str = 'existing says "build your own"; new says "waste of time"',
) -> Verdict:
    return Verdict(
        classification="adversarial",
        target_position_id=target,
        reconciliation=Reconciliation(type=type, reconciled=reconciled, explanation=explanation),
        rationale=rationale,
    )


def seed_source(
    *, unit_id="seed#0", video_id="seed", date="2025-01-01", alignment="supporting",
    stance="affirms", quote="you should build your own evals", statement="Build your own evals.",
) -> PositionSource:
    return PositionSource(
        unit_id=unit_id, video_id=video_id, date=date, alignment=alignment,
        stance=stance, quote=quote, statement=statement,
    )


def seeded_store(tmp_path) -> KBStore:
    """A store with one open, single-source supporting position ``evals-0001``."""
    store = KBStore("evals", root=tmp_path)
    store.create_position(
        statement="You should build your own task-specific evals.",
        at=NOW, first_source=seed_source(), reason="seed",
    )
    return store


def converging_store(tmp_path) -> KBStore:
    """A store with a converging ``evals-0001`` (3 distinct videos over >3 months)."""
    store = KBStore("evals", root=tmp_path)
    pos = store.create_position(
        statement="You should build your own task-specific evals.",
        at=NOW, first_source=seed_source(unit_id="v1#0", video_id="v1", date="2025-01-01"),
        reason="first",
    )
    pos.add_source(seed_source(unit_id="v2#0", video_id="v2", date="2025-03-01"), at=NOW)
    pos.record_transition(Maturity.emerging_trend, at=NOW, reason="second source")
    pos.add_source(seed_source(unit_id="v3#0", video_id="v3", date="2025-05-01"), at=NOW)
    pos.record_transition(Maturity.converging, at=NOW, reason="third over >3 months")
    return store


# --- novel -----------------------------------------------------------------


def test_novel_opens_a_new_open_position(tmp_path):
    store = KBStore("evals", root=tmp_path)
    inc = make_incoming("Small models are good enough for most tasks.", video_id="vidA", date="2025-05-01")
    retriever = FakeRetriever(default_ids=[])         # nothing to compare against
    adj = FakeAdjudicator()                            # must NOT be consulted

    updated, deltas = reconcile([inc], store, retriever=retriever, adjudicator=adj, now=NOW)

    assert adj.calls == []                             # empty candidates -> novel, no judgment spent
    assert len(updated) == 1
    pos = updated.get("evals-0001")
    assert pos.maturity is Maturity.open_question
    assert pos.statement == "Small models are good enough for most tasks."
    assert pos.unit_ids == ["vidA#0"]
    assert pos.supporting_sources and not pos.opposing_sources
    assert len(deltas.net_new) == 1
    assert deltas.net_new[0].position_id == "evals-0001"
    assert deltas.net_new[0].citation.video_id == "vidA"
    assert deltas.newly_confirmed == [] and deltas.newly_contested == []
    assert deltas.maturity_transitions == []           # a fresh 1-source position stays open


def test_never_merges_on_distance_alone(tmp_path):
    # A look-alike candidate IS retrieved, but the adjudicator judges the unit novel — the
    # engine opens a NEW position and never merges into the neighbor on similarity.
    store = seeded_store(tmp_path)
    inc = make_incoming("Latency budgets matter for agents.", video_id="vidB", date="2025-06-01")
    retriever = FakeRetriever(default_ids=["evals-0001"])
    adj = FakeAdjudicator({"vidB#0": novel("Latency budgets matter for agents.")})

    updated, deltas = reconcile([inc], store, retriever=retriever, adjudicator=adj, now=NOW)

    assert adj.calls == [("vidB#0", ["evals-0001"])]   # it DID weigh the candidate...
    assert len(updated) == 2                            # ...and still opened a new position
    assert updated.get("evals-0001").unit_ids == ["seed#0"]   # the look-alike untouched
    assert len(deltas.net_new) == 1 and deltas.newly_confirmed == []


# --- confirming ------------------------------------------------------------


def test_confirming_new_evidence_adds_supporting_source_and_ratchets_maturity(tmp_path):
    store = seeded_store(tmp_path)
    inc = make_incoming("Definitely build evals yourself.", video_id="vidB", date="2025-03-01")
    retriever = FakeRetriever(default_ids=["evals-0001"])
    adj = FakeAdjudicator({"vidB#0": confirming("evals-0001", kind="new-evidence")})

    updated, deltas = reconcile([inc], store, retriever=retriever, adjudicator=adj, now=NOW)

    pos = updated.get("evals-0001")
    assert pos.unit_ids == ["seed#0", "vidB#0"]
    assert len(pos.supporting_sources) == 2 and not pos.opposing_sources
    assert len(deltas.newly_confirmed) == 1
    d = deltas.newly_confirmed[0]
    assert d.kind is ConfirmingKind.new_evidence and d.position_id == "evals-0001"
    assert d.citation.video_id == "vidB"
    # two distinct videos now agree -> emerging, and the transition is recorded
    assert pos.maturity is Maturity.emerging_trend
    assert len(deltas.maturity_transitions) == 1
    t = deltas.maturity_transitions[0]
    assert (t.from_maturity, t.to_maturity) == ("open-question", "emerging-trend")
    assert t.trigger_unit_id == "vidB#0"


def test_confirming_redundant_is_flagged_and_does_not_ratchet(tmp_path):
    store = seeded_store(tmp_path)
    # a restatement from the SAME video ("seed") — no new independent source
    inc = make_incoming("Build your own evals, once more.", video_id="seed", date="2025-01-01", unit_id="seed#9")
    retriever = FakeRetriever(default_ids=["evals-0001"])
    adj = FakeAdjudicator({"seed#9": confirming("evals-0001", kind="redundant")})

    updated, deltas = reconcile([inc], store, retriever=retriever, adjudicator=adj, now=NOW)

    assert deltas.newly_confirmed[0].kind is ConfirmingKind.redundant
    assert updated.get("evals-0001").maturity is Maturity.open_question   # still one distinct video
    assert deltas.maturity_transitions == []


# --- adversarial (the guardrail seam) --------------------------------------


def test_adversarial_captures_both_stances_types_reconciliation_and_contests(tmp_path):
    store = seeded_store(tmp_path)
    inc = make_incoming(
        "Building your own evals is a waste of time.", video_id="vidC", date="2025-04-01", stance="denies"
    )
    retriever = FakeRetriever(default_ids=["evals-0001"])
    adj = FakeAdjudicator(
        {"vidC#0": adversarial("evals-0001", type="empirical", reconciled=False,
                               explanation="one measured cost, the other measured quality")}
    )

    updated, deltas = reconcile([inc], store, retriever=retriever, adjudicator=adj, now=NOW)

    pos = updated.get("evals-0001")
    # both stances are kept, quoted, dated
    assert pos.is_contested
    assert len(pos.supporting_sources) == 1 and len(pos.opposing_sources) == 1
    assert pos.maturity is Maturity.contested

    assert len(deltas.newly_contested) == 1
    c = deltas.newly_contested[0]
    assert c.supporting.video_id == "seed" and c.opposing.video_id == "vidC"
    assert c.supporting.date == dt.date(2025, 1, 1) and c.opposing.date == dt.date(2025, 4, 1)
    assert c.supporting.quote != c.opposing.quote      # genuinely two different claims
    assert c.reconciliation.type is ReconciliationType.empirical
    assert c.reconciliation.reconciled is False and c.reconciliation.is_open
    assert c.became_contested is True

    # the reconciliation attempt is durably recorded in the status history
    event = pos.status_history[-1]
    assert event.to_maturity is Maturity.contested
    assert "empirical" in event.reason and "unreconciled — genuinely open" in event.reason
    assert event.trigger_unit_id == "vidC#0"
    # and surfaced as a maturity transition
    assert any(t.to_maturity == "contested" for t in deltas.maturity_transitions)


def test_adversarial_resets_a_converging_position_to_contested(tmp_path):
    store = converging_store(tmp_path)
    assert store.get("evals-0001").maturity is Maturity.converging
    inc = make_incoming("Evals are overrated for small teams.", video_id="vidX", date="2025-06-10", stance="denies")
    retriever = FakeRetriever(default_ids=["evals-0001"])
    adj = FakeAdjudicator({"vidX#0": adversarial("evals-0001", type="contextual")})

    updated, deltas = reconcile([inc], store, retriever=retriever, adjudicator=adj, now=NOW)

    pos = updated.get("evals-0001")
    assert pos.maturity is Maturity.contested          # a single dissent reopened it
    t = [t for t in deltas.maturity_transitions if t.to_maturity == "contested"][0]
    assert t.from_maturity == "converging"
    assert deltas.newly_contested[0].reconciliation.type is ReconciliationType.contextual


# --- idempotency + intra-batch ---------------------------------------------


def test_rerunning_the_same_batch_is_a_noop(tmp_path):
    store = KBStore("evals", root=tmp_path)
    inc = make_incoming("Agents need their own evals.", video_id="vidA", date="2025-05-01")
    reconcile([inc], store, retriever=FakeRetriever(default_ids=[]), adjudicator=FakeAdjudicator(), now=NOW)
    assert len(store) == 1

    # second pass: the unit is already a source -> skipped before retrieval, empty deltas
    retriever, adj = FakeRetriever(default_ids=[]), FakeAdjudicator()
    _, deltas = reconcile([inc], store, retriever=retriever, adjudicator=adj, now=NOW)
    assert len(store) == 1
    assert deltas.is_empty
    assert retriever.calls == [] and adj.calls == []


def test_intra_batch_second_unit_confirms_first_units_new_position(tmp_path):
    store = KBStore("evals", root=tmp_path)
    a = make_incoming("Agents need their own evals.", video_id="vidA", date="2025-05-01")
    b = make_incoming("Yes, agents really do need evals.", video_id="vidB", date="2025-06-01")
    # a: retriever finds nothing -> novel (opens evals-0001). b: retriever now finds evals-0001.
    retriever = FakeRetriever(
        {"Agents need their own evals.": [], "Yes, agents really do need evals.": ["evals-0001"]}
    )
    adj = FakeAdjudicator({"vidB#0": confirming("evals-0001", kind="new-evidence")})

    updated, deltas = reconcile([a, b], store, retriever=retriever, adjudicator=adj, now=NOW)

    assert len(updated) == 1                           # b folded into a's position, not a 2nd one
    assert updated.get("evals-0001").unit_ids == ["vidA#0", "vidB#0"]
    assert len(deltas.net_new) == 1 and len(deltas.newly_confirmed) == 1
    # b was only adjudicable because a added the position mid-batch (a itself went via empty retrieval)
    assert adj.calls == [("vidB#0", ["evals-0001"])]


# --- error + result shape --------------------------------------------------


def test_verdict_targeting_unknown_position_raises(tmp_path):
    store = seeded_store(tmp_path)
    inc = make_incoming("Something.", video_id="vidZ", date="2025-05-01")
    adj = FakeAdjudicator({"vidZ#0": confirming("evals-9999", kind="redundant")})   # bogus target
    with pytest.raises(ReconcileError):
        reconcile([inc], store, retriever=FakeRetriever(default_ids=["evals-0001"]), adjudicator=adj, now=NOW)


def test_result_unpacks_as_tuple_and_returns_the_same_store(tmp_path):
    store = KBStore("evals", root=tmp_path)
    result = reconcile([], store, retriever=FakeRetriever(default_ids=[]), adjudicator=FakeAdjudicator(), now=NOW)
    assert result.updated_kb is store
    updated, deltas = result                           # NamedTuple unpacks as (updated_kb, deltas)
    assert updated is store and deltas.is_empty


def test_empty_batch_yields_empty_deltas(tmp_path):
    store = seeded_store(tmp_path)
    _, deltas = reconcile([], store, retriever=FakeRetriever(), adjudicator=FakeAdjudicator(), now=NOW)
    assert deltas.is_empty and deltas.total_changes() == 0
    assert len(store) == 1                              # untouched


# --- persistence integration -----------------------------------------------


def test_reconciled_contested_kb_saves_and_reloads(tmp_path):
    store = seeded_store(tmp_path)
    inc = make_incoming("Building your own evals is a waste.", video_id="vidC", date="2025-04-01", stance="denies")
    adj = FakeAdjudicator({"vidC#0": adversarial("evals-0001")})
    reconcile([inc], store, retriever=FakeRetriever(default_ids=["evals-0001"]), adjudicator=adj, now=NOW)
    store.save()

    reloaded = KBStore.load("evals", root=tmp_path)
    pos = reloaded.get("evals-0001")
    assert pos.is_contested
    assert len(pos.supporting_sources) == 1 and len(pos.opposing_sources) == 1
    assert pos.maturity is Maturity.contested


def test_reconcile_against_committed_seed_kb_read_only():
    # Loads the committed sample KB (fixtures/sample-kb/evals) and reconciles a fixture unit
    # against it WITHOUT saving — proves the engine works on realistic positions, disk
    # untouched. The illustrative sample lives under fixtures/ so kb-data/ holds only the
    # pipeline's own real run output.
    from kb.config import FIXTURES_DIR

    store = KBStore.load("evals", root=FIXTURES_DIR / "sample-kb")
    before = len(store)
    assert before >= 1                                 # the seed KB has positions
    inc = make_incoming("A brand-new eval idea nobody has stated.", video_id="vidNew", date="2025-10-01")
    retriever = FakeRetriever(default_ids=["evals-0001"])
    adj = FakeAdjudicator({"vidNew#0": novel("A brand-new eval idea.")})

    updated, deltas = reconcile([inc], store, retriever=retriever, adjudicator=adj, now=NOW)

    assert len(updated) == before + 1
    assert len(deltas.net_new) == 1
    assert deltas.net_new[0].citation.video_id == "vidNew"
