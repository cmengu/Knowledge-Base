"""The LLM seam for extraction.

The extractor depends on the narrow :class:`LLMClient` protocol — ``complete(system,
prompt, model) -> str`` — not on any concrete SDK. That injection point is what makes
the extraction step deterministically testable: tests pass a fake (or a fixture-replay)
client and never make a live call, while production passes :class:`AgentSDKClient`.

:class:`AgentSDKClient` drives the pipeline on the Claude *subscription* via the Claude
Agent SDK (research finding #1: the Agent SDK draws from the bundled monthly Agent-SDK
credit, not the metered API). The SDK is imported lazily inside the client so importing
``kb.extract`` — as the test suite does — never requires the SDK or its ``claude`` CLI.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

__all__ = ["LLMClient", "AgentSDKClient", "ExtractionError", "LLMError", "DEFAULT_MAX_TURNS"]

# Belt-and-braces for long transcripts (ticket #18). A single extraction turn caps how
# much JSON the model can emit; a dense transcript busts it and the SDK aborts with
# "Reached maximum number of turns (1)". Allowing several turns lets the model continue
# its own output across turns, so a chunk whose units don't fit one turn still completes.
# Chunking bounds each call's size; this keeps a dense chunk from failing at the boundary.
DEFAULT_MAX_TURNS = 8


class ExtractionError(Exception):
    """Raised when a transcript cannot be turned into validated units.

    Covers both LLM-side failures (surfaced by :class:`AgentSDKClient`) and payload
    failures in the extractor (non-JSON output, or JSON that violates the schema).
    """


# Backwards-friendly alias: the LLM-transport failure is a kind of ExtractionError.
LLMError = ExtractionError


@runtime_checkable
class LLMClient(Protocol):
    """A single-turn text-in / text-out LLM, selectable per call by model.

    Implementations must return the model's raw textual response (expected to contain a
    JSON object). They must raise :class:`ExtractionError` on any transport/LLM failure
    rather than returning a sentinel, so the extractor can treat a returned string as
    "the model produced output".
    """

    def complete(self, *, system: str, prompt: str, model: str) -> str: ...


class AgentSDKClient:
    """Real :class:`LLMClient` backed by the Claude Agent SDK (subscription credit).

    Runs a stateless, tool-free query so the model does pure extraction — no file access,
    no repo settings — and returns the assembled text. ``max_turns`` allows the model to
    continue its own output across turns (:data:`DEFAULT_MAX_TURNS`); see ticket #18. Used
    by the prototype scripts; never exercised by the test suite.
    """

    def __init__(self, *, cwd: str | None = None, max_turns: int = DEFAULT_MAX_TURNS) -> None:
        self._cwd = cwd
        self._max_turns = max_turns

    def complete(self, *, system: str, prompt: str, model: str) -> str:
        import anyio

        return anyio.run(self._acomplete, system, prompt, model)

    async def _acomplete(self, system: str, prompt: str, model: str) -> str:
        # Lazy import: keeps `import kb.extract` free of the SDK / `claude` CLI so the
        # test suite (which only touches the protocol + a fake) needs neither.
        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            ResultMessage,
            TextBlock,
            query,
        )

        options = ClaudeAgentOptions(
            model=model,
            system_prompt=system,
            max_turns=self._max_turns,
            allowed_tools=[],          # pure text extraction — grant no tools
            setting_sources=None,      # ignore any project/user CLAUDE.md and settings
            cwd=self._cwd,
        )

        text_parts: list[str] = []
        result_text: str | None = None
        try:
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, AssistantMessage):
                    if message.error:
                        raise ExtractionError(f"Agent SDK reported error: {message.error}")
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            text_parts.append(block.text)
                elif isinstance(message, ResultMessage):
                    if message.is_error:
                        detail = message.result or (message.errors and "; ".join(message.errors))
                        raise ExtractionError(f"Agent SDK query failed: {detail}")
                    result_text = message.result
        except ExtractionError:
            raise
        except Exception as exc:  # transport / CLI / decode errors -> uniform failure
            raise ExtractionError(f"Agent SDK query failed: {exc}") from exc

        # ResultMessage.result is the authoritative final text; fall back to the
        # concatenated assistant text blocks if it is absent.
        text = result_text if result_text is not None else "".join(text_parts)
        if not text.strip():
            raise ExtractionError("Agent SDK returned no text output")
        return text
