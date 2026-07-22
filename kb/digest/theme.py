"""The digest's look: self-contained CSS, progressive-enhancement JS, and design tokens.

The digest is the pipeline's primary output surface (ticket #10) and must render as a
*single self-contained HTML file* — no external stylesheets, fonts, scripts, or images,
so it opens correctly from disk, in an email, or behind the strictest CSP. This module
owns everything visual so :mod:`kb.digest.render` can stay focused on structure and prose:

* :data:`CSS` — the whole stylesheet, inlined into ``<style>``. An editorial theme (a
  serif reading column, a restrained accent, colour-coded delta labels) that is
  *theme-aware*: it ships a light palette and a dark override via
  ``@media (prefers-color-scheme: dark)``, so the same file reads well morning or night.
* :data:`JS` — a tiny, dependency-free progressive enhancement: a category filter so a
  reader can focus the briefing (e.g. "just the disagreements"). It is inert without
  JavaScript — the controls start ``hidden`` and every section is visible — so the page
  never depends on script to be complete (spec: never an empty file).
* the token maps (:data:`MATURITY_BADGE`, :data:`MATURITY_ORDER`, :data:`DELTA_LABEL`) —
  the small vocabulary that ties a maturity flag or a delta kind to its glyph, label, and
  colour class, shared by every section so the whole page reads as one system.

Design families reused throughout (all HTML/CSS, never ASCII art): the *stat tile* row,
the *citation chip* (``▷ video · date``), the *two-column stance card* for a contest, the
*maturity ladder*, and the *position card*.
"""

from __future__ import annotations

__all__ = [
    "CSS",
    "JS",
    "MATURITY_BADGE",
    "MATURITY_ORDER",
    "MATURITY_CLASS",
    "DELTA_LABEL",
]

# One glyph + human label per maturity flag, mirroring kb.reconcile.markdown.MATURITY_BADGE
# so the HTML digest and the Markdown KB speak the same visual language.
MATURITY_BADGE: dict[str, str] = {
    "open-question": "○ open question",
    "emerging-trend": "◔ emerging trend",
    "converging": "◑ converging",
    "solved": "● solved",
    "contested": "⚔ contested",
}

# The ladder rungs, weakest → strongest. ``contested`` is deliberately absent: it is off
# the ladder (a live disagreement), rendered as a separate marker, not a rung.
MATURITY_ORDER: tuple[str, ...] = (
    "open-question",
    "emerging-trend",
    "converging",
    "solved",
)

# Maturity flag → CSS modifier class (colour family). Kept in sync with the palette in CSS.
MATURITY_CLASS: dict[str, str] = {
    "open-question": "mat--open",
    "emerging-trend": "mat--emerging",
    "converging": "mat--converging",
    "solved": "mat--solved",
    "contested": "mat--contested",
}

# Delta kind → (uppercase label, CSS tag class). The label vocabulary the reader learns
# once and sees consistently; the class carries the colour.
DELTA_LABEL: dict[str, tuple[str, str]] = {
    "net-new": ("New position", "tag--new"),
    "new-evidence": ("Confirmed · new evidence", "tag--new-evidence"),
    "redundant": ("Confirmed · restated", "tag--redundant"),
    "contested": ("Newly contested", "tag--contested"),
    "matured": ("Matured", "tag--matured"),
    "reopened": ("Reopened", "tag--reopened"),
}


