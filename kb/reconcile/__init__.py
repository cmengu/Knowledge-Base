"""Layer 4 — the per-topic knowledge base of positions (ticket #06).

This package owns the *state* the pipeline accumulates: the position data model and the
per-topic store that persists it as flat JSON (canonical) + Markdown (rendered). The
reconciliation *engine* that decides how incoming units update these positions — the
two-stage matcher and the Opus adjudicator (ticket #08) — and the maturity state machine
that drives the flags (ticket #09) build on this substrate and will land in this package
alongside it.

Public surface::

    from kb.reconcile import (
        Position, PositionSource, StatusEvent,   # the position data model
        Maturity, Alignment,                     # the enums
        KBStore,                                  # per-topic load/save + CRUD
        render_markdown,                          # the human-readable view
    )
"""

from __future__ import annotations

from kb.reconcile.markdown import render_markdown
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
]
