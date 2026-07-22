"""Render a reconciliation run's typed :class:`~kb.reconcile.Deltas` as an HTML digest.

This is the pipeline's **primary output surface** (ticket #10). On every run the system
emits one rich, self-contained HTML "Reader's Digest" — morning-readable, with visuals —
of what changed in the knowledge base since the last run. The digest *is* a diff of the
KB, so this module consumes the typed :class:`~kb.reconcile.deltas.Deltas` the
reconciliation engine (#08) emits and turns it into an editorial briefing, adapting the
``/explain-diff-html`` skill's style (Kleppmann-clear prose framing around a diff view,
HTML/CSS diagrams and cards, colour-coded delta labels — never ASCII art).

The single public seam is :func:`render_digest` — ``Deltas → HTML string`` — with
:func:`write_digest` the thin file-writing wrapper the pipeline calls. Everything the page
needs is baked in (CSS + a tiny progressive-enhancement script from :mod:`kb.digest.theme`),
so the output makes **no external request** and opens correctly from disk or an email.

Three properties are load-bearing, each a spec requirement:

* **Never an empty file** (spec user story 22). A run that changed nothing still renders a
  real page — a calm "no changes" hero plus the *current state of the knowledge base* — so
  the reader always has something to read. :func:`render_digest` guarantees a non-trivial
  document for empty deltas.
* **Both stances, quoted, dated** (user stories 24, 26). A newly contested position renders
  as a two-column stance card holding *both* competing quotes with source + date and the
  typed reconciliation attempt. Minority/contested views are kept visually separate — the
  digest critiques, it does not smooth into a forecast.
* **Trends are citation-bound** (user story 25). Every maturity move cites the specific
  videos + dates behind it, pulled from the run's own citations (and, when the current KB
  is supplied, the full supporting timeline) — so a "where it's going" claim is never handed
  over on thin air.

**Determinism.** The renderer is pure and never touches the wall clock: the run ``date`` is
injected by the caller (the filename is ``digests/YYYY-MM-DD-<topic>.html``), text is
composed from the deltas, and any set-derived ordering is sorted. The same inputs always
produce byte-identical HTML, which is what lets the digest be tested without a live run.
"""

from __future__ import annotations

import datetime as dt
import html
import os
from collections.abc import Iterable, Sequence
from pathlib import Path

from kb.config import DIGESTS_DIR
from kb.reconcile import (
    Citation,
    ConfirmedDelta,
    ContestedDelta,
    Deltas,
    KBStore,
    MaturityTransitionDelta,
    NetNewDelta,
    Position,
)
from kb.digest.theme import (
    CSS,
    DELTA_LABEL,
    JS,
    MATURITY_BADGE,
    MATURITY_CLASS,
    MATURITY_ORDER,
)

__all__ = ["render_digest", "write_digest", "digest_filename", "DIGESTS_DIR"]

_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
_NUM_WORD = ("no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")

# Ordering for the "state of the field" list: live debates first (they need attention),
# then most-settled down to least. Mirrors the reader's priorities, not the ladder.
_STATE_RANK = {"contested": 0, "solved": 1, "converging": 2, "emerging-trend": 3, "open-question": 4}


# ----------------------------------------------------------------------------
# public API
# ----------------------------------------------------------------------------