CSS = """
:root {
  --bg: #fbfaf7;
  --surface: #ffffff;
  --surface-2: #f5f3ee;
  --ink: #1d1b16;
  --ink-soft: #45413a;
  --muted: #726d63;
  --border: #e7e2d7;
  --border-strong: #d8d2c4;
  --accent: #a23b2c;
  --accent-ink: #872f22;
  --shadow: 0 1px 2px rgba(28,27,22,.05), 0 8px 24px -12px rgba(28,27,22,.18);

  /* delta / maturity colour families: --x = text, --x-bg = tint, --x-line = border */
  --new: #3a3ad0;      --new-bg: #ececfb;      --new-line: #cfcef6;
  --evid: #1c7a4b;     --evid-bg: #e3f5ea;     --evid-line: #c2e8d1;
  --redun: #5c6470;    --redun-bg: #eef0f3;    --redun-line: #dde1e7;
  --contest: #96650e;  --contest-bg: #fbf0d6;  --contest-line: #f0dfae;
  --matured: #0e7683;  --matured-bg: #d9f1f4;  --matured-line: #b6e4e9;
  --reopen: #a5324a;   --reopen-bg: #fbe3e9;   --reopen-line: #f4c7d1;
}

@media (prefers-color-scheme: dark) {
  :root {
    --bg: #16150f;
    --surface: #201e17;
    --surface-2: #2a271e;
    --ink: #f2efe6;
    --ink-soft: #d7d2c4;
    --muted: #a29c8c;
    --border: #34301f00;
    --border: #35322a;
    --border-strong: #45402f;
    --accent: #e98a6a;
    --accent-ink: #f0a488;
    --shadow: 0 1px 2px rgba(0,0,0,.3), 0 10px 30px -14px rgba(0,0,0,.6);

    --new: #a9a7ff;      --new-bg: #23224a;      --new-line: #34336a;
    --evid: #74e4a4;     --evid-bg: #163325;     --evid-line: #245039;
    --redun: #9aa4b2;    --redun-bg: #24272e;    --redun-line: #363b45;
    --contest: #f3c56a;  --contest-bg: #38300f;  --contest-line: #574916;
    --matured: #63d6e3;  --matured-bg: #103139;  --matured-line: #1c4c58;
    --reopen: #f59ab0;   --reopen-bg: #3a1622;   --reopen-line: #5a2436;
  }
}

* { box-sizing: border-box; }
html { scroll-behavior: smooth; -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font: 400 18px/1.65 "Iowan Old Style", "Charter", "Bitstream Charter", Georgia, Cambria, "Times New Roman", serif;
  padding: 0 20px 96px;
}
.wrap { max-width: 780px; margin: 0 auto; }

/* --- UI type: labels, chips, tiles use a system sans; prose stays serif --- */
.sans, .tag, .chip, .tile-label, .badge, .cite, .kicker, nav.toc a, .filterbar, .rung-label, .section-kicker {
  font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}
code, .mono, .cite { font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace; }

/* --- masthead --- */
header.masthead { padding: 48px 0 18px; border-bottom: 2px solid var(--ink); margin-bottom: 8px; }
.kicker {
  font-size: 12px; letter-spacing: .14em; text-transform: uppercase;
  color: var(--accent-ink); font-weight: 700; margin: 0 0 10px;
}
h1.title { font-size: clamp(30px, 6vw, 46px); line-height: 1.08; margin: 0 0 12px; letter-spacing: -.015em; }
.dek { font-size: 20px; color: var(--ink-soft); margin: 0 0 18px; font-style: italic; }
.dateline { font-size: 14px; color: var(--muted); margin: 0; }
.dateline .sep { opacity: .5; padding: 0 8px; }

/* --- the narrative brief (issue #19): the digest's opening lede section --- */
section.brief {
  margin: 30px 0 8px; padding: 26px 28px; border-radius: 16px;
  background: var(--surface); border: 1px solid var(--border);
  border-top: 4px solid var(--accent); box-shadow: var(--shadow);
}
section.brief .section-kicker { color: var(--accent-ink); }
section.brief h2.section-title { margin: 2px 0 10px; }
.brief-body { font-size: 18.5px; line-height: 1.7; color: var(--ink); }
.brief-body p { margin: 0 0 16px; }
.brief-body p:first-child { font-size: 19.5px; }
.brief-body p:first-child::first-letter {
  float: left; font-size: 58px; line-height: .82; padding: 4px 10px 0 0;
  font-weight: 700; color: var(--accent);
}
.brief-body p:last-child { margin-bottom: 0; }

/* --- collapsed full-position-list appendix (shown when a brief leads the page) --- */
section.diff.appendix { margin-top: 34px; }
.state-appendix { border-top: 1px solid var(--border); padding-top: 8px; }
.state-appendix > summary {
  cursor: pointer; list-style: none; display: flex; flex-wrap: wrap; align-items: baseline;
  gap: 10px; padding: 10px 0; color: var(--ink-soft);
}
.state-appendix > summary::-webkit-details-marker { display: none; }
.state-appendix > summary .section-kicker {
  font-size: 12px; letter-spacing: .12em; text-transform: uppercase; color: var(--muted);
  font-weight: 700; margin: 0;
}
.state-appendix > summary .appendix-title { font-size: 20px; font-weight: 700; color: var(--ink); }
.state-appendix > summary .appendix-hint { font-size: 13px; color: var(--muted); margin-left: auto; }
.state-appendix[open] > summary .appendix-hint { visibility: hidden; }
.appendix-body { padding-top: 6px; }

/* --- stat tiles --- */
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 12px; margin: 24px 0 8px; }
.tile {
  background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
  padding: 14px 16px; box-shadow: var(--shadow); border-top: 3px solid var(--tile-accent, var(--border-strong));
}
.tile .num { font-size: 30px; font-weight: 700; line-height: 1; letter-spacing: -.02em; }
.tile-label { font-size: 12px; letter-spacing: .04em; text-transform: uppercase; color: var(--muted); margin-top: 6px; }
.tile-sub { font-size: 11.5px; color: var(--muted); margin-top: 3px; opacity: .85; }
.tile--new { --tile-accent: var(--new); } .tile--new .num { color: var(--new); }
.tile--confirmed { --tile-accent: var(--evid); } .tile--confirmed .num { color: var(--evid); }
.tile--contested { --tile-accent: var(--contest); } .tile--contested .num { color: var(--contest); }
.tile--matured { --tile-accent: var(--matured); } .tile--matured .num { color: var(--matured); }

/* --- filter bar (progressive enhancement; starts hidden) --- */
.filterbar {
  display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
  margin: 22px 0 4px; padding: 12px 14px; background: var(--surface-2);
  border: 1px solid var(--border); border-radius: 12px; font-size: 13px;
}
.filterbar .fl-label { color: var(--muted); font-weight: 600; margin-right: 2px; }
.chip {
  cursor: pointer; border: 1px solid var(--border-strong); background: var(--surface);
  color: var(--ink-soft); border-radius: 999px; padding: 5px 12px; font-size: 13px; font-weight: 600;
}
.chip[aria-pressed="false"] { opacity: .42; text-decoration: line-through; }
.chip .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; vertical-align: middle; }

/* --- table of contents --- */
nav.toc { margin: 26px 0 8px; font-size: 14px; }
nav.toc a {
  color: var(--ink-soft); text-decoration: none; border-bottom: 1px solid var(--border-strong);
  padding-bottom: 1px; margin-right: 18px; white-space: nowrap;
}
nav.toc a:hover { color: var(--accent-ink); border-color: var(--accent); }

/* --- prose --- */
.lede { font-size: 20px; line-height: 1.6; margin: 22px 0; color: var(--ink); }
.lede .drop { float: left; font-size: 62px; line-height: .82; padding: 4px 10px 0 0; font-weight: 700; color: var(--accent); }
p { margin: 0 0 16px; }
a { color: var(--accent-ink); }

/* --- sections --- */
section.diff { margin: 40px 0 8px; scroll-margin-top: 16px; }
.section-kicker { font-size: 12px; letter-spacing: .12em; text-transform: uppercase; color: var(--muted); font-weight: 700; margin: 0 0 2px; }
h2.section-title { font-size: 26px; margin: 0 0 6px; letter-spacing: -.01em; }
.section-intro { color: var(--ink-soft); margin: 0 0 18px; font-size: 17px; }

/* --- cards --- */
.card {
  background: var(--surface); border: 1px solid var(--border); border-left: 4px solid var(--card-line, var(--border-strong));
  border-radius: 12px; padding: 18px 20px; margin: 0 0 16px; box-shadow: var(--shadow);
}
.card--new { --card-line: var(--new); }
.card--confirmed { --card-line: var(--evid); }
.card--contested { --card-line: var(--contest); }
.card--matured { --card-line: var(--matured); }
.card .statement { font-size: 19px; font-weight: 600; margin: 8px 0 12px; line-height: 1.4; }
.card .pid { color: var(--muted); font-weight: 400; }

/* --- delta tag (colour-coded label) --- */
.tag {
  display: inline-flex; align-items: center; gap: 6px; font-size: 11.5px; font-weight: 700;
  letter-spacing: .05em; text-transform: uppercase; padding: 4px 10px; border-radius: 999px;
  border: 1px solid transparent;
}
.tag--new { color: var(--new); background: var(--new-bg); border-color: var(--new-line); }
.tag--new-evidence { color: var(--evid); background: var(--evid-bg); border-color: var(--evid-line); }
.tag--redundant { color: var(--redun); background: var(--redun-bg); border-color: var(--redun-line); }
.tag--contested { color: var(--contest); background: var(--contest-bg); border-color: var(--contest-line); }
.tag--matured { color: var(--matured); background: var(--matured-bg); border-color: var(--matured-line); }
.tag--reopened { color: var(--reopen); background: var(--reopen-bg); border-color: var(--reopen-line); }

/* --- quote + citation chip --- */
blockquote.q {
  margin: 0; padding: 2px 0 2px 14px; border-left: 3px solid var(--border-strong);
  font-size: 17px; line-height: 1.55; color: var(--ink);
}
.cite {
  display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; color: var(--muted);
  background: var(--surface-2); border: 1px solid var(--border); border-radius: 8px;
  padding: 3px 9px; margin-top: 8px; white-space: nowrap; max-width: 100%;
}
.cite .play { color: var(--accent); font-size: 11px; }
.cite b { color: var(--ink-soft); font-weight: 600; }
.cite .u { opacity: .7; }
.cite .sep { opacity: .55; }
.cite.more { font-weight: 600; }

/* citation row under a maturity move ("Backed by: …") */
.cite-row { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 4px 0 0; }
.cite-lead { font-size: 12.5px; color: var(--muted); font-weight: 600; margin-right: 2px; }

/* redundant confirmations disclosure */
.redundant-wrap { margin-top: 4px; }
.redundant-wrap > summary { cursor: pointer; color: var(--muted); font-size: 14px; font-weight: 600; padding: 6px 0; }
.redundant-wrap[open] > summary { margin-bottom: 10px; }
.redundant-wrap .card--confirmed { opacity: .82; }

/* --- two-column stance card (a contest) --- */
.stances { display: grid; grid-template-columns: 1fr auto 1fr; gap: 0; align-items: stretch; margin: 6px 0 4px; }
.stance { padding: 14px 16px; border: 1px solid var(--border); background: var(--surface-2); }
.stance.support { border-radius: 12px 0 0 12px; border-right: none; }
.stance.oppose { border-radius: 0 12px 12px 0; border-left: none; }
.stance .side { font-size: 11.5px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; margin-bottom: 8px; }
.stance.support .side { color: var(--evid); }
.stance.oppose .side { color: var(--reopen); }
.vs {
  display: flex; align-items: center; justify-content: center; width: 42px;
  font: 700 13px ui-sans-serif, system-ui, sans-serif; color: var(--muted);
  background: var(--surface); border-top: 1px solid var(--border); border-bottom: 1px solid var(--border);
}
.vs span { background: var(--surface); border: 1px solid var(--border-strong); border-radius: 999px; padding: 4px 7px; }

/* --- reconciliation callout --- */
.recon {
  margin-top: 12px; padding: 12px 14px; border-radius: 10px; background: var(--contest-bg);
  border: 1px solid var(--contest-line); font-size: 15.5px; line-height: 1.55;
}
.recon .rtype { font-weight: 700; color: var(--contest); font-family: ui-sans-serif, system-ui, sans-serif; }
.recon .verdict { font-size: 11.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; padding: 2px 8px; border-radius: 999px; margin-left: 6px; }
.recon .verdict.open { color: var(--reopen); background: var(--reopen-bg); border: 1px solid var(--reopen-line); }
.recon .verdict.resolved { color: var(--evid); background: var(--evid-bg); border: 1px solid var(--evid-line); }
.recon details { margin-top: 8px; }
.recon summary { cursor: pointer; color: var(--contest); font-weight: 600; font-size: 14px; font-family: ui-sans-serif, system-ui, sans-serif; }
.recon .explain { margin-top: 8px; color: var(--ink-soft); }

/* --- maturity ladder --- */
.ladder { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; margin: 10px 0 4px; }
.rung {
  display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 8px 10px; border-radius: 10px;
  border: 1px dashed var(--border-strong); color: var(--muted); background: var(--surface); min-width: 96px;
}
.rung .rung-label { font-size: 12px; font-weight: 600; }
.rung .rung-tag { font-size: 10px; letter-spacing: .06em; text-transform: uppercase; font-weight: 700; }
.rung.from { border-style: solid; opacity: .8; }
.rung.from .rung-tag { color: var(--muted); }
.rung.to { border-style: solid; border-width: 2px; }
.rung.to.mat--emerging { border-color: var(--new); color: var(--new); } .rung.to.mat--emerging .rung-tag { color: var(--new); }
.rung.to.mat--converging { border-color: var(--matured); color: var(--matured); } .rung.to.mat--converging .rung-tag { color: var(--matured); }
.rung.to.mat--solved { border-color: var(--evid); color: var(--evid); } .rung.to.mat--solved .rung-tag { color: var(--evid); }
.rung.to.mat--open { border-color: var(--redun); color: var(--redun); } .rung.to.mat--open .rung-tag { color: var(--redun); }
.ladder .arrow { color: var(--muted); font-size: 18px; padding: 0 2px; }
.contested-marker {
  display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 8px 12px; border-radius: 10px;
  border: 2px solid var(--contest); color: var(--contest); background: var(--contest-bg); min-width: 96px;
}
.contested-marker .rung-label { font-size: 12px; font-weight: 700; }
.contested-marker .rung-tag { font-size: 10px; letter-spacing: .06em; text-transform: uppercase; font-weight: 700; }

/* --- maturity badge (state summary + cards) --- */
.badge {
  display: inline-flex; align-items: center; gap: 5px; font-size: 12px; font-weight: 700;
  padding: 3px 9px; border-radius: 999px; border: 1px solid transparent; white-space: nowrap;
}
.mat--open { color: var(--redun); background: var(--redun-bg); border-color: var(--redun-line); }
.mat--emerging { color: var(--new); background: var(--new-bg); border-color: var(--new-line); }
.mat--converging { color: var(--matured); background: var(--matured-bg); border-color: var(--matured-line); }
.mat--solved { color: var(--evid); background: var(--evid-bg); border-color: var(--evid-line); }
.mat--contested { color: var(--contest); background: var(--contest-bg); border-color: var(--contest-line); }

/* --- state-of-the-KB section --- */
.kb-bar { display: flex; height: 12px; border-radius: 999px; overflow: hidden; border: 1px solid var(--border); margin: 6px 0 4px; }
.kb-bar span { display: block; }
.kb-bar .s-open { background: var(--redun); } .kb-bar .s-emerging { background: var(--new); }
.kb-bar .s-converging { background: var(--matured); } .kb-bar .s-solved { background: var(--evid); }
.kb-bar .s-contested { background: var(--contest); }
.kb-legend { display: flex; flex-wrap: wrap; gap: 10px 18px; font-size: 13px; color: var(--muted); margin: 10px 0 20px; }
.kb-legend .lg { display: inline-flex; align-items: center; gap: 6px; }
.kb-legend .sw { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }
.pos-row {
  display: flex; align-items: flex-start; gap: 12px; padding: 12px 0; border-top: 1px solid var(--border);
}
.pos-row .pmeta { flex: 0 0 auto; display: flex; flex-direction: column; gap: 6px; align-items: flex-start; min-width: 148px; }
.pos-row .pstmt { flex: 1 1 auto; }
.pos-row .pstmt .s { font-weight: 500; }
.pos-row .pcount { font-size: 12.5px; color: var(--muted); }

/* --- no-changes hero --- */
.calm {
  text-align: center; padding: 30px 20px; border: 1px dashed var(--border-strong);
  border-radius: 16px; background: var(--surface); margin: 22px 0 8px;
}
.calm .mark { font-size: 40px; line-height: 1; }
.calm h2 { font-size: 24px; margin: 12px 0 6px; }
.calm p { color: var(--ink-soft); max-width: 46ch; margin: 0 auto; }

/* --- callout --- */
.callout {
  border: 1px solid var(--border); border-left: 4px solid var(--accent); background: var(--surface);
  border-radius: 10px; padding: 14px 18px; margin: 26px 0; font-size: 16px; color: var(--ink-soft);
}
.callout b { color: var(--ink); }

/* --- footer --- */
footer.foot {
  margin-top: 48px; padding-top: 20px; border-top: 1px solid var(--border);
  font-size: 13px; color: var(--muted); font-family: ui-sans-serif, system-ui, sans-serif;
}
footer.foot code { font-size: 12.5px; color: var(--ink-soft); }

.empty-note { color: var(--muted); font-style: italic; }

/* --- filter visibility (JS toggles body classes) --- */
body.hide-new section[data-cat="new"],
body.hide-confirmed section[data-cat="confirmed"],
body.hide-contested section[data-cat="contested"],
body.hide-matured section[data-cat="matured"] { display: none; }

/* --- responsive --- */
@media (max-width: 620px) {
  body { font-size: 17px; padding: 0 15px 72px; }
  .stances { grid-template-columns: 1fr; }
  .stance.support { border-radius: 12px 12px 0 0; border-right: 1px solid var(--border); border-bottom: none; }
  .stance.oppose { border-radius: 0 0 12px 12px; border-left: 1px solid var(--border); border-top: none; }
  .vs { width: 100%; height: 34px; border-left: 1px solid var(--border); border-right: 1px solid var(--border); }
  .pos-row { flex-direction: column; gap: 8px; }
  nav.toc a { display: inline-block; margin-bottom: 8px; }
}

@media print {
  body { background: #fff; color: #000; }
  .filterbar { display: none; }
  .card, .tile { box-shadow: none; }
}
"""


# Progressive enhancement only: the page is complete and readable with JS disabled (the
# filter bar starts `hidden` and nothing is hidden). On load we reveal the bar and wire
# each chip to toggle one delta category's visibility via a body class the CSS keys on.
JS = """
(function () {
  var bar = document.getElementById('filterbar');
  if (!bar) return;
  bar.hidden = false;
  bar.addEventListener('click', function (e) {
    var chip = e.target.closest('.chip');
    if (!chip) return;
    var cat = chip.getAttribute('data-cat');
    var on = chip.getAttribute('aria-pressed') !== 'false';
    chip.setAttribute('aria-pressed', on ? 'false' : 'true');
    document.body.classList.toggle('hide-' + cat, on);
  });
})();
"""
