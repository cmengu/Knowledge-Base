"""The routing step: :class:`ExtractedVideo` -> validated :class:`RoutedVideo`.

This is the deterministic seam of Layer 3. Everything non-deterministic sits behind the
injected :class:`~kb.extract.llm.LLMClient` (the shared ticket-#02 mechanism, which
issue-4 committed under ``kb.extract.llm``); given a client, ``route_video`` is a pure
function of its inputs. The flow:

    units --prompt(topics)--> LLM.complete --extract JSON--> validate(RoutingPayload)
          --normalize+check topics, join by unit_id, check coverage--> RoutedVideo

Two behaviors are load-bearing and are what the tests pin:

* **Escalation.** The primary (Haiku) call runs first; if its output fails validation —
  non-JSON, schema-invalid, an unknown topic, an uncovered unit — the step retries once
  on the fallback (Sonnet) model. A *transport* failure from the client is not a
  validation failure and is not escalated; it propagates.
* **Config-driven topic set.** The set of legal topics is injected (from
  ``config/topics.yaml``), used both to build the prompt and to reject any topic the
  model returns that is not in the set. Adding a topic in config makes it assignable with
  no code change.
"""

from __future__ import annotations

import re

from pydantic import ValidationError

from kb.config import load_topics
from kb.extract.extractor import extract_json_object
from kb.extract.llm import ExtractionError, LLMClient
from kb.extract.schema import ExtractedVideo
from kb.route.config import RoutingConfig
from kb.route.prompt import build_prompt
from kb.route.schema import RoutedUnit, RoutedVideo, RoutingPayload

__all__ = ["RoutingError", "route_video", "units_for_downstream"]


class RoutingError(Exception):
    """Raised when the LLM output cannot be turned into a validated ``RoutedVideo``.

    Covers non-JSON output, JSON that violates :class:`RoutingPayload`, a topic outside
    the configured set, a unit assigned no topic, and coverage gaps (a missing or unknown
    unit id). These are exactly the failures that trigger the Haiku->Sonnet escalation.
    """


_NORM = re.compile(r"[\s_]+")


def _normalize(token: str) -> str:
    """Fold trivial formatting drift so ``"Small Models"``/``"small_models"`` match.

    Lower-cases, trims, and collapses internal whitespace/underscores to a single hyphen.
    This forgives cosmetic variation while still rejecting genuinely-unknown topics.
    """

    return _NORM.sub("-", token.strip().lower())


def _resolve_topics(raw_topics: list[str], canonical: dict[str, str], *, where: str) -> list[str]:
    """Map returned topics to canonical config keys; reject unknowns; dedupe in order."""

    resolved: list[str] = []
    seen: set[str] = set()
    for raw in raw_topics:
        key = canonical.get(_normalize(raw))
        if key is None:
            raise RoutingError(
                f"routing for {where} returned unknown topic {raw!r}; "
                f"allowed: {sorted(canonical.values())}"
            )
        if key not in seen:
            seen.add(key)
            resolved.append(key)
    if not resolved:
        raise RoutingError(f"routing for {where} produced no topics")
    return resolved