def render_digest(
    deltas: Deltas,
    *,
    topic: str,
    date: dt.date | str,
    positions: KBStore | Sequence[Position] | None = None,
    previous_date: dt.date | str | None = None,
) -> str:
    """Render ``deltas`` as one self-contained HTML digest document and return it.

    ``topic`` is the topic this digest covers (``evals`` for the slice). ``date`` is the
    run date, **injected by the caller** (never the wall clock) — it dates the masthead and
    names the file. ``positions`` is the *current* knowledge base (a :class:`KBStore` or a
    sequence of :class:`Position`); when given, the digest appends a "state of the field"
    summary and enriches every maturity move with the full timeline of videos behind it.
    Supplying it is what makes a no-changes page substantive, so the pipeline always does.
    ``previous_date`` — the last run's date, if known — sharpens the "since …" framing.

    The returned string is a complete ``<!doctype html>`` document with all CSS and JS
    inlined; it is never empty, even when ``deltas`` is.
    """

    run_date = _coerce_date(date)
    prev_date = _coerce_date(previous_date) if previous_date is not None else None
    pos_list = _normalize_positions(positions)
    pos_by_id = {p.position_id: p for p in pos_list} if pos_list is not None else {}

    title = f"{topic} digest · {run_date.isoformat()}"
    masthead = _masthead(topic, run_date, prev_date, empty=deltas.is_empty)

    if deltas.is_empty:
        body = "\n".join(
            [
                masthead,
                _no_changes_hero(topic, run_date),
                _state_section(pos_list, standing=True),
                _critique_callout(),
                _footer(topic, run_date),
            ]
        )
        return _document(title, body)

    citations = _citation_index(deltas)
    sections, present = _diff_sections(deltas, citations, pos_by_id)

    body = "\n".join(
        [
            masthead,
            _stat_tiles(deltas),
            _filter_bar(present),
            _toc(present, has_state=pos_list is not None),
            _lede(deltas, topic, prev_date),
            sections,
            _critique_callout(),
            _state_section(pos_list, standing=True),
            _footer(topic, run_date),
        ]
    )
    return _document(title, body)


def digest_filename(topic: str, date: dt.date | str) -> str:
    """The digest's filename, ``YYYY-MM-DD-<topic>.html`` — dated from the injected date."""

    return f"{_coerce_date(date).isoformat()}-{topic}.html"


def write_digest(
    deltas: Deltas,
    *,
    topic: str,
    date: dt.date | str,
    positions: KBStore | Sequence[Position] | None = None,
    previous_date: dt.date | str | None = None,
    out_dir: str | Path = DIGESTS_DIR,
) -> Path:
    """Render the digest and write it to ``<out_dir>/YYYY-MM-DD-<topic>.html`` atomically.

    Returns the path written. The write is atomic (temp file + ``os.replace``, matching the
    KB store) so an interrupted run cannot leave a half-written page. ``date`` names the
    file, so re-running with the same date overwrites in place rather than piling up.
    """

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / digest_filename(topic, date)
    document = render_digest(
        deltas, topic=topic, date=date, positions=positions, previous_date=previous_date
    )
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    tmp.write_text(document, encoding="utf-8")
    os.replace(tmp, path)
    return path


# ----------------------------------------------------------------------------
# masthead / hero / summary
# ----------------------------------------------------------------------------


def _masthead(topic: str, date: dt.date, prev: dt.date | None, *, empty: bool) -> str:
    dek = (
        f"A diff of the {_esc(topic)} knowledge base."
        if not empty
        else f"The {_esc(topic)} knowledge base held steady."
    )
    parts = [_human_date(date)]
    if prev is not None:
        parts.append(f"since {_human_date(prev)}")
    parts.append(f"topic · {_esc(topic)}")
    dateline = '<span class="sep">·</span>'.join(f"<span>{p}</span>" for p in parts)
    return (
        '<header class="masthead">'
        '<p class="kicker">Knowledge Base · Reader’s Digest</p>'
        f'<h1 class="title">What changed in <em>{_esc(topic)}</em></h1>'
        f'<p class="dek">{dek}</p>'
        f'<p class="dateline sans">{dateline}</p>'
        "</header>"
    )


def _stat_tiles(deltas: Deltas) -> str:
    ladder_up = sum(1 for t in deltas.maturity_transitions if t.to_maturity != "contested")
    new_evidence = sum(1 for c in deltas.newly_confirmed if c.kind.value == "new-evidence")
    tiles = [
        ("tile--new", len(deltas.net_new), "New positions", None),
        (
            "tile--confirmed",
            len(deltas.newly_confirmed),
            "Confirmations",
            f"{new_evidence} new evidence" if deltas.newly_confirmed else None,
        ),
        ("tile--contested", len(deltas.newly_contested), "Newly contested", None),
        (
            "tile--matured",
            len(deltas.maturity_transitions),
            "Maturity shifts",
            f"{ladder_up} matured ↑" if deltas.maturity_transitions else None,
        ),
    ]
    cells = []
    for cls, num, label, sub in tiles:
        sub_html = f'<div class="tile-sub sans">{_esc(sub)}</div>' if sub else ""
        cells.append(
            f'<div class="tile {cls}"><div class="num">{num}</div>'
            f'<div class="tile-label">{_esc(label)}</div>{sub_html}</div>'
        )
    return f'<div class="tiles">{"".join(cells)}</div>'


