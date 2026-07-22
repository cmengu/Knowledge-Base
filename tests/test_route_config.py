"""Config-loading tests for the routing layer (ticket #07)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from kb.config import CONFIG_DIR
from kb.route import RoutingConfig, load_routing_config


def test_defaults():
    config = RoutingConfig()
    assert config.model == "haiku"          # cheap bulk tier
    assert config.fallback_model == "sonnet"  # escalation target
    assert config.slice_topic == "evals"    # the vertical slice's gate


def test_loads_committed_routing_yaml():
    config = load_routing_config()          # reads config/routing.yaml
    assert config.model == "haiku"
    assert config.fallback_model == "sonnet"
    assert config.slice_topic == "evals"


def test_committed_routing_yaml_exists():
    assert (CONFIG_DIR / "routing.yaml").exists()


def test_missing_file_returns_defaults(tmp_path):
    config = load_routing_config(tmp_path / "nope.yaml")
    assert config == RoutingConfig()


def test_slice_topic_null_widens(tmp_path):
    path = tmp_path / "routing.yaml"
    path.write_text("model: haiku\nfallback_model: sonnet\nslice_topic: null\n", encoding="utf-8")
    assert load_routing_config(path).slice_topic is None


def test_overrides_from_yaml(tmp_path):
    path = tmp_path / "routing.yaml"
    path.write_text("model: sonnet\nfallback_model: opus\nslice_topic: harness\n", encoding="utf-8")
    config = load_routing_config(path)
    assert (config.model, config.fallback_model, config.slice_topic) == ("sonnet", "opus", "harness")


def test_rejects_unknown_field():
    with pytest.raises(ValidationError):
        RoutingConfig(temperature=0.7)      # extra="forbid": config is fixed
