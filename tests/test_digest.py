"""Digest rendering tests (ticket #10).

The digest is the pipeline's primary output surface: an HTML diff of the knowledge base
since the last run. These tests assert the spec-load-bearing content is present in the
rendered HTML — both stances of a contest quoted with source + date, citations on
trend-like moves, colour-coded delta labels, the never-empty no-changes page — and that
rendering is deterministic and safely escapes arbitrary quote text. They use the committed
sample deltas + positions (or hand-built ones); no live model or network is touched.

Cosmetic wording and CSS are not pinned beyond what the spec requires.
"""

from __future__ import annotations

import datetime as dt
import json

import pytest

from kb.config import FIXTURES_DIR
from kb.digest import digest_filename, render_digest, write_digest
from kb.reconcile import (
    Citation,
    ConfirmedDelta,
    ConfirmingKind,
    Deltas,
    KBStore,
    MaturityTransitionDelta,
    NetNewDelta,
    Position,
)

SAMPLE_DIR = FIXTURES_DIR / "reconcile-sample" / "evals"
RUN_DATE = dt.date(2025, 10, 15)


# --- fixtures ---------------------------------------------------------------


@pytest.fixture
def sample_deltas() -> Deltas:
    return Deltas.model_validate(json.loads((SAMPLE_DIR / "deltas.json").read_text("utf-8")))


@pytest.fixture
def sample_positions() -> list[Position]:
    doc = json.loads((SAMPLE_DIR / "positions.json").read_text("utf-8"))
    return [Position.model_validate(p) for p in doc["positions"]]


@pytest.fixture
def sample_html(sample_deltas, sample_positions) -> str:
    return render_digest(
        sample_deltas,
        topic="evals",
        date=RUN_DATE,
        positions=sample_positions,
        previous_date=dt.date(2025, 9, 20),
    )


def _citation(unit_id, video_id, date, quote, statement="stmt") -> Citation:
    return Citation(unit_id=unit_id, video_id=video_id, date=date, quote=quote, statement=statement)


# --- document shape ---------------------------------------------------------


def test_output_is_a_complete_self_contained_html_document(sample_html):
    assert sample_html.lstrip().startswith("<!doctype html>")
    assert "<html" in sample_html and "</html>" in sample_html
    # CSS + JS inlined; no external requests.
    assert "<style>" in sample_html and "</style>" in sample_html
    assert "<script>" in sample_html
    for external in ("http://", "https://", "src=\"//", "<link", "@import"):
        assert external not in sample_html, f"external reference leaked: {external!r}"


def test_masthead_names_topic_and_run_date(sample_html):
    assert "evals" in sample_html
    assert "October 15, 2025" in sample_html          # human-readable run date
    assert "Reader" in sample_html and "Digest" in sample_html


# --- newly contested: both stances, quoted, sourced, dated ------------------


def test_contested_shows_both_stances_quoted_with_source_and_date(sample_html):
    # supporting side (the existing manual-first position), quoted with its video + date
    assert "The first obvious solution to this complexity is manual evaluations" in sample_html
    assert "K8LLVi5Xrh8" in sample_html and "2025-05-11" in sample_html
    # opposing side (the incoming dissent), quoted with its own video + date
    assert "don&#x27;t waste time reading outputs by hand" in sample_html  # apostrophe escaped
    assert "demo-eval-talk-06" in sample_html and "2025-10-15" in sample_html
    # the two are visually separated as opposing stances, not merged
    assert "Supporting" in sample_html and "Opposing" in sample_html


def test_contested_shows_typed_reconciliation_including_open_outcome(sample_html):
    assert "Empirical disagreement" in sample_html
    # "unreconciled — genuinely open" is a first-class outcome and must be shown
    assert "unreconciled" in sample_html
    # the explanation text is present (in a disclosure)
    assert "opposite process recommendations" in sample_html


def test_contested_marks_flip_to_contested(sample_html):
    assert "flipped it to contested" in sample_html