def _lede(deltas: Deltas, topic: str, prev: dt.date | None) -> str:
    since = f"Since {_human_date(prev)}" if prev is not None else "Since the last run"
    total = deltas.total_changes()
    summary = _run_summary(deltas)
    contested_line = ""
    if deltas.newly_contested:
        contested_line = (
            " Where two credible voices disagree, both are quoted side by side below — "
            "the digest preserves the argument rather than settling it for you."
        )
    # The drop cap is the first letter of the fixed opening word "Since".
    return (
        f'<p class="lede"><span class="drop">S</span>ince{since[5:]}, the '
        f"<b>{_esc(topic)}</b> knowledge base moved in "
        f"{_plural(total, 'place')}. This briefing is a <b>diff of what you know</b>: "
        f"{summary}.{contested_line}</p>"
    )


def _run_summary(deltas: Deltas) -> str:
    clauses: list[str] = []
    if deltas.net_new:
        clauses.append(f"{_num_word(len(deltas.net_new))} new position{_s(len(deltas.net_new))} opened")
    ev = [c for c in deltas.newly_confirmed if c.kind.value == "new-evidence"]
    rd = [c for c in deltas.newly_confirmed if c.kind.value == "redundant"]
    if ev:
        clauses.append(f"{_num_word(len(ev))} position{_s(len(ev))} picked up fresh evidence")
    if rd:
        clauses.append(f"{_num_word(len(rd))} point{_s(len(rd))} {'was' if len(rd) == 1 else 'were'} restated")
    if deltas.newly_contested:
        n = len(deltas.newly_contested)
        clauses.append(f"{_num_word(n)} genuine disagreement{_s(n)} surfaced")
    ladder_up = [t for t in deltas.maturity_transitions if t.to_maturity != "contested"]
    if ladder_up:
        clauses.append(f"{_num_word(len(ladder_up))} position{_s(len(ladder_up))} matured up the ladder")
    if not clauses:
        clauses.append("the maturity of an existing position shifted")
    return _join_clauses(clauses)


# ----------------------------------------------------------------------------
# diff sections
# ----------------------------------------------------------------------------


def _diff_sections(
    deltas: Deltas, citations: dict[str, Citation], pos_by_id: dict[str, Position]
) -> tuple[str, list[tuple[str, str, str]]]:
    """Build the diff sections and return ``(html, present)`` where present drives the
    filter bar + TOC as ``(cat, chip_label, toc_label)`` triples, in reading order."""

    blocks: list[str] = []
    present: list[tuple[str, str, str]] = []

    if deltas.net_new:
        blocks.append(_net_new_section(deltas.net_new))
        present.append(("new", "New positions", "New positions"))
    if deltas.newly_contested:
        blocks.append(_contested_section(deltas.newly_contested))
        present.append(("contested", "Disagreements", "Disagreements"))
    if deltas.newly_confirmed:
        blocks.append(_confirmed_section(deltas.newly_confirmed))
        present.append(("confirmed", "Confirmations", "Confirmations"))
    if deltas.maturity_transitions:
        blocks.append(_matured_section(deltas.maturity_transitions, citations, pos_by_id))
        present.append(("matured", "Maturity", "How maturity moved"))

    return "\n".join(blocks), present


def _section(cat: str, kicker: str, title: str, intro: str, cards: str) -> str:
    return (
        f'<section class="diff" id="{cat}" data-cat="{cat}">'
        f'<p class="section-kicker">{_esc(kicker)}</p>'
        f'<h2 class="section-title">{_esc(title)}</h2>'
        f'<p class="section-intro">{intro}</p>'
        f"{cards}</section>"
    )


