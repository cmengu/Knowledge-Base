"""Configuration for the topic-routing step (loaded from ``config/routing.yaml``).

Two things are config-driven here, per the spec:

* **model tiers** — routing is a cheap bulk step, so it runs on Haiku, escalating to
  Sonnet only when Haiku's output fails schema validation (spec: cheap tiers for bulk
  routing; ticket #07: "escalate to Sonnet only if Haiku output fails validation").
* **the slice topic** — for the vertical slice only ``evals``-routed units flow
  downstream, but routing itself runs over all configured topics so widening is free.
  ``slice_topic: null`` widens the pipeline to let every routed unit through.

The *topic set* itself is not duplicated here: it lives in ``config/topics.yaml`` (the
single cross-layer source of truth, loaded via :func:`kb.config.load_topics`) and is
injected into :func:`kb.route.classifier.route_video`.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from kb.config import CONFIG_DIR, load_yaml

__all__ = ["RoutingConfig", "load_routing_config"]


class RoutingConfig(BaseModel):
    """Knobs for routing units to topics."""

    model_config = ConfigDict(extra="forbid")

    model: str = Field(
        default="haiku",
        description="Agent SDK model alias/id for routing (Haiku tier — cheap bulk step).",
    )
    fallback_model: str = Field(
        default="sonnet",
        description="Model to retry with when the primary model's output fails schema "
        "validation. Set equal to `model` (or empty) to disable escalation.",
    )
    slice_topic: str | None = Field(
        default="evals",
        description="Slice gate: only units routed to this topic flow downstream. "
        "`null` widens the pipeline so every routed unit passes.",
    )


def load_routing_config(path: str | Path | None = None) -> RoutingConfig:
    """Load :class:`RoutingConfig` from YAML (defaults when the file is absent)."""

    path = Path(path) if path is not None else CONFIG_DIR / "routing.yaml"
    if not path.exists():
        return RoutingConfig()
    return RoutingConfig.model_validate(load_yaml(path) or {})
