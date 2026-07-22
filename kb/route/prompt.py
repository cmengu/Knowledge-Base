"""Prompt construction for the topic-routing step.

The system prompt is *assembled from the configured topic set* (spec: the topic set is
extensible in config) rather than hard-coding six topics: the caller passes the topics —
loaded from ``config/topics.yaml`` — and the prompt lists exactly those. Each of the
known six carries a one-line gloss (:data:`TOPIC_GLOSSES`) to sharpen the model's
judgment; a topic added in config that has no gloss is still listed by name and remains
routable, so widening the set never requires touching code.

Only ``unit_id`` + normalized ``text`` are shown per unit — enough to route on, and it
keeps the model's job to "assign topics", not "re-read the transcript".
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from kb.extract.schema import Unit

__all__ = ["TOPIC_GLOSSES", "build_system_prompt", "build_user_prompt", "build_prompt"]

# One-line glosses for the fixed six (spec Implementation Decisions → Topic routing).
# Config may add topics beyond these; unknown topics are listed by name, no gloss.
TOPIC_GLOSSES: Mapping[str, str] = {
    "evals": "evaluation, benchmarks, LLM-as-judge, test datasets, red-teaming, "
    "monitoring — measuring the quality/safety of models or LLM systems.",
    "small-models": "small / efficient / on-device language models, SLMs, "
    "distillation, quantization, and the cost/latency case for smaller models.",
    "open-source": "open-weight and open-source models, tooling, and self-hosting; "
    "the open ecosystem versus closed/proprietary providers.",
    "harness": "agent frameworks, orchestration, tool-use scaffolding, prompt chains, "
    "and the pipelines/harnesses built around models.",
    "enterprise": "enterprise and business adoption — deploying LLMs at companies, ROI, "
    "compliance, security, and organizational rollout.",
    "swe-practices": "software-engineering practice for building with LLMs — testing, "
    "CI/CD, logging, version control, code review, and developer workflow.",
}

_SYSTEM_TEMPLATE = """\
You are a topic router for a knowledge base of YouTube talks about AI.

Given content units extracted from one talk, assign topics from a FIXED set. You classify
at two levels:
  1. the video as a whole -> one or more topics,
  2. each individual unit -> one or more topics.

A unit may belong to SEVERAL topics at once — assign every topic that genuinely applies,
not just one. Assign a topic only when the unit is really about it; do not stretch. Every
unit must receive at least one topic (pick the closest fit if it is borderline).

The FIXED topic set — use ONLY these exact topic keys, nothing else:
{topic_block}

For each unit you are given its id and a one-sentence statement of its content. Output
ONLY a single JSON object of this exact form:
  {{"video_topics": ["<topic>", ...],
    "units": [{{"unit_id": "<id>", "topics": ["<topic>", ...]}}, ...]}}

Rules:
  - Include EXACTLY one entry in "units" for every unit id you were given — no more, none
    missing. Echo each unit_id back exactly as given.
  - "topics" and "video_topics" must be non-empty and contain only keys from the fixed set
    above, spelled exactly.
  - Output the JSON object only: no prose, no markdown, no code fences."""


def _topic_block(topics: Iterable[str]) -> str:
    lines = []
    for topic in topics:
        gloss = TOPIC_GLOSSES.get(topic)
        lines.append(f"  - {topic}: {gloss}" if gloss else f"  - {topic}")
    return "\n".join(lines)


def build_system_prompt(topics: Sequence[str]) -> str:
    """Assemble the routing system prompt for a given (config-driven) topic set."""

    if not topics:
        raise ValueError("routing needs at least one topic in the configured set")
    return _SYSTEM_TEMPLATE.format(topic_block=_topic_block(topics))


def _unit_id_for(unit: Unit, video_id: str, index: int) -> str:
    """The id used to reference a unit in the prompt (extractor's scheme as a fallback)."""

    return unit.unit_id or f"{video_id}#{index}"


def build_user_prompt(units: Sequence[Unit], *, video_id: str) -> str:
    """Render the units to route as ``[unit_id] text`` lines for the user turn."""

    lines = [
        f"[{_unit_id_for(unit, video_id, index)}] {unit.text}"
        for index, unit in enumerate(units)
    ]
    body = "\n".join(lines)
    return (
        "Route the following units from one talk. Assign topics to each unit and to the "
        "video overall, as instructed.\n\n" + body
    )


def build_prompt(
    units: Sequence[Unit], *, video_id: str, topics: Sequence[str]
) -> tuple[str, str]:
    """Return ``(system_prompt, user_prompt)`` for the routing call."""

    return build_system_prompt(topics), build_user_prompt(units, video_id=video_id)
