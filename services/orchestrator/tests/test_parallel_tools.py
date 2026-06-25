"""U25: independent (non-approval) tool calls execute concurrently."""

from __future__ import annotations

import asyncio
import os

os.environ.setdefault("LLM_PROVIDER", "echo")

from orchestrator import pipeline as pipeline_mod
from orchestrator.approval_manager import ApprovalManager
from orchestrator.context_builder import ContextBuilder
from orchestrator.intent_router import IntentRouter
from orchestrator.persona_manager import PersonaManager
from orchestrator.pipeline import OrchestratorPipeline
from shared_events.bus import AsyncEventBus


async def test_independent_tools_run_in_parallel(monkeypatch) -> None:
    bus = AsyncEventBus()
    await bus.start()

    # Three read tools requested in one turn.
    async def fake_llm(messages, tools=None, **kw):
        if not any(m["role"] == "tool" for m in messages):
            return {"content": None, "tool_calls": [
                {"id": "a", "name": "list_calendar_events_today", "arguments": "{}"},
                {"id": "b", "name": "get_unread_mail", "arguments": "{}"},
                {"id": "c", "name": "list_tasks", "arguments": "{}"},
            ]}
        return {"content": "done", "tool_calls": None}

    # Each connector call sleeps 100ms. Sequential → ~300ms; parallel → ~100ms.
    in_flight = 0
    max_in_flight = 0

    async def slow_connector(self, tool_name, arguments):
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.1)
        in_flight -= 1
        return f"[{tool_name} ok]"

    monkeypatch.setattr(pipeline_mod, "openai_chat", fake_llm)
    monkeypatch.setattr(OrchestratorPipeline, "_call_connector", slow_connector)

    pipeline = OrchestratorPipeline(
        bus, IntentRouter(mode="work"), ApprovalManager(bus, session_id="t"),
        ContextBuilder(), PersonaManager(),
    )

    loop = asyncio.get_event_loop()
    t0 = loop.time()
    reply = await pipeline.orchestrate("what's my day look like?", "s1")
    elapsed = loop.time() - t0

    assert reply == "done"
    assert max_in_flight == 3          # all three ran concurrently
    assert elapsed < 0.25              # ~0.1s parallel, not ~0.3s sequential
    await bus.stop()
