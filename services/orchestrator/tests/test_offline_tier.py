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
    p._offline_llm_base = "http://localhost:11434/v1"
    p._offline_llm_model = "llama3.1"
    return p


async def test_offline_uses_local_model_when_available(monkeypatch, bus) -> None:
    used: dict = {}

    async def fake_local(messages, *, base_url, model):
        used["base_url"] = base_url
        used["model"] = model
        return {"content": "Local model answer.", "tool_calls": None}

    monkeypatch.setattr(pipeline_mod, "local_chat", fake_local)
    reply = await _pipeline(bus).orchestrate("what's up?", "s1")
    assert reply == "Local model answer."
    assert used["base_url"] == "http://localhost:11434/v1"
    assert used["model"] == "llama3.1"


async def test_offline_falls_back_to_regex_when_local_down(monkeypatch, bus) -> None:
    async def dead_local(messages, *, base_url, model):
        raise ConnectionError("local model not running")

    monkeypatch.setattr(pipeline_mod, "local_chat", dead_local)
    # The regex FallbackAgent handles "time" locally.
    reply = await _pipeline(bus).orchestrate("what time is it?", "s1")
    assert "current time" in reply.lower()  # regex fallback kicked in


async def test_offline_regex_only_when_no_local_base_url(bus) -> None:
    p = _pipeline(bus)
    p._offline_llm_base = None  # no local model configured
    reply = await p.orchestrate("what time is it?", "s1")
    assert "current time" in reply.lower()