def _net_new_section(items: list[NetNewDelta]) -> str:
    intro = (
        "Positions the field had not stated before this run — each opens as an "
        "<b>open question</b>, a single voice on the record, waiting to be confirmed or contested."
    )
    cards = "".join(
        f'<div class="card card--new">'
        f"{_tag('net-new')}"
        f'<p class="statement">{_esc(d.statement)} <span class="pid mono">{_esc(d.position_id)}</span></p>'
        f"{_quote_block(d.citation)}"
        "</div>"
        for d in items
    )
    return _section("new", "Net-new", "New positions", intro, cards)


def _contested_section(items: list[ContestedDelta]) -> str:
    intro = (
        "The heart of the briefing. A credible dissent met an existing position, so both "
        "stances are kept side by side — quoted, sourced, and dated — with the disagreement "
        "typed but <b>not</b> smoothed away."
    )
    cards = "".join(_contested_card(d) for d in items)
    return _section("contested", "Newly contested", "New disagreements", intro, cards)


def _contested_card(d: ContestedDelta) -> str:
    flip = (
        "This run flipped it to contested."
        if d.became_contested
        else "An already-contested position took a further dissent."
    )
    return (
        '<div class="card card--contested">'
        f"{_tag('contested')}"
        f'<p class="statement">{_esc(d.position_statement)} '
        f'<span class="pid mono">{_esc(d.position_id)}</span></p>'
        f'<p class="section-intro" style="margin:0 0 10px">{_esc(flip)}</p>'
        '<div class="stances">'
        f'<div class="stance support"><div class="side">Supporting</div>'
        f"{_quote_block(d.supporting)}</div>"
        '<div class="vs"><span>vs</span></div>'
        f'<div class="stance oppose"><div class="side">Opposing</div>'
        f"{_quote_block(d.opposing)}</div>"
        "</div>"
        f"{_reconciliation(d.reconciliation)}"
        "</div>"
    )


def _reconciliation(r) -> str:
    verdict_cls, verdict_txt = (
        ("open", "unreconciled — genuinely open")
        if r.is_open
        else ("resolved", "reconciled")
    )
    return (
        '<div class="recon">'
        f'<span class="rtype">{_esc(r.type.value.capitalize())} disagreement</span>'
        f'<span class="verdict {verdict_cls}">{_esc(verdict_txt)}</span>'
        "<details><summary>Why they disagree</summary>"
        f'<p class="explain">{_esc(r.explanation)}</p></details>'
        "</div>"
    )


def _confirmed_section(items: list[ConfirmedDelta]) -> str:
    evidence = [d for d in items if d.kind.value == "new-evidence"]
    redundant = [d for d in items if d.kind.value == "redundant"]
    intro = (
        "Existing positions that gained backing. A <b>fresh, independent voice</b> "
        "strengthens confidence and can ratchet maturity up; a mere restatement is kept for "
        "the record but tucked away so it does not crowd the briefing."
    )
    cards = "".join(_confirmed_card(d) for d in evidence)
    if redundant:
        rows = "".join(_confirmed_card(d, muted=True) for d in redundant)
        cards += (
            f"<details class='redundant-wrap'><summary class='sans'>"
            f"Show {_plural(len(redundant), 'restatement')} (redundant)</summary>{rows}</details>"
        )
    if not cards:
        cards = '<p class="empty-note">No confirmations this run.</p>'
    return _section("confirmed", "Confirmed", "Confirmations", intro, cards)


def _confirmed_card(d: ConfirmedDelta, *, muted: bool = False) -> str:
    kind = "redundant" if muted else "new-evidence"
    return (
        '<div class="card card--confirmed">'
        f"{_tag(kind)}"
        f'<p class="statement">{_esc(d.position_statement)} '
        f'<span class="pid mono">{_esc(d.position_id)}</span></p>'
        f"{_quote_block(d.citation)}"
        "</div>"
    )


def _matured_section(
    items: list[MaturityTransitionDelta],
    citations: dict[str, Citation],
    pos_by_id: dict[str, Position],
) -> str:
    intro = (
        "How positions moved along <b>open question → emerging → converging → "
        "solved</b> — and where a dissent knocked one back to contested. Every move is "
        "tied to the specific videos behind it; a trend is never asserted on thin air."
    )
    cards = "".join(_matured_card(t, citations, pos_by_id) for t in items)
    return _section("matured", "Maturity", "How maturity moved", intro, cards)