# --- net-new ----------------------------------------------------------------


def test_net_new_position_rendered_with_statement_and_citation(sample_html):
    assert "version-controlled" in sample_html
    assert "New position" in sample_html                 # colour-coded label
    assert "evals-0005" in sample_html


# --- confirmations: redundant vs new-evidence -------------------------------


def test_confirmation_distinguishes_redundant_from_new_evidence():
    deltas = Deltas(
        newly_confirmed=[
            ConfirmedDelta(
                position_id="evals-0001",
                position_statement="System eval beats model eval.",
                kind=ConfirmingKind.new_evidence,
                citation=_citation("vidX#1", "vidX", "2025-08-01", "a fresh independent voice"),
            ),
            ConfirmedDelta(
                position_id="evals-0002",
                position_statement="Build your own evals.",
                kind=ConfirmingKind.redundant,
                citation=_citation("vidY#2", "vidY", "2025-08-02", "the same point again"),
            ),
        ]
    )
    html = render_digest(deltas, topic="evals", date=RUN_DATE)
    assert "new evidence" in html.lower()
    # redundant is kept (for provenance) but labelled distinctly as a restatement
    assert "restated" in html.lower() or "redundant" in html.lower()
    assert "a fresh independent voice" in html
    assert "the same point again" in html


# --- maturity transitions: trend-like, citation-bound -----------------------


def test_maturity_transition_shown_with_from_and_to(sample_html):
    # the sample has open-question -> contested
    assert "open question" in sample_html               # the "was" rung label
    assert "How maturity moved" in sample_html


def test_ladder_move_cites_the_supporting_videos(sample_positions):
    """A trend claim must cite the specific videos behind it (spec user story 25)."""
    deltas = Deltas(
        maturity_transitions=[
            MaturityTransitionDelta(
                position_id="evals-0001",
                statement="System eval beats model eval.",
                from_maturity="emerging-trend",
                to_maturity="converging",
                reason="three independent sources agreeing over >3 months",
                trigger_unit_id="demo-eval-talk-06#0",
            )
        ]
    )
    html = render_digest(deltas, topic="evals", date=RUN_DATE, positions=sample_positions)
    assert "Matured" in html
    assert "Backed by" in html
    # evals-0001's distinct supporting videos are cited as the trend's evidence
    assert "K8LLVi5Xrh8" in html
    assert "demo-eval-talk-02" in html


def test_maturity_transition_cites_trigger_when_no_kb_supplied():
    """Even without the KB, a move is citable: the run's own citations carry source+date."""
    deltas = Deltas(
        net_new=[
            NetNewDelta(
                position_id="evals-0005",
                statement="Version-control your evals.",
                citation=_citation("demo-eval-talk-06#1", "demo-eval-talk-06", "2025-10-15", "keep evals in git"),
            )
        ],
        maturity_transitions=[
            MaturityTransitionDelta(
                position_id="evals-0005",
                statement="Version-control your evals.",
                from_maturity="—",
                to_maturity="open-question",
                reason="opened as a new open position",
                trigger_unit_id="demo-eval-talk-06#1",
            )
        ],
    )
    html = render_digest(deltas, topic="evals", date=RUN_DATE)  # no positions
    assert "demo-eval-talk-06" in html
    assert "2025-10-15" in html


# --- stat tiles + summary ---------------------------------------------------


def test_stat_tiles_count_each_bucket(sample_html):
    assert "New positions" in sample_html
    assert "Confirmations" in sample_html
    assert "Newly contested" in sample_html
    assert "Maturity shifts" in sample_html


def test_editorial_lede_frames_the_diff(sample_html):
    assert "diff of what you know" in sample_html
    # critique-not-prediction framing is explicit
    assert "critiques, it does not predict" in sample_html


# --- state of the field -----------------------------------------------------


def test_state_section_summarizes_current_kb(sample_html):
    assert "State of the field" in sample_html
    # every position statement appears in the standing-state list
    assert "LLM-as-a-judge" in sample_html
    # a maturity distribution + contested count is shown
    assert "contested" in sample_html


