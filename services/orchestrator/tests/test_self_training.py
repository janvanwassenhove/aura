"""U60: self-training — approval-gated save_skill + teach-mode feedback."""

from __future__ import annotations

import json
import os

os.environ.setdefault("LLM_PROVIDER", "echo")

import pytest
from orchestrator import pipeline as pipeline_mod
from orchestrator.approval_manager import ApprovalManager
from orchestrator.context_builder import ContextBuilder
from orchestrator.intent_router import IntentRouter
from orchestrator.persona_manager import PersonaManager
from orchestrator.pipeline import OrchestratorPipeline
from orchestrator.skills import SkillStore
from shared_events.bus import AsyncEventBus
from shared_policies import APPROVAL_REQUIRED, MODE_TOOL_MAP


def test_save_skill_is_approval_gated_and_advertised() -> None:
    assert "save_skill" in APPROVAL_REQUIRED
    assert "save_skill" in MODE_TOOL_MAP["work"]
    assert "save_skill" in MODE_TOOL_MAP["home"]


@pytest.fixture()
async def bus():
    b = AsyncEventBus()
    await b.start()
    yield b
    await b.stop()


def _pipeline(bus, store) -> OrchestratorPipeline:
    p = OrchestratorPipeline(
        bus, IntentRouter(mode="work"), ApprovalManager(bus, session_id="t"),
        ContextBuilder(), PersonaManager(),
    )
    p.set_skill_store(store)
    return p


async def test_agent_learns_a_skill_after_owner_approval(bus, tmp_path, monkeypatch) -> None:
    store = SkillStore(str(tmp_path))
    approvals: list[str] = []

    async def scripted_llm(messages, tools=None, **kw):
        if not any(m["role"] == "tool" for m in messages):
            return {"content": None, "tool_calls": [{
                "id": "s1", "name": "save_skill",
                "arguments": json.dumps({
                    "name": "deploy-flow",
                    "description": "how the owner deploys",
                    "body": "Run tests first, then deploy.",
                    "triggers": ["deploy"],
                    "person": "jan",
                }),
            }]}
        return {"content": "Learned it.", "tool_calls": None}

    async def fake_approval(self, tool_name, arguments):
        approvals.append(tool_name)
        return True

    monkeypatch.setattr(pipeline_mod, "openai_chat", scripted_llm)
    monkeypatch.setattr(ApprovalManager, "request_approval", fake_approval)

    reply = await _pipeline(bus, store).orchestrate(
        "onthou: altijd eerst tests draaien voor een deploy", "s1")

    assert reply == "Learned it."
    assert approvals == ["save_skill"]           # the gate fired
    saved = store.get("deploy-flow")
    assert saved is not None and saved.person == "jan"
    assert "Run tests first" in saved.body


async def test_denied_save_skill_stores_nothing(bus, tmp_path, monkeypatch) -> None:
    from orchestrator.approval_manager import ApprovalDeniedError

    store = SkillStore(str(tmp_path))

    async def scripted_llm(messages, tools=None, **kw):
        if not any(m["role"] == "tool" for m in messages):
            return {"content": None, "tool_calls": [{
                "id": "s1", "name": "save_skill",
                "arguments": json.dumps({"name": "sneaky", "description": "x", "body": "y"}),
            }]}
        return {"content": "Understood, not saving it.", "tool_calls": None}

    async def deny(self, tool_name, arguments):
        raise ApprovalDeniedError(tool_name)

    monkeypatch.setattr(pipeline_mod, "openai_chat", scripted_llm)
    monkeypatch.setattr(ApprovalManager, "request_approval", deny)

    reply = await _pipeline(bus, store).orchestrate("save this", "s1")
    assert reply == "Understood, not saving it."
    assert store.get("sneaky") is None           # nothing written on deny


async def test_self_training_nudge_is_in_the_prompt(bus, tmp_path, monkeypatch) -> None:
    captured: list[str] = []

    async def fake_llm(messages, tools=None, **kw):
        captured.append(messages[0]["content"])
        return {"content": "ok", "tool_calls": None}

    monkeypatch.setattr(pipeline_mod, "openai_chat", fake_llm)
    await _pipeline(bus, SkillStore(str(tmp_path))).orchestrate("hallo", "s1")
    assert "SELF-TRAINING" in captured[0]
    assert "save_skill" in captured[0]