def _matured_card(
    t: MaturityTransitionDelta,
    citations: dict[str, Citation],
    pos_by_id: dict[str, Position],
) -> str:
    reopened = t.to_maturity == "contested"
    tag = _tag("reopened") if reopened else _tag("matured")
    cites = _trend_citations(t, citations, pos_by_id)
    cite_label = "Triggered by" if reopened else "Backed by"
    cite_html = (
        f'<p class="cite-row"><span class="cite-lead sans">{cite_label}:</span> {cites}</p>'
        if cites
        else ""
    )
    return (
        '<div class="card card--matured">'
        f"{tag}"
        f'<p class="statement">{_esc(t.statement)} '
        f'<span class="pid mono">{_esc(t.position_id)}</span></p>'
        f"{_ladder(t.from_maturity, t.to_maturity)}"
        f'<p class="section-intro" style="margin:8px 0 6px">{_esc(t.reason)}</p>'
        f"{cite_html}"
        "</div>"
    )


def _ladder(from_flag: str, to_flag: str) -> str:
    """A horizontal maturity ladder with the from-rung and to-rung marked; a to-contested
    transition points off the ladder to a separate contested marker."""

    blank_tag = '<span class="rung-tag">&nbsp;</span>'
    rungs = []
    for flag in MATURITY_ORDER:
        classes = ["rung"]
        tag = blank_tag
        if flag == from_flag:
            classes.append("from")
            tag = '<span class="rung-tag">was</span>'
        if flag == to_flag:
            classes.append("to")
            classes.append(MATURITY_CLASS[flag])
            tag = '<span class="rung-tag">now</span>'
        label = MATURITY_BADGE.get(flag, flag).split(" ", 1)[-1]
        rungs.append(
            f'<div class="{" ".join(classes)}">'
            f'<span class="rung-label">{_esc(label)}</span>{tag}</div>'
        )
    ladder = '<div class="ladder">' + "".join(rungs)
    if to_flag == "contested":
        ladder += (
            '<span class="arrow">→</span>'
            '<div class="contested-marker"><span class="rung-label">⚔ contested</span>'
            '<span class="rung-tag">now</span></div>'
        )
    ladder += "</div>"
    return ladder


def _trend_citations(
    t: MaturityTransitionDelta,
    citations: dict[str, Citation],
    pos_by_id: dict[str, Position],
) -> str:
    """Citation chips backing a maturity move.

    When the current KB is supplied, a ladder move shows the full timeline of supporting
    videos + dates behind the trend (spec user story 25); otherwise it falls back to the
    run's own citation for the triggering unit. A to-contested move shows the dissent that
    triggered it.
    """

    position = pos_by_id.get(t.position_id)
    if position is not None and t.to_maturity != "contested":
        seen: set[str] = set()
        chips: list[str] = []
        for src in sorted(position.supporting_sources, key=lambda s: (s.date, s.unit_id)):
            if src.video_id in seen:
                continue
            seen.add(src.video_id)
            chips.append(_chip(src.video_id, src.date, src.unit_id))
        if chips:
            shown, extra = chips[:6], len(chips) - 6
            tail = f'<span class="cite more">+{extra} more</span>' if extra > 0 else ""
            return "".join(shown) + tail
    if t.trigger_unit_id and t.trigger_unit_id in citations:
        c = citations[t.trigger_unit_id]
        return _chip(c.video_id, c.date, c.unit_id)
    if t.trigger_unit_id:
        # Last-resort: the video id is the prefix of the unit id (`{video_id}#{index}`).
        vid = t.trigger_unit_id.rsplit("#", 1)[0]
        return _chip(vid, None, t.trigger_unit_id)
    return ""


# ----------------------------------------------------------------------------
# state of the knowledge base
# ----------------------------------------------------------------------------