def _build_routed_video(raw: str, extracted: ExtractedVideo, topics: list[str]) -> RoutedVideo:
    """Parse + validate one raw model response into a ``RoutedVideo`` (raises on any fault)."""

    try:
        payload_json = extract_json_object(raw)
    except ExtractionError as exc:
        raise RoutingError(f"routing output contained no JSON object: {exc}") from exc

    try:
        payload = RoutingPayload.model_validate_json(payload_json)
    except ValidationError as exc:
        raise RoutingError(f"routing output did not match the routing schema: {exc}") from exc

    canonical = {_normalize(topic): topic for topic in topics}
    video_topics = _resolve_topics(payload.video_topics, canonical, where="the video")

    routing_by_id: dict[str, list[str]] = {}
    for entry in payload.units:
        if entry.unit_id in routing_by_id:
            raise RoutingError(f"routing output has duplicate unit id {entry.unit_id!r}")
        routing_by_id[entry.unit_id] = _resolve_topics(
            entry.topics, canonical, where=f"unit {entry.unit_id!r}"
        )

    routed_units: list[RoutedUnit] = []
    input_ids: list[str] = []
    for index, unit in enumerate(extracted.units):
        unit_id = unit.unit_id or f"{extracted.video_id}#{index}"
        input_ids.append(unit_id)
        topics_for_unit = routing_by_id.get(unit_id)
        if topics_for_unit is None:
            raise RoutingError(f"routing output is missing an assignment for unit {unit_id!r}")
        routed_units.append(RoutedUnit(unit=unit, topics=topics_for_unit))

    unknown_ids = set(routing_by_id) - set(input_ids)
    if unknown_ids:
        raise RoutingError(f"routing output references unknown unit ids: {sorted(unknown_ids)}")

    return RoutedVideo(
        video_id=extracted.video_id,
        date=extracted.date,
        topic_tags=video_topics,
        units=routed_units,
    )


def route_video(
    extracted: ExtractedVideo,
    *,
    llm: LLMClient,
    config: RoutingConfig | None = None,
    topics: list[str] | None = None,
) -> RoutedVideo:
    """Route a video and each of its units to one or more topics.

    Parameters
    ----------
    extracted:
        The Layer 2 extraction record whose units are to be routed.
    llm:
        The injected LLM client (real in production, a fake/replay in tests).
    config:
        Routing knobs (model tiers). Defaults are used when omitted.
    topics:
        The legal topic set. Defaults to ``config/topics.yaml`` via
        :func:`kb.config.load_topics`; pass an explicit list to route against a custom set.

    Escalation: the primary ``config.model`` runs first; if its output fails validation,
    the call is retried once on ``config.fallback_model`` (when that differs). If every
    attempt fails validation, the last :class:`RoutingError` is raised.
    """

    config = config or RoutingConfig()
    topics = topics if topics is not None else load_topics()
    if not topics:
        raise RoutingError("no topics configured; routing needs at least one topic")

    if not extracted.units:
        # Nothing to route unit-wise; still ask for the video-level topics.
        return _route_empty(extracted, llm=llm, config=config, topics=topics)

    system, prompt = build_prompt(extracted.units, video_id=extracted.video_id, topics=topics)

    models: list[str] = [config.model]
    if config.fallback_model and config.fallback_model != config.model:
        models.append(config.fallback_model)

    last_error: RoutingError | None = None
    for model in models:
        raw = llm.complete(system=system, prompt=prompt, model=model)
        try:
            return _build_routed_video(raw, extracted, topics)
        except RoutingError as exc:
            last_error = exc  # validation failure -> try the next (stronger) model

    assert last_error is not None  # loop ran at least once
    raise last_error


def _route_empty(
    extracted: ExtractedVideo, *, llm: LLMClient, config: RoutingConfig, topics: list[str]
) -> RoutedVideo:
    """Route a video that has no units: assign the whole configured set at video level.

    A video with zero extracted units is a degenerate input (extraction found nothing to
    compare). Rather than spend an LLM call with an empty unit list, tag it with every
    topic so it is never silently dropped from the slice; there are no units to gate.
    """

    return RoutedVideo(
        video_id=extracted.video_id,
        date=extracted.date,
        topic_tags=list(topics),
        units=[],
    )


def units_for_downstream(
    routed: RoutedVideo, *, slice_topic: str | None
) -> list[RoutedUnit]:
    """Select the units that flow downstream under the slice gate.

    In slice mode (``slice_topic`` set), only units routed to that topic pass — the spec's
    "only ``evals``-routed units flow downstream" rule. ``slice_topic=None`` widens the
    pipeline so every routed unit passes (routing already ran over all topics, so widening
    costs nothing).
    """

    if slice_topic is None:
        return list(routed.units)
    return [routed_unit for routed_unit in routed.units if slice_topic in routed_unit.topics]
