"""Layer 3 — topic routing (ticket #07).

Classifies each video and each individual unit to one or more topics from the fixed,
config-driven set (``config/topics.yaml``). Multi-topic assignment is allowed per unit;
routing runs over every configured topic while the slice gate lets only ``evals`` units
flow downstream. Public surface:

    from kb.route import (
        RoutedUnit, RoutedVideo,                  # the routing result
        RoutingPayload, UnitRouting,              # the LLM-facing contract
        route_video, units_for_downstream,        # the routing step + slice gate
        RoutingError,                             # validation failure (triggers escalation)
        RoutingConfig, load_routing_config,       # config (model tiers, slice topic)
        build_prompt, TOPIC_GLOSSES,              # prompt assembly
    )
"""

from __future__ import annotations

from kb.route.classifier import RoutingError, route_video, units_for_downstream
from kb.route.config import RoutingConfig, load_routing_config
from kb.route.prompt import (
    TOPIC_GLOSSES,
    build_prompt,
    build_system_prompt,
    build_user_prompt,
)
from kb.route.schema import RoutedUnit, RoutedVideo, RoutingPayload, UnitRouting

__all__ = [
    # schema
    "RoutedUnit",
    "RoutedVideo",
    "RoutingPayload",
    "UnitRouting",
    # routing step + slice gate
    "route_video",
    "units_for_downstream",
    "RoutingError",
    # config
    "RoutingConfig",
    "load_routing_config",
    # prompt
    "build_prompt",
    "build_system_prompt",
    "build_user_prompt",
    "TOPIC_GLOSSES",
]
