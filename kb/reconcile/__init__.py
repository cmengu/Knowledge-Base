"""Layer 4 — the per-topic knowledge base of positions (ticket #06).

This package owns the *state* the pipeline accumulates: the position data model and the
per-topic store that persists it as flat JSON (canonical) + Markdown (rendered). The
reconciliation *engine* that decides how incoming units update these positions — the
two-stage matcher and the Opus adjudicator (ticket #08) — builds on this substrate and
will land here alongside it. The **maturity state machine** that drives the flags
(ticket #09) lives here now: :func:`compute_maturity` (pure) and :func:`apply_maturity`,
driven by :class:`MaturityConfig` from ``config/maturity.yaml``.

Public surface::

    from kb.reconcile import (
        Position, PositionSource, StatusEvent,   # the position data model
        Maturity, Alignment,                     # the enums
        KBStore,                                  # per-topic load/save + CRUD
        render_markdown,                          # the human-readable view
        MaturityConfig, load_maturity_config,     # the maturity thresholds (#09)
        compute_maturity, apply_maturity,         # the maturity state machine (#09)
    )
"""

from __future__ import annotations

from kb.reconcile.markdown import render_markdown
from kb.reconcile.maturity import (
    MaturityConfig,
    apply_maturity,
    apply_maturity_batch,
    compute_maturity,
    load_maturity_config,
)
from kb.reconcile.schema import (
    Alignment,
    Maturity,
    Position,
    PositionSource,
    StatusEvent,
)
from kb.reconcile.store import KBStore

__all__ = [
    # data model
    "Position",
    "PositionSource",
    "StatusEvent",
    "Maturity",
    "Alignment",
    # store
    "KBStore",
    # rendering
    "render_markdown",
    # maturity state machine (#09)
    "MaturityConfig",
    "load_maturity_config",
    "compute_maturity",
    "apply_maturity",
    "apply_maturity_batch",
]
