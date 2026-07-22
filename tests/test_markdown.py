"""Markdown rendering tests (ticket #06).

The Markdown is the human-readable, git-diffable view of a topic's positions. These
assert the spec-load-bearing content is present — both stances of a contested position
quoted with source + date, and the status timeline — and that rendering is deterministic.
Cosmetic wording is not pinned beyond what the spec requires.
"""

from __future__ import annotations

import datetime as dt

from kb.reconcile import Maturity, Position, PositionSource, render_markdown

T0 = dt.datetime(2025, 5, 11, 9, 0)
T1 = dt.datetime(2025, 6, 15, 9, 0)


def make_source(**overrides) -> PositionSource:
    base = dict(
        unit_id="vidA#1",
        video_id="vidA",
        date="2025-05-11",
        alignment="supporting",
        stance="affirms",
        quote="you need to build your own evals",
        statement="Build your own evals.",
    )
    base.update(overrides)
    return PositionSource(**base)


def make_position(**overrides) -> Position:
    base = dict(
        position_id="evals-0001",
        topic="evals",
        statement="You should build your own task-specific evals.",
        at=T0,
        first_source=make_source(),
    )
    base.update(overrides)
    return Position.create(**base)


def contested_position() -> Position:
    pos = make_position()
    pos.add_source(
        make_source(
            unit_id="vidB#3",
            video_id="vidB",
            date="2025-06-15",
            alignment="opposing",
            stance="denies",
            quote="public benchmarks are enough on their own",
            statement="Public benchmarks are sufficient.",
        ),
        at=T1,
    )
    pos.record_transition(Maturity.contested, at=T1, reason="a credible dissent", trigger_unit_id="vidB#3")
    return pos


def test_empty_topic_renders_valid_document():
    out = render_markdown([], topic="evals")
    assert out.startswith("# Knowledge base — evals")
    assert "No positions yet" in out
    assert out.endswith("\n")


def test_header_reports_position_and_contested_counts():
    out = render_markdown([make_position(), contested_position()], topic="evals")
    # two positions, one of them contested
    assert "2 position(s), 1 contested" in out


def test_contested_shows_both_stances_with_quote_source_and_date():
    out = render_markdown([contested_position()], topic="evals")
    assert "**Supporting**" in out
    assert "**Opposing**" in out
    # supporting side: quote + video + date
    assert "you need to build your own evals" in out
    assert "vidA" in out and "2025-05-11" in out
    # opposing side: the *other* claim, quoted, with its own source + date
    assert "public benchmarks are enough on their own" in out
    assert "vidB" in out and "2025-06-15" in out


def test_uncontested_position_uses_single_sources_list():
    out = render_markdown([make_position()], topic="evals")
    assert "**Sources**" in out
    assert "**Opposing**" not in out                  # nothing to contest


def test_status_history_shows_transitions_with_dates():
    out = render_markdown([contested_position()], topic="evals")
    assert "**Status history**" in out
    assert "opened as open-question" in out
    assert "emerging-trend → contested" not in out    # this one jumped straight to contested
    assert "open-question → contested" in out
    assert "2025-06-15" in out                         # when it was contested
    assert "`vidB#3`" in out                           # the triggering unit is cited


def test_maturity_badge_appears_in_heading():
    out = render_markdown([make_position()], topic="evals")
    assert "evals-0001" in out
    assert "open question" in out                      # from MATURITY_BADGE


def test_rendering_is_deterministic():
    positions = [contested_position(), make_position(position_id="evals-0002")]
    assert render_markdown(positions, topic="evals") == render_markdown(positions, topic="evals")
