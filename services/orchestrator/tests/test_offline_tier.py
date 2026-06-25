"""U21: offline tier prefers a local model, falls back to regex when it's down."""

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
from shared_schemas.robot.models import RobotMode


class _FakeHeartbeat:
    mode = RobotMode.OFFLINE


@pytest.fixture()
async def bus():
    b = AsyncEventBus()
    await b.start()
    yield b
    await b.stop()


def _pipeline(bus) -> OrchestratorPipeline:
    p = OrchestratorPipeline(
        bus, IntentRouter(mode="work"), ApprovalManager(bus, session_id="t"),
        ContextBuilder(), PersonaManager(),
    )
    p.set_heartbeat_monitor(_FakeHeartbeat())
    p._offline_llm = "ollama"
    return p


async def test_offline_uses_local_model_when_available(monkeypatch, bus) -> None:
    used: dict = {}

    async def fake_llm(messages, tools=None, *, provider=None, model=None):
        used["provider"] = provider
        return {"content": "Local model answer.", "tool_calls": None}

    monkeypatch.setattr(pipeline_mod, "openai_chat", fake_llm)
    reply = await _pipeline(bus).orchestrate("what's up?", "s1")
    assert reply == "Local model answer."
    assert used["provider"] == "ollama"  # forced the local provider


async def test_offline_falls_back_to_regex_when_local_down(monkeypatch, bus) -> None:
    async def dead_llm(messages, tools=None, *, provider=None, model=None):
        raise ConnectionError("ollama not running")

    monkeypatch.setattr(pipeline_mod, "openai_chat", dead_llm)
    # The regex FallbackAgent handles "time" locally.
    reply = await _pipeline(bus).orchestrate("what time is it?", "s1")
    assert "current time" in reply.lower()  # regex fallback kicked in
