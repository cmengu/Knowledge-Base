"""The reconciliation engine — the two-stage matcher tying Layers 4 and 5 together (#08).

This is the core value of the whole pipeline and its single highest-value seam:

    reconcile(incoming_units, topic_kb) -> (updated_kb, deltas)

For each incoming unit, in order:

1. **Stage 1 (retrieve).** Ask the injected :class:`~kb.reconcile.retrieval.CandidateRetriever`
   for the top-k positions closest to the unit's text. If none clear the floor the unit is
   novel by construction — there is nothing to compare against — and no judgment is spent.
2. **Stage 2 (adjudicate).** Ask the injected :class:`~kb.reconcile.adjudicator.Adjudicator`
   to classify the unit against those candidates as confirming / novel / adversarial. The
   engine *never* merges on the retrieval score alone — the verdict decides.
3. **Apply.** Mutate the topic's :class:`~kb.reconcile.store.KBStore` accordingly and record
   the change in a typed :class:`~kb.reconcile.deltas.Deltas`:
   * confirming  → attach the unit as a supporting source (``redundant`` vs ``new-evidence``);
   * novel       → open a fresh ``open-question`` position;
   * adversarial → attach the unit as an *opposing* source (both stances now kept), record
     the typed reconciliation attempt, and let maturity reset the position to contested.
4. **Re-flag.** Recompute the position's maturity via the injected ``compute_maturity``
   policy and, if it moved, record the transition (into the status history and the deltas).

Two behaviors make repeated runs safe and batches self-consistent:

* **Idempotent.** A unit whose id is already a source somewhere in the KB is skipped, so
  re-reconciling the same batch is a no-op that changes nothing and emits empty deltas.
* **Intra-batch.** The KB is updated as the batch is processed, so a later unit can confirm
  or contest a position an earlier unit in the *same* batch just opened — the earliest
  stater founds the position, the rest reconcile against it.

Both matcher stages and the maturity policy are injected, so this module — and its tests —
depend on no embedding model, vector database, or LLM. Production wires the real BGE-M3
retriever and the Opus adjudicator; tests wire fakes.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import NamedTuple

from pydantic import BaseModel, ConfigDict, Field

from kb.config import CONFIG_DIR, load_yaml
from kb.reconcile.adjudicator import Adjudicator, Classification, Verdict
from kb.reconcile.deltas import (
    Citation,
    ConfirmedDelta,
    ContestedDelta,
    Deltas,
    MaturityTransitionDelta,
    NetNewDelta,
)
from kb.reconcile.incoming import IncomingUnit
from kb.reconcile.maturity import MaturityConfig, compute_maturity as default_compute_maturity
from kb.reconcile.maturity import maturity_reason
from kb.reconcile.retrieval import CandidateRetriever
from kb.reconcile.schema import Alignment, Maturity, Position
from kb.reconcile.store import KBStore

__all__ = [
    "reconcile",
    "ReconcileResult",
    "ReconcileConfig",
    "ReconcileError",
    "MaturityPolicy",
    "load_reconcile_config",
]

# The maturity policy is injected so ticket #09 can refine it without touching the engine.
MaturityPolicy = Callable[..., Maturity]


class ReconcileError(Exception):
    """Raised when a verdict cannot be applied — e.g. it targets a position not in the KB."""


class ReconcileConfig(BaseModel):
    """Engine knobs (loaded from ``config/reconciliation.yaml``).

    ``adjudicator_model`` is carried here so the whole reconciliation step is configured in
    one file; the engine itself only reads ``top_k`` and ``min_score`` (the retrieval
    narrowing), while the caller uses ``adjudicator_model`` to wire the Opus adjudicator.
    """

    model_config = ConfigDict(extra="forbid")

    top_k: int = Field(
        default=5, ge=1, description="How many candidate positions stage 1 retrieves per unit."
    )
    min_score: float = Field(
        default=0.30,
        ge=0.0,
        le=1.0,
        description="Cosine floor below which a candidate is too unrelated to adjudicate.",
    )
    adjudicator_model: str = Field(
        default="opus",
        description="Agent SDK model for stage-2 adjudication (Opus per the spec).",
    )


class ReconcileResult(NamedTuple):
    """The engine's output: the mutated store and the run's typed diff.

    A :class:`~typing.NamedTuple` so it unpacks as ``(updated_kb, deltas)`` — the seam the
    spec and ticket name — while also being addressable as ``.updated_kb`` / ``.deltas``.
    """

    updated_kb: KBStore
    deltas: Deltas


def load_reconcile_config(path: str | Path | None = None) -> ReconcileConfig:
    """Load :class:`ReconcileConfig` from YAML (defaults when the file is absent)."""

    path = Path(path) if path is not None else CONFIG_DIR / "reconciliation.yaml"
    if not path.exists():
        return ReconcileConfig()
    return ReconcileConfig.model_validate(load_yaml(path) or {})


def reconcile(
    incoming_units: Sequence[IncomingUnit],
    topic_kb: KBStore,
    *,
    retriever: CandidateRetriever,
    adjudicator: Adjudicator,
    now: dt.datetime | None = None,
    config: ReconcileConfig | None = None,
    maturity_config: MaturityConfig | None = None,
    compute_maturity: MaturityPolicy = default_compute_maturity,
) -> ReconcileResult:
    """Reconcile ``incoming_units`` into ``topic_kb`` and return ``(updated_kb, deltas)``.

    Mutates ``topic_kb`` in place (and returns it) — persistence stays explicit: the caller
    calls :meth:`KBStore.save` when the batch is done. ``now`` is the run timestamp stamped
    on every new source and status transition (defaults to the wall clock; tests pass a
    fixed value for determinism).
    """

    now = now or dt.datetime.now()
    config = config or ReconcileConfig()
    maturity_config = maturity_config or MaturityConfig()
    deltas = Deltas()

    # Idempotency: every unit already recorded as a source anywhere in the KB is skipped,
    # so re-running a batch changes nothing.
    seen_unit_ids: set[str] = {uid for p in topic_kb for uid in p.unit_ids}

    for incoming in incoming_units:
        unit_id = incoming.unit_id
        if unit_id in seen_unit_ids:
            continue
        seen_unit_ids.add(unit_id)

        candidates = retriever.top_k(
            query_text=incoming.unit.text,
            positions=topic_kb.positions(),
            k=config.top_k,
            min_score=config.min_score,
        )
        candidate_positions = [c.position for c in candidates]

        if not candidate_positions:
            # Nothing semantically near it — novel by construction, no adjudication needed.
            verdict = Verdict(
                classification=Classification.novel,
                canonical_statement=incoming.unit.text,
                rationale="no semantically similar existing position to compare against",
            )
        else:
            verdict = adjudicator.adjudicate(unit=incoming, candidates=candidate_positions)

        _apply(verdict, incoming, topic_kb, deltas, now, maturity_config, compute_maturity)

    return ReconcileResult(updated_kb=topic_kb, deltas=deltas)


# --- verdict application ---------------------------------------------------


def _apply(
    verdict: Verdict,
    incoming: IncomingUnit,
    store: KBStore,
    deltas: Deltas,
    now: dt.datetime,
    maturity_config: MaturityConfig,
    compute_maturity: MaturityPolicy,
) -> None:
    if verdict.classification is Classification.novel:
        _apply_novel(verdict, incoming, store, deltas, now, maturity_config, compute_maturity)
    elif verdict.classification is Classification.confirming:
        _apply_confirming(verdict, incoming, store, deltas, now, maturity_config, compute_maturity)
    else:
        _apply_adversarial(verdict, incoming, store, deltas, now, maturity_config, compute_maturity)


def _apply_novel(
    verdict, incoming, store, deltas, now, maturity_config, compute_maturity
) -> None:
    statement = (verdict.canonical_statement or incoming.unit.text).strip()
    position = store.create_position(
        statement=statement,
        at=now,
        first_source=incoming.to_source(Alignment.supporting),
        reason="opened as a new open position (novel unit)",
    )
    deltas.net_new.append(
        NetNewDelta(
            position_id=position.position_id,
            statement=position.statement,
            citation=_incoming_citation(incoming),
        )
    )
    _reflag(position, incoming, deltas, now, maturity_config, compute_maturity)


def _apply_confirming(
    verdict, incoming, store, deltas, now, maturity_config, compute_maturity
) -> None:
    position = _require_target(verdict, store)
    position.add_source(incoming.to_source(Alignment.supporting), at=now)
    deltas.newly_confirmed.append(
        ConfirmedDelta(
            position_id=position.position_id,
            position_statement=position.statement,
            kind=verdict.confirming_kind,
            citation=_incoming_citation(incoming),
        )
    )
    _reflag(position, incoming, deltas, now, maturity_config, compute_maturity)


def _apply_adversarial(
    verdict, incoming, store, deltas, now, maturity_config, compute_maturity
) -> None:
    position = _require_target(verdict, store)
    was_contested = position.is_contested
    position.add_source(incoming.to_source(Alignment.opposing), at=now)

    # Durably record the reconciliation attempt in the transition reason (the position
    # schema is reused as-is; the structured attempt travels in the delta below).
    reconciliation = verdict.reconciliation
    outcome = "reconciled" if reconciliation.reconciled else "unreconciled — genuinely open"
    reason = (
        f"contested — {reconciliation.type.value} disagreement, {outcome}: "
        f"{reconciliation.explanation}"
    )
    _reflag(
        position, incoming, deltas, now, maturity_config, compute_maturity, override_reason=reason
    )

    supporting = position.supporting_sources
    deltas.newly_contested.append(
        ContestedDelta(
            position_id=position.position_id,
            position_statement=position.statement,
            supporting=Citation.from_source(supporting[0])
            if supporting
            else _incoming_citation(incoming),
            opposing=_incoming_citation(incoming),
            reconciliation=reconciliation,
            became_contested=(not was_contested) and position.is_contested,
        )
    )


def _reflag(
    position: Position,
    incoming: IncomingUnit,
    deltas: Deltas,
    now: dt.datetime,
    maturity_config: MaturityConfig,
    compute_maturity: MaturityPolicy,
    *,
    override_reason: str | None = None,
) -> None:
    """Recompute the position's maturity and record a transition if it moved."""

    new_flag = compute_maturity(position, now=now, config=maturity_config)
    reason = override_reason or maturity_reason(position, new_flag)
    event = position.record_transition(
        new_flag, at=now, reason=reason, trigger_unit_id=incoming.unit_id
    )
    if event is not None:
        deltas.maturity_transitions.append(
            MaturityTransitionDelta(
                position_id=position.position_id,
                statement=position.statement,
                from_maturity=event.from_maturity.value if event.from_maturity else "—",
                to_maturity=event.to_maturity.value,
                reason=event.reason,
                trigger_unit_id=event.trigger_unit_id,
            )
        )


def _require_target(verdict: Verdict, store: KBStore) -> Position:
    position = store.get(verdict.target_position_id)
    if position is None:
        raise ReconcileError(
            f"verdict targets position {verdict.target_position_id!r}, which is not in the KB"
        )
    return position


def _incoming_citation(incoming: IncomingUnit) -> Citation:
    unit = incoming.unit
    return Citation(
        unit_id=incoming.unit_id,
        video_id=incoming.video_id,
        date=incoming.date,
        quote=unit.raw_quote,
        statement=unit.text,
    )
