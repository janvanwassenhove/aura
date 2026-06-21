"""Tool-calling path tests — verify the LLM `tools=` wiring and the OpenAI-shaped
follow-up message reconstruction, without any network.

These cover the Phase 0b fix: previously the LLM was never given `tools=`, so the
connector path was unreachable.
"""

from __future__ import annotations

import asyncio
import os

import pytest

os.environ.setdefault("LLM_PROVIDER", "echo")

from orchestrator import pipeline as pipeline_mod
from orchestrator.approval_manager import ApprovalManager
from orchestrator.context_builder import ContextBuilder
from orchestrator.intent_router import IntentRouter
from orchestrator.persona_manager import PersonaManager
from orchestrator.pipeline import OrchestratorPipeline
from orchestrator.tool_schemas import build_tool_specs
from shared_events.bus import AsyncEventBus
from shared_schemas.events.orchestrator import ToolCallSucceeded


@pytest.fixture()
async def bus() -> AsyncEventBus:
    b = AsyncEventBus()
    await b.start()
    yield b
    await b.stop()


@pytest.fixture()
def pipeline(bus: AsyncEventBus) -> OrchestratorPipeline:
    return OrchestratorPipeline(
        bus, IntentRouter(mode="work"), ApprovalManager(bus, session_id="test"),
        ContextBuilder(), PersonaManager(),
    )


def test_build_tool_specs_filters_to_allowed_with_schema() -> None:
    specs = build_tool_specs(frozenset({"list_calendar_events_today", "speak", "unknown"}))
    names = [s["function"]["name"] for s in specs]
    assert names == ["list_calendar_events_today"]  # 'speak'/'unknown' have no schema
    assert specs[0]["type"] == "function"


async def test_tool_call_round_trip(monkeypatch, bus, pipeline) -> None:
    """LLM asks for a read tool → connector runs → final answer synthesized."""
    calls: list[dict] = []

    async def fake_llm(messages, tools=None):
        calls.append({"messages": list(messages), "tools": tools})
        if len(calls) == 1:
            # First call: the model must have been given the tool schemas.
            assert tools, "LLM was not advertised any tools — the bug we fixed"
            assert any(t["function"]["name"] == "list_calendar_events_today" for t in tools)
            return {"content": None, "tool_calls": [
                {"id": "call_1", "name": "list_calendar_events_today", "arguments": "{}"},
            ]}
        return {"content": "You have 2 meetings today.", "tool_calls": None}

    async def fake_connector(self, tool_name, arguments):
        return '[{"subject": "Standup"}, {"subject": "Review"}]'

    monkeypatch.setattr(pipeline_mod, "openai_chat", fake_llm)
    monkeypatch.setattr(OrchestratorPipeline, "_call_connector", fake_connector)

    succeeded: list[ToolCallSucceeded] = []
    bus.subscribe(ToolCallSucceeded, lambda e: succeeded.append(e) or asyncio.sleep(0))

    reply = await pipeline.orchestrate("What meetings do I have today?", "s1")
    await asyncio.sleep(0)

    assert reply == "You have 2 meetings today."
    # Second LLM call must carry a valid OpenAI-shaped assistant+tool exchange.
    follow_up = calls[1]["messages"]
    assistant = next(m for m in follow_up if m["role"] == "assistant" and m.get("tool_calls"))
    tool_msg = next(m for m in follow_up if m["role"] == "tool")
    assert assistant["tool_calls"][0]["id"] == "call_1"
    assert tool_msg["tool_call_id"] == "call_1"  # ids must match or OpenAI 400s
    assert len(succeeded) == 1


async def test_every_tool_call_gets_a_response_message(monkeypatch, bus, pipeline) -> None:
    """A blocked tool still needs a matching `tool` message (OpenAI requirement)."""
    async def fake_llm(messages, tools=None):
        # Two tool calls; one allowed-but-mocked, one not allowed in 'work'? Use an
        # unknown tool to force the not-allowed branch.
        if not any(m["role"] == "tool" for m in messages):
            return {"content": None, "tool_calls": [
                {"id": "a", "name": "list_todos", "arguments": "{}"},
                {"id": "b", "name": "advance_slide", "arguments": "{}"},  # not in 'work'
            ]}
        # Assert both tool_calls have responses before we answer.
        tool_ids = {m["tool_call_id"] for m in messages if m["role"] == "tool"}
        assert tool_ids == {"a", "b"}
        return {"content": "done", "tool_calls": None}

    async def fake_connector(self, tool_name, arguments):
        return "ok"

    monkeypatch.setattr(pipeline_mod, "openai_chat", fake_llm)
    monkeypatch.setattr(OrchestratorPipeline, "_call_connector", fake_connector)

    reply = await pipeline.orchestrate("do things", "s2")
    assert reply == "done"
