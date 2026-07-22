"""Layers 4 & 5 — the per-topic knowledge base and the reconciliation engine.

Layer 4 (ticket #06) owns the *state* the pipeline accumulates: the position data model
and the per-topic store that persists it as flat JSON (canonical) + Markdown (rendered).

Layer 5 (ticket #08) is the core value on top of that state: the **two-stage matcher +
reconciliation engine**. Stage 1 retrieves candidate positions by local embedding
similarity; stage 2, the injected Opus adjudicator, judges each unit as confirming /
novel / adversarial — never merging on distance alone — and the engine applies the
verdict, re-flags maturity (ticket #09's policy, injected), and emits a typed diff the
digest (#10) renders directly.

Public surface::

    from kb.reconcile import (
        # Layer 4 — position data model + store
        Position, PositionSource, StatusEvent, Maturity, Alignment, KBStore, render_markdown,
        # Layer 5 — the reconciliation seam
        reconcile, ReconcileResult, ReconcileConfig, IncomingUnit,
        # stage 1 — retrieval (injected)
        CandidateRetriever, Candidate, LocalVectorRetriever,
        # stage 2 — adjudication (injected)
        Adjudicator, OpusAdjudicator, Verdict, Classification, parse_verdict,
        # typed diff the digest consumes
        Deltas, ConfirmedDelta, NetNewDelta, ContestedDelta, MaturityTransitionDelta,
        Citation, ConfirmingKind, Reconciliation, ReconciliationType,
        # maturity policy (config-driven, injected)
        compute_maturity, MaturityConfig,
    )
"""

from __future__ import annotations

from kb.reconcile.adjudicator import (
    AdjudicationConfig,
    AdjudicationError,
    Adjudicator,
    Classification,
    OpusAdjudicator,
    Verdict,
    build_adjudication_prompt,
    parse_verdict,
)
from kb.reconcile.deltas import (
    Citation,
    ConfirmedDelta,
    ConfirmingKind,
    ContestedDelta,
    Deltas,
    MaturityTransitionDelta,
    NetNewDelta,
    Reconciliation,
    ReconciliationType,
)
from kb.reconcile.engine import (
    ReconcileConfig,
    ReconcileError,
    ReconcileResult,
    load_reconcile_config,
    reconcile,
)
from kb.reconcile.incoming import IncomingUnit
from kb.reconcile.markdown import render_markdown
from kb.reconcile.maturity import (
    MaturityConfig,
    compute_maturity,
    load_maturity_config,
    maturity_reason,
)
from kb.reconcile.retrieval import Candidate, CandidateRetriever, LocalVectorRetriever
from kb.reconcile.schema import (
    Alignment,
    Maturity,
    Position,
    PositionSource,
    StatusEvent,
)
from kb.reconcile.store import KBStore

__all__ = [
    # -- Layer 4: data model + store --
    "Position",
    "PositionSource",
    "StatusEvent",
    "Maturity",
    "Alignment",
    "KBStore",
    "render_markdown",
    # -- Layer 5: the reconciliation seam --
    "reconcile",
    "ReconcileResult",
    "ReconcileConfig",
    "ReconcileError",
    "load_reconcile_config",
    "IncomingUnit",
    # -- stage 1: retrieval (injected) --
    "CandidateRetriever",
    "Candidate",
    "LocalVectorRetriever",
    # -- stage 2: adjudication (injected) --
    "Adjudicator",
    "OpusAdjudicator",
    "AdjudicationConfig",
    "AdjudicationError",
    "Verdict",
    "Classification",
    "parse_verdict",
    "build_adjudication_prompt",
    # -- typed diff the digest consumes --
    "Deltas",
    "ConfirmedDelta",
    "NetNewDelta",
    "ContestedDelta",
    "MaturityTransitionDelta",
    "Citation",
    "ConfirmingKind",
    "Reconciliation",
    "ReconciliationType",
    # -- maturity policy (config-driven, injected) --
    "compute_maturity",
    "maturity_reason",
    "MaturityConfig",
    "load_maturity_config",
]
