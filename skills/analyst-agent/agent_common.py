"""Shared plumbing for every analyst-agent report type.

Each report type (initiation of coverage, earnings update, sector report,
quarterly outlook, trading report) drives its own Claude tool-use conversation
against its own tool vocabulary and system prompt. The conversation mechanics
-- constructing a client, running the turn loop, collecting ``tool_use``
blocks -- are identical across all of them, so they live here once instead of
being copy-pasted into every report module.

Nothing in this module knows about workspace state or report rendering; it is
purely "evidence + prompt in, tool calls out".
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence


#: Highest-reasoning model available for research synthesis. Override
#: per-agent with the ``model`` constructor argument on any report agent.
DEFAULT_MODEL = "claude-opus-5"

#: Non-streaming ceiling that stays clear of SDK HTTP timeouts.
DEFAULT_MAX_TOKENS = 16000

#: Safety valve on the tool-use loop. Each turn is one API round trip.
DEFAULT_MAX_TURNS = 12


class AgentRunError(RuntimeError):
    """Raised when a report agent cannot complete a run."""


@dataclass
class ToolResult:
    """One ``tool_use`` block emitted by Claude.

    Attributes:
        name: Tool name, e.g. ``record_assumption``.
        input: Decoded tool input object.
        tool_use_id: The block id, used to correlate ``tool_result`` replies.
    """

    name: str
    input: Dict[str, Any]
    tool_use_id: str = ""


def name_value_array_schema(description: str) -> Dict[str, Any]:
    """Strict-mode schema for a list of name/value pairs.

    Every tool in this package runs under Anthropic's ``strict`` schema
    validation, which needs fully specified shapes rather than a free-form
    object. This is the standard way every report type represents an
    open-ended map (valuation inputs, per-scenario assumption deltas, ...) as
    a strict-compatible array instead.
    """

    return {
        "type": "array",
        "description": description,
        "items": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Entry name, e.g. peer_pe."},
                "value": {"type": "string", "description": "Entry value as text, e.g. 18.0."},
            },
            "required": ["name", "value"],
            "additionalProperties": False,
        },
    }


def as_mapping(payload: Any) -> Dict[str, Any]:
    """Normalize a name/value collection (see :func:`name_value_array_schema`) into a dict.

    Plain objects are accepted too, for callers that build tool results by hand
    (tests, offline fixtures) rather than receiving them from the SDK.
    """

    if isinstance(payload, dict):
        return dict(payload)
    if isinstance(payload, (list, tuple)):
        mapping: Dict[str, Any] = {}
        for item in payload:
            if isinstance(item, dict) and "name" in item:
                mapping[str(item.get("name", "")).strip()] = item.get("value")
        return mapping
    return {}


def block_attribute(block: Any, name: str, default: Any = None) -> Any:
    """Read an attribute from an SDK content block or a plain dict.

    The real Anthropic SDK returns typed content-block objects; tests and
    scripted fakes commonly use plain dicts instead. Every caller in this
    package needs to accept either.
    """

    if isinstance(block, dict):
        return block.get(name, default)
    return getattr(block, name, default)


def build_client(anthropic_api_key: Optional[str], client: Any) -> Any:
    """Return ``client`` if supplied, else construct an ``anthropic.Anthropic``.

    The SDK is imported lazily so that importing this module -- and running the
    offline test suite -- never requires ``anthropic`` to be installed.

    Args:
        anthropic_api_key: API key. Falls back to ``ANTHROPIC_API_KEY``, which
            the SDK also resolves on its own.
        client: A pre-built client, or any object exposing ``messages.create``.
            Supplying one skips SDK construction entirely.

    Raises:
        AgentRunError: If no client was supplied and ``anthropic`` cannot be
            imported.
    """

    if client is not None:
        return client
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - depends on host env
        raise AgentRunError(
            "the anthropic SDK is required for live runs: pip install anthropic"
        ) from exc
    api_key = anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
    return anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()


def run_tool_loop(
    client: Any,
    model: str,
    system_prompt: str,
    tool_definitions: Sequence[Dict[str, Any]],
    user_prompt: str,
    max_turns: int = DEFAULT_MAX_TURNS,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> List[ToolResult]:
    """Run one tool-use conversation and collect every tool call Claude makes.

    Tool results sent back to the model are acknowledgements only ("recorded");
    the actual workspace write happens after the conversation, in one
    deterministic pass owned by the caller, so a mid-conversation failure
    cannot leave persistent state half-written.

    A ``pause_turn`` stop reason (the model wants to keep reasoning past a
    single response) is resumed automatically rather than treated as done.

    Args:
        client: An Anthropic client, or any object exposing ``messages.create``.
        model: Claude model id.
        system_prompt: The report type's system prompt.
        tool_definitions: The report type's tool schemas.
        user_prompt: The user turn carrying evidence and the work order.
        max_turns: Maximum tool-use round trips before the run is cut short.
        max_tokens: Per-turn token ceiling.

    Returns:
        Every ``tool_use`` block collected, across every turn, in emission order.
    """

    messages: List[Dict[str, Any]] = [{"role": "user", "content": user_prompt}]
    collected: List[ToolResult] = []

    for _ in range(max_turns):
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            tools=list(tool_definitions),
            thinking={"type": "adaptive"},
            messages=messages,
        )
        content = list(getattr(response, "content", []) or [])
        stop_reason = getattr(response, "stop_reason", None)

        if stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": content})
            continue

        tool_blocks = [block for block in content if block_attribute(block, "type") == "tool_use"]
        if not tool_blocks:
            break

        messages.append({"role": "assistant", "content": content})
        tool_results = []
        for block in tool_blocks:
            collected.append(
                ToolResult(
                    name=str(block_attribute(block, "name", "")),
                    input=block_attribute(block, "input", {}) or {},
                    tool_use_id=str(block_attribute(block, "id", "")),
                )
            )
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block_attribute(block, "id", ""),
                    "content": "recorded",
                }
            )
        # All results for one assistant turn go back in a single user message.
        messages.append({"role": "user", "content": tool_results})

    return collected
