"""Prompt construction for the extraction step.

Forks the *shape* of the UncleTony78 LangChain analyzer — a Pydantic schema turned into
format instructions, with a JSON-only output contract — but hand-writes a compact,
model-friendly schema description instead of dumping ``model_json_schema()`` (clearer
for the model, and it omits the pipeline-only ``unit_id`` field the LLM must not emit).
The system prompt is a stable constant so it can be prompt-cached across a batch; the
per-video transcript is the only varying part and lives in the user prompt.
"""

from __future__ import annotations

from collections.abc import Iterable

from kb.extract.transcript import TranscriptSegment, render_transcript

__all__ = ["SYSTEM_PROMPT", "build_user_prompt", "build_prompt"]

SYSTEM_PROMPT = """\
You extract structured "units" of content from a transcript of a YouTube talk about AI \
topics, so they can be compared across many videos over time.

A UNIT is any single, self-contained piece of content from the talk — not only a \
thesis. There are two kinds:
  - "claim":   the speaker asserts something (a position, finding, prediction, or \
recommendation).
  - "content": value-adding material that is NOT phrased as an assertion (a definition, \
a walkthrough, an example, framing, a caveat).
Prefer "claim" whenever there is a genuine assertion; use "content" otherwise. Most \
units in an opinionated talk are claims.

Extract every distinct unit worth comparing later. Do NOT merge two different points \
into one unit, and do NOT split a single point across several units. Skip pure filler \
(greetings, "let's dive in", music, sign-offs).

For each unit produce EXACTLY these fields and no others:
  - "type":            "claim" or "content".
  - "text":            a normalized, self-contained statement of the point, in your own \
words, that reads correctly on its own without the surrounding transcript. One or two \
sentences.
  - "raw_quote":       a verbatim span copied from the transcript that this unit is \
drawn from. Copy it exactly; do not paraphrase.
  - "timestamp":       the start time of the raw quote, taken from the [M:SS] marker on \
the line it begins on, written as that same clock string (e.g. "2:41") or as a number \
of seconds.
  - "stance":          the speaker's polarity toward the subject of "text":
        "affirms"  -> asserts it is true / holds / is good,
        "denies"   -> asserts it is false / does not hold / is bad,
        "neutral"  -> descriptive, takes no side (use this for most "content" units),
        "mixed"    -> holds both sides ("it depends").
  - "evidence_offered": a JSON array of short phrases naming each piece of backing the \
speaker gives for a claim (e.g. "benchmark results", "cites a paper", "personal \
experience", "live demonstration"). Use an empty array [] when no evidence is offered \
(as is normal for "content" units).

Output ONLY a single JSON object of the form:
  {"units": [ {unit}, {unit}, ... ]}
No prose, no markdown, no code fences — just the JSON object. Order the units as they \
occur in the talk."""


def build_user_prompt(
    segments: Iterable[TranscriptSegment], *, max_chars: int | None = None
) -> str:
    """Render the timestamped transcript into the user-turn prompt body."""

    body = render_transcript(segments, max_chars=max_chars)
    return "Here is the transcript. Extract the units as instructed.\n\n" + body


def build_prompt(
    segments: Iterable[TranscriptSegment], *, max_chars: int | None = None
) -> tuple[str, str]:
    """Return ``(system_prompt, user_prompt)`` for the extraction call."""

    return SYSTEM_PROMPT, build_user_prompt(segments, max_chars=max_chars)