def _state_section(positions: list[Position] | None, *, standing: bool) -> str:
    if positions is None:
        if standing:
            return (
                '<section class="diff" id="state"><p class="section-kicker">State</p>'
                '<h2 class="section-title">State of the field</h2>'
                '<p class="empty-note">The current knowledge base was not supplied to this '
                "render.</p></section>"
            )
        return ""
    if not positions:
        return (
            '<section class="diff" id="state"><p class="section-kicker">State</p>'
            '<h2 class="section-title">State of the field</h2>'
            '<p class="empty-note">The knowledge base has no positions yet.</p></section>'
        )

    counts = _maturity_counts(positions)
    contested = counts.get("contested", 0)
    intro = (
        f"Where <b>{_plural(len(positions), 'position')}</b> stand today"
        + (f", <b>{contested}</b> of them contested" if contested else "")
        + ". Live debates lead; settled consensus follows."
    )
    rows = "".join(
        _position_row(p)
        for p in sorted(positions, key=lambda p: (_STATE_RANK.get(p.maturity.value, 9), p.position_id))
    )
    return (
        '<section class="diff" id="state">'
        '<p class="section-kicker">State</p>'
        '<h2 class="section-title">State of the field</h2>'
        f'<p class="section-intro">{intro}</p>'
        f"{_distribution_bar(counts, len(positions))}"
        f"{rows}"
        "</section>"
    )


def _distribution_bar(counts: dict[str, int], total: int) -> str:
    order = [
        ("contested", "s-contested", "contested"),
        ("open-question", "s-open", "open"),
        ("emerging-trend", "s-emerging", "emerging"),
        ("converging", "s-converging", "converging"),
        ("solved", "s-solved", "solved"),
    ]
    segs, legend = [], []
    for flag, cls, label in order:
        n = counts.get(flag, 0)
        if not n:
            continue
        pct = round(100 * n / total, 2)
        segs.append(f'<span class="{cls}" style="width:{pct}%" title="{label}: {n}"></span>')
        legend.append(
            f'<span class="lg"><span class="sw {cls}"></span>{_esc(label)} · {n}</span>'
        )
    return f'<div class="kb-bar">{"".join(segs)}</div><div class="kb-legend sans">{"".join(legend)}</div>'


def _position_row(p: Position) -> str:
    flag = p.maturity.value
    badge = f'<span class="badge {MATURITY_CLASS.get(flag, "")}">{_esc(MATURITY_BADGE.get(flag, flag))}</span>'
    n_src = len(p.distinct_videos)
    span = p.span_days
    if span is None:
        span_txt = "no sources"
    elif span == 0:
        span_txt = "same-day"
    else:
        span_txt = f"{span}-day span"
    return (
        '<div class="pos-row">'
        f'<div class="pmeta">{badge}'
        f'<span class="pcount sans">{_plural(n_src, "source")} · {span_txt}</span></div>'
        f'<div class="pstmt"><span class="pid mono">{_esc(p.position_id)}</span> '
        f'<span class="s">{_esc(p.statement)}</span></div>'
        "</div>"
    )


