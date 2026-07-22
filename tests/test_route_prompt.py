"""Prompt-assembly tests for the routing layer (ticket #07).

The routing prompt is *assembled from the configured topic set* — that is the mechanism
behind "config-driven, extensible topics", so it is worth pinning at the seam: the prompt
lists exactly the topics it is given, known topics carry a gloss, and a topic added in
config (with no gloss) is still listed by name. Wording beyond that is not asserted.
"""

from __future__ import annotations

import pytest

from kb.extract import Unit
from kb.route import TOPIC_GLOSSES, build_prompt, build_system_prompt, build_user_prompt


def test_system_prompt_lists_exactly_the_configured_topics():
    system = build_system_prompt(["evals", "harness"])
    assert "- evals:" in system
    assert "- harness:" in system
    assert "enterprise" not in system      # a topic NOT in the set is not listed


def test_known_topics_carry_their_gloss():
    system = build_system_prompt(["evals"])
    assert TOPIC_GLOSSES["evals"] in system


def test_topic_added_in_config_is_listed_without_a_gloss():
    system = build_system_prompt(["evals", "robotics"])
    assert "- robotics" in system          # extensible: new topic still appears
    assert "- robotics:" not in system     # ...by name only, since it has no gloss


def test_all_six_known_topics_have_a_gloss():
    for topic in ["evals", "small-models", "open-source", "harness", "enterprise", "swe-practices"]:
        assert topic in TOPIC_GLOSSES


def test_empty_topic_set_raises():
    with pytest.raises(ValueError):
        build_system_prompt([])


def test_user_prompt_lists_unit_ids_and_text():
    units = [
        Unit(type="claim", text="Evals are a moat.", raw_quote="q", timestamp=1, stance="affirms", unit_id="v#0"),
        Unit(type="content", text="Anatomy of an eval.", raw_quote="q", timestamp=2, stance="neutral", unit_id="v#1"),
    ]
    user = build_user_prompt(units, video_id="v")
    assert "[v#0] Evals are a moat." in user
    assert "[v#1] Anatomy of an eval." in user


def test_user_prompt_falls_back_to_positional_id_when_unit_id_missing():
    units = [Unit(type="claim", text="No id yet.", raw_quote="q", timestamp=1, stance="affirms")]
    user = build_user_prompt(units, video_id="vid")
    assert "[vid#0] No id yet." in user    # matches the extractor's {video_id}#{index} scheme


def test_build_prompt_returns_system_and_user():
    units = [Unit(type="claim", text="x", raw_quote="q", timestamp=1, stance="affirms", unit_id="v#0")]
    system, user = build_prompt(units, video_id="v", topics=["evals"])
    assert "topic router" in system
    assert "[v#0] x" in user
