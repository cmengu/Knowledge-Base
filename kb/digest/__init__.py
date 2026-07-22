"""The digest layer — the pipeline's primary output surface (ticket #10).

On every run the pipeline renders one rich, self-contained HTML "Reader's Digest" of what
changed in the knowledge base since the last run. The digest *is* a diff of the KB: it
consumes the typed :class:`~kb.reconcile.deltas.Deltas` the reconciliation engine (#08)
emits and turns it into a morning-readable editorial briefing — colour-coded delta labels,
HTML/CSS diagrams and cards, both stances of every contest quoted with source + date, and
citations on anything trend-like. It is never an empty file: a no-changes run still renders
a real page with the current state of the field.

Public surface::

    from kb.digest import render_digest, write_digest, digest_filename, DIGESTS_DIR

* :func:`render_digest` — ``Deltas → HTML string`` (the pure seam the tests exercise);
* :func:`write_digest`  — render + write ``digests/YYYY-MM-DD-<topic>.html`` atomically;
* :func:`digest_filename` — the deterministic filename from an injected date;
* :data:`DIGESTS_DIR` — the default output directory (``digests/`` at the repo root);
* :class:`TopicBriefer` — the optional LLM-written narrative brief (issue #19,
  :mod:`kb.digest.brief`) that leads with contradictions; its prose is passed to
  :func:`render_digest` via the optional ``brief=`` argument (``None`` = today's output).

Rendering stays pure and deterministic — the model call lives in :class:`TopicBriefer`, and
``render_digest`` only ever takes the finished string — so the digest is testable offline.

Look-and-feel (CSS + the tiny progressive-enhancement script) lives in
:mod:`kb.digest.theme`; :mod:`kb.digest.render` owns structure and prose.
"""

from __future__ import annotations

from kb.digest.brief import BriefConfig, TopicBriefer, build_brief_prompt
from kb.digest.render import DIGESTS_DIR, digest_filename, render_digest, write_digest

__all__ = [
    "render_digest",
    "write_digest",
    "digest_filename",
    "DIGESTS_DIR",
    "TopicBriefer",
    "BriefConfig",
    "build_brief_prompt",
]