def test_state_section_accepts_a_kbstore(sample_positions):
    store = KBStore("evals", positions=sample_positions)
    html = render_digest(Deltas(), topic="evals", date=RUN_DATE, positions=store)
    assert "State of the field" in html
    assert "evals-0001" in html


# --- never an empty file (no-changes page) ----------------------------------


def test_no_changes_page_is_non_empty_and_says_so(sample_positions):
    html = render_digest(Deltas(), topic="evals", date=RUN_DATE, positions=sample_positions)
    assert len(html) > 2000
    assert "No changes since the last run" in html
    # and it still carries the current KB state summary (spec requirement)
    assert "State of the field" in html
    assert "Manual evaluation" in html                   # a real position statement


def test_no_changes_page_non_empty_even_without_positions():
    html = render_digest(Deltas(), topic="evals", date=RUN_DATE)
    assert len(html) > 1000
    assert "No changes since the last run" in html
    assert html.lstrip().startswith("<!doctype html>")


def test_empty_deltas_never_renders_diff_sections():
    html = render_digest(Deltas(), topic="evals", date=RUN_DATE)
    assert "New disagreements" not in html
    assert "How maturity moved" not in html


# --- escaping / safety ------------------------------------------------------


def test_arbitrary_quote_text_is_html_escaped():
    evil = _citation(
        "v#0", "vid", "2025-01-01",
        quote="<script>alert(1)</script> & <img src=x onerror=alert(2)>",
        statement="A < B & C",
    )
    deltas = Deltas(
        net_new=[NetNewDelta(position_id="evals-9", statement="<b>x</b> & y", citation=evil)]
    )
    html = render_digest(deltas, topic="evals", date=RUN_DATE)
    assert "<script>alert(1)</script>" not in html       # not injected raw
    assert "<img src=x onerror=alert(2)>" not in html
    assert "&lt;script&gt;" in html                       # present, escaped
    # the only real <script> element is our own trusted (static) JS block
    assert html.count("<script>") == 1


# --- determinism ------------------------------------------------------------


def test_render_is_deterministic(sample_deltas, sample_positions):
    a = render_digest(sample_deltas, topic="evals", date=RUN_DATE, positions=sample_positions)
    b = render_digest(sample_deltas, topic="evals", date=RUN_DATE, positions=sample_positions)
    assert a == b


def test_render_does_not_depend_on_wall_clock(sample_deltas, sample_positions):
    """Date is injected, never read from the clock, so output is date-stable."""
    one = render_digest(sample_deltas, topic="evals", date="2025-10-15", positions=sample_positions)
    two = render_digest(sample_deltas, topic="evals", date=dt.date(2025, 10, 15), positions=sample_positions)
    assert one == two                                    # str and date inputs agree


# --- filename + writing -----------------------------------------------------


def test_digest_filename_uses_injected_date_not_today():
    assert digest_filename("evals", "2024-01-02") == "2024-01-02-evals.html"
    assert digest_filename("small-models", dt.date(2025, 12, 31)) == "2025-12-31-small-models.html"
    # the wall-clock date must not leak into the name
    assert dt.date.today().isoformat() not in digest_filename("evals", "2020-06-06")


def test_write_digest_writes_named_file(tmp_path, sample_deltas, sample_positions):
    path = write_digest(
        sample_deltas, topic="evals", date=RUN_DATE, positions=sample_positions, out_dir=tmp_path
    )
    assert path == tmp_path / "2025-10-15-evals.html"
    assert path.exists()
    content = path.read_text("utf-8")
    assert content == render_digest(
        sample_deltas, topic="evals", date=RUN_DATE, positions=sample_positions
    )
    assert content.lstrip().startswith("<!doctype html>")


