"""Shared scripted-Claude-client fakes for analyst-agent report-type tests.

Every report type drives a Claude tool-use conversation through
``agent_common.run_tool_loop``, which only needs an object exposing
``messages.create(**kwargs) -> response`` where ``response`` carries
``.content`` (a list of blocks) and ``.stop_reason``. These fakes stand in for
the real ``anthropic.Anthropic`` client so tests run with no network access
and no SDK dependency, and reproduce the same content-block shapes
(``FakeBlock``) whether built as ``tool_use`` or plain ``text``.

Extracted from ``tests/test_analyst_agent_e2e.py`` so every new report-type
test module can import one shared implementation instead of redefining it.
"""

from __future__ import annotations


class FakeBlock:
    """Stand-in for an SDK content block."""

    def __init__(self, type, name=None, input=None, id=None, text=None):
        self.type = type
        self.name = name
        self.input = input
        self.id = id
        self.text = text


class FakeResponse:
    """Stand-in for an SDK ``Message``."""

    def __init__(self, content, stop_reason):
        self.content = content
        self.stop_reason = stop_reason


class FakeMessages:
    def __init__(self, turns):
        self._turns = list(turns)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self._turns:
            return FakeResponse([FakeBlock("text", text="Done.")], "end_turn")
        return self._turns.pop(0)


class FakeAnthropicClient:
    """Minimal object exposing the one method every report agent calls."""

    def __init__(self, turns):
        self.messages = FakeMessages(turns)


def tool(name, payload, identifier):
    """Build one scripted ``tool_use`` content block."""

    return FakeBlock("tool_use", name=name, input=payload, id=identifier)


def text(content, identifier=None):
    """Build one scripted plain-text content block."""

    return FakeBlock("text", text=content, id=identifier)
