"""U42: the pipeline remembers the conversation across turns."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("LLM_PROVIDER", "echo")

from orchestrator import pipeline as pipeline_mod
from orchestrator.approval_manager import ApprovalManager
from orchestrator.context_builder import ContextBuilder
from orchestrator.intent_router import IntentRouter
from orchestrator.persona_manager import PersonaManager
from orchestrator.pipeline import OrchestratorPipeline
from shared_events.bus import AsyncEventBus


@pytest.fixture()
async def bus():
    b = AsyncEventBus()
    await b.start()
    yield b
    await b.stop()


def _pipeline(bus) -> OrchestratorPipeline:
    return OrchestratorPipeline(
        bus, IntentRouter(mode="home"), ApprovalManager(bus, session_id="t"),
        ContextBuilder(), PersonaManager(),
    )


async def test_prior_turns_are_sent_to_the_llm(monkeypatch, bus) -> None:
    seen: list[list[dict]] = []

    async def fake_llm(messages, tools=None):
        seen.append(messages)
        return {"content": "ok", "tool_calls": None}

    monkeypatch.setattr(pipeline_mod, "openai_chat", fake_llm)
    p = _pipeline(bus)
    await p.orchestrate("My name is Jan.", "s1")
    await p.orchestrate("What did I just say?", "s1")

    # Second call must include the first exchange (user + assistant) before the
    # new user message.
    second = seen[1]
    contents = [m["content"] for m in second]
    assert "My name is Jan." in contents
    assert "ok" in contents            # remembered assistant reply
    assert second[-1]["content"] == "What did I just say?"
    roles = [m["role"] for m in second]
    assert roles[0] == "system"


async def test_sessions_are_isolated(monkeypatch, bus) -> None:
    captured: list[list[dict]] = []

    async def fake_llm(messages, tools=None):
        captured.append(messages)
        return {"content": "ok", "tool_calls": None}

    monkeypatch.setattr(pipeline_mod, "openai_chat", fake_llm)
    p = _pipeline(bus)
    await p.orchestrate("secret for session A", "A")
    await p.orchestrate("hello from B", "B")
    b_contents = [m["content"] for m in captured[1]]
    assert "secret for session A" not in b_contents


async def test_history_is_capped(monkeypatch, bus) -> None:
    monkeypatch.setenv("MAX_CONTEXT_TURNS", "2")

    async def fake_llm(messages, tools=None):
        return {"content": "reply", "tool_calls": None}

    monkeypatch.setattr(pipeline_mod, "openai_chat", fake_llm)
    p = _pipeline(bus)
    p._max_history = 4  # 2 turns * 2
    for i in range(5):
        await p.orchestrate(f"msg {i}", "s")
    assert len(p._recall("s")) <= 4