def test_write_digest_overwrites_same_date(tmp_path, sample_deltas, sample_positions):
    p1 = write_digest(sample_deltas, topic="evals", date=RUN_DATE, out_dir=tmp_path)
    p2 = write_digest(Deltas(), topic="evals", date=RUN_DATE, positions=sample_positions, out_dir=tmp_path)
    assert p1 == p2                                       # same date -> same path, replaced
    assert "No changes since the last run" in p2.read_text("utf-8")
    assert len(list(tmp_path.glob("*.html"))) == 1


# --- narrative brief placement (issue #19) ----------------------------------

BRIEF_PROSE = (
    "The evals field is pulled apart by one live disagreement over manual review.\n\n"
    "Beyond that, a version-control practice is emerging as several voices converge.\n\n"
    "What changed this run is a single dissent that flipped a settled point back open."
)


def test_brief_none_is_byte_identical_to_no_brief(sample_deltas, sample_positions):
    """The brief is optional: render with brief=None must equal render with no brief arg,
    so existing callers and tests are untouched (spec/#19)."""
    without = render_digest(sample_deltas, topic="evals", date=RUN_DATE, positions=sample_positions)
    with_none = render_digest(
        sample_deltas, topic="evals", date=RUN_DATE, positions=sample_positions, brief=None
    )
    assert without == with_none
    assert "The Brief" not in without                    # no brief chrome leaks in


def test_brief_renders_first_as_its_own_section(sample_deltas, sample_positions):
    html = render_digest(
        sample_deltas, topic="evals", date=RUN_DATE, positions=sample_positions, brief=BRIEF_PROSE,
    )
    assert 'id="brief"' in html
    assert "The Brief" in html
    # the brief prose is present, split into paragraphs (escaped model output)
    assert "pulled apart by one live disagreement" in html
    # it leads: the brief section comes before the diff sections and the position list
    assert html.index('id="brief"') < html.index('id="state"')
    assert html.index('id="brief"') < html.index('class="tiles"')


def test_brief_moves_position_list_into_collapsible_appendix(sample_deltas, sample_positions):
    html = render_digest(
        sample_deltas, topic="evals", date=RUN_DATE, positions=sample_positions, brief=BRIEF_PROSE,
    )
    # the full position list is now a secondary, collapsible appendix
    assert "<details" in html
    assert 'class="state-appendix"' in html
    assert "Full position list" in html
    # every position still renders (nothing is dropped) — just tucked away
    assert "evals-0001" in html
    # the appendix <details> is self-contained (no extra <script> needed for it)
    assert html.count("<script>") == 1


def test_brief_paragraphs_are_escaped_not_injected():
    html = render_digest(
        Deltas(), topic="evals", date=RUN_DATE,
        brief="<script>alert(1)</script> a genuine paragraph of the brief.",
    )
    assert "<script>alert(1)</script>" not in html       # not injected raw
    assert "&lt;script&gt;" in html
    assert html.count("<script>") == 1                    # only our own trusted JS block


def test_brief_works_on_no_changes_page(sample_positions):
    html = render_digest(
        Deltas(), topic="evals", date=RUN_DATE, positions=sample_positions, brief=BRIEF_PROSE,
    )
    assert "The Brief" in html
    assert "No changes since the last run" in html
    assert 'class="state-appendix"' in html              # list still collapsed on quiet runs


# --- committed eyeball sample stays in sync ---------------------------------


def test_committed_sample_matches_current_renderer(sample_deltas, sample_positions):
    """The committed fixtures/digest-sample/*.html must equal a fresh render, so the
    eyeball sample never drifts from the code (regenerate via scripts/render_digest.py)."""
    sample_path = FIXTURES_DIR / "digest-sample" / "2025-10-15-evals.html"
    if not sample_path.exists():
        pytest.skip("digest sample not generated yet")
    expected = render_digest(
        sample_deltas, topic="evals", date=RUN_DATE, positions=sample_positions,
        previous_date=dt.date(2025, 9, 20),
    )
    assert sample_path.read_text("utf-8") == expected