def _maturity_counts(positions: Iterable[Position]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for p in positions:
        counts[p.maturity.value] = counts.get(p.maturity.value, 0) + 1
    return counts


# ----------------------------------------------------------------------------
# no-changes hero + shared chrome
# ----------------------------------------------------------------------------


def _no_changes_hero(topic: str, date: dt.date) -> str:
    return (
        '<div class="calm">'
        '<div class="mark">✓</div>'
        "<h2>No changes since the last run</h2>"
        f"<p>No new units moved the <b>{_esc(topic)}</b> knowledge base as of "
        f"{_human_date(date)}. Nothing was opened, confirmed, or contested — so here is "
        "where the field stands today.</p>"
        "</div>"
    )


def _critique_callout() -> str:
    return (
        '<div class="callout sans">'
        "<b>How to read this.</b> This digest <b>critiques, it does not predict.</b> "
        "Contested positions are kept side by side rather than resolved into a narrative, and "
        "every trend claim is bound to the videos that support it. A confident forecast is "
        "exactly what you will not find here."
        "</div>"
    )


def _footer(topic: str, date: dt.date) -> str:
    return (
        '<footer class="foot">'
        f"Generated by the YouTube-KB pipeline for topic <b>{_esc(topic)}</b>, "
        f"run of {_human_date(date)}. This page is a diff of the knowledge base; the "
        f"canonical state lives in <code>kb-data/{_esc(topic)}/positions.json</code>. "
        "Self-contained — no external requests."
        "</footer>"
    )


def _toc(present: list[tuple[str, str, str]], *, has_state: bool) -> str:
    links = [f'<a href="#{cat}">{_esc(toc_label)}</a>' for cat, _chip_label, toc_label in present]
    if has_state:
        links.append('<a href="#state">State of the field</a>')
    if not links:
        return ""
    return f'<nav class="toc sans">{"".join(links)}</nav>'


def _filter_bar(present: list[tuple[str, str, str]]) -> str:
    if not present:
        return ""
    dot = {"new": "var(--new)", "confirmed": "var(--evid)", "contested": "var(--contest)", "matured": "var(--matured)"}
    chips = "".join(
        f'<button class="chip" data-cat="{cat}" aria-pressed="true">'
        f'<span class="dot" style="background:{dot.get(cat, "var(--muted)")}"></span>{_esc(label)}</button>'
        for cat, label, _toc_label in present
    )
    return (
        '<div class="filterbar sans" id="filterbar" hidden>'
        '<span class="fl-label">Focus</span>'
        f"{chips}</div>"
    )


# ----------------------------------------------------------------------------
# small shared components
# ----------------------------------------------------------------------------


def _tag(kind: str) -> str:
    label, cls = DELTA_LABEL[kind]
    return f'<span class="tag {cls}">{_esc(label)}</span>'


def _quote_block(c: Citation) -> str:
    return (
        f'<blockquote class="q">{_esc(c.quote)}</blockquote>'
        f"{_chip(c.video_id, c.date, c.unit_id)}"
    )


def _chip(video_id: str, date: dt.date | None, unit_id: str | None) -> str:
    date_html = (
        f'<span class="sep"> · </span>{_esc(_fmt_date(date))}' if date is not None else ""
    )
    unit_html = f' <span class="u">{_esc(unit_id)}</span>' if unit_id else ""
    return (
        f'<span class="cite"><span class="play">▷</span> '
        f"<b>{_esc(video_id)}</b>{date_html}{unit_html}</span>"
    )


def _document(title: str, body: str) -> str:
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="color-scheme" content="light dark">\n'
        f"<title>{_esc(title)}</title>\n"
        f"<style>{CSS}</style>\n"
        "</head>\n<body>\n"
        f'<div class="wrap">\n{body}\n</div>\n'
        f"<script>{JS}</script>\n"
        "</body>\n</html>\n"
    )


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------


def _citation_index(deltas: Deltas) -> dict[str, Citation]:
    """Map ``unit_id → Citation`` across every bucket, so a maturity transition can be
    cited with source + date from the run's own data — no join back to the KB needed."""

    index: dict[str, Citation] = {}
    for d in deltas.net_new:
        index[d.citation.unit_id] = d.citation
    for d in deltas.newly_confirmed:
        index[d.citation.unit_id] = d.citation
    for d in deltas.newly_contested:
        index[d.supporting.unit_id] = d.supporting
        index[d.opposing.unit_id] = d.opposing
    return index


def _normalize_positions(
    positions: KBStore | Sequence[Position] | None,
) -> list[Position] | None:
    if positions is None:
        return None
    if isinstance(positions, KBStore):
        return positions.positions()
    return sorted(positions, key=lambda p: p.position_id)


def _coerce_date(value: dt.date | str) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value))


def _fmt_date(value: dt.date) -> str:
    return value.isoformat()


def _human_date(value: dt.date) -> str:
    return f"{_MONTHS[value.month - 1]} {value.day}, {value.year}"


def _esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def _s(n: int) -> str:
    return "" if n == 1 else "s"


def _plural(n: int, singular: str, plural: str | None = None) -> str:
    word = singular if n == 1 else (plural or singular + "s")
    return f"{n} {word}"


def _num_word(n: int) -> str:
    return _NUM_WORD[n] if 0 <= n < len(_NUM_WORD) else str(n)


def _join_clauses(clauses: list[str]) -> str:
    if not clauses:
        return ""
    if len(clauses) == 1:
        return clauses[0]
    if len(clauses) == 2:
        return f"{clauses[0]} and {clauses[1]}"
    return ", ".join(clauses[:-1]) + f", and {clauses[-1]}"
