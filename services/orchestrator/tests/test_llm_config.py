"""Tests for LLM runtime config — GET/PATCH /orchestrator/config/llm endpoints
and the config singleton used by llm.py.
"""

from __future__ import annotations

import importlib
import os
import sys

import pytest
from fastapi.testclient import TestClient

# Set echo mode BEFORE importing orchestrator modules so the config singleton
# and any test-time LLM call uses echo (no API keys needed).
os.environ.setdefault("LLM_PROVIDER", "echo")


def _make_client() -> TestClient:
    """Build a minimal FastAPI test client with only the orchestrator router."""
    from fastapi import FastAPI
    from orchestrator import routes as r
    from orchestrator.approval_manager import ApprovalManager
    from orchestrator.context_builder import ContextBuilder
    from orchestrator.intent_router import IntentRouter
    from orchestrator.persona_manager import PersonaManager
    from orchestrator.pipeline import OrchestratorPipeline
    from shared_events.bus import AsyncEventBus

    bus = AsyncEventBus()
    intent_router = IntentRouter(mode="work")
    approval_mgr = ApprovalManager(bus, session_id="test")
    context_builder = ContextBuilder()
    persona_mgr = PersonaManager()
    pipeline = OrchestratorPipeline(bus, intent_router, approval_mgr, context_builder, persona_mgr)

    r.init(
        router_=intent_router,
        approval_mgr=approval_mgr,
        context_builder=context_builder,
        persona_mgr=persona_mgr,
        pipeline=pipeline,
    )

    app = FastAPI()
    app.include_router(r.router)
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_config():
    """Reset the LLM config singleton to env defaults before each test."""
    from orchestrator import config as cfg_mod
    cfg_mod._config = cfg_mod.LLMConfig()
    yield
    cfg_mod._config = cfg_mod.LLMConfig()


@pytest.fixture()
def client() -> TestClient:
    return _make_client()


# ------------------------------------------------------------------
# GET /orchestrator/config/llm
# ------------------------------------------------------------------

def test_get_llm_config_returns_initial_provider(client: TestClient) -> None:
    resp = client.get("/orchestrator/config/llm")
    assert resp.status_code == 200
    data = resp.json()
    # LLM_PROVIDER was set to "echo" before import
    assert data["provider"] == "echo"
    assert "model" in data
    assert "openai_key_set" in data
    assert "openrouter_key_set" in data


def test_get_llm_config_key_set_reflects_env(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    resp = client.get("/orchestrator/config/llm")
    assert resp.status_code == 200
    data = resp.json()
    assert data["openai_key_set"] is True
    assert data["openrouter_key_set"] is False


# ------------------------------------------------------------------
# PATCH /orchestrator/config/llm
# ------------------------------------------------------------------

def test_patch_updates_provider_and_model(client: TestClient) -> None:
    resp = client.patch(
        "/orchestrator/config/llm",
        json={"provider": "openrouter", "model": "openai/gpt-oss-20b:free"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "openrouter"
    assert data["model"] == "openai/gpt-oss-20b:free"


def test_patch_persists_to_get(client: TestClient) -> None:
    client.patch(
        "/orchestrator/config/llm",
        json={"provider": "openai", "model": "gpt-4o"},
    )
    resp = client.get("/orchestrator/config/llm")
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "openai"
    assert data["model"] == "gpt-4o"


def test_patch_invalid_provider_returns_422(client: TestClient) -> None:
    resp = client.patch(
        "/orchestrator/config/llm",
        json={"provider": "banana", "model": "something"},
    )
    assert resp.status_code == 422


def test_patch_echo_provider(client: TestClient) -> None:
    resp = client.patch("/orchestrator/config/llm", json={"provider": "echo", "model": ""})
    assert resp.status_code == 200
    assert resp.json()["provider"] == "echo"


# ------------------------------------------------------------------
# openai_chat respects runtime config (regression: echo path)
# ------------------------------------------------------------------

async def test_openai_chat_uses_runtime_config_echo() -> None:
    from orchestrator.config import update_config
    from orchestrator.llm import openai_chat

    update_config("echo", "")
    result = await openai_chat([{"role": "user", "content": "hello"}])
    assert result["content"].startswith("[echo]")
    assert "hello" in result["content"]
    assert result["tool_calls"] is None


# ------------------------------------------------------------------
# Multi-provider support (anthropic, ollama) — config-level only
# ------------------------------------------------------------------

@pytest.mark.parametrize("provider", ["anthropic", "ollama"])
def test_patch_accepts_new_providers(client: TestClient, provider: str) -> None:
    resp = client.patch("/orchestrator/config/llm", json={"provider": provider, "model": ""})
    assert resp.status_code == 200
    assert resp.json()["provider"] == provider


def test_default_models_for_new_providers() -> None:
    from orchestrator.config import _default_model

    assert _default_model("anthropic").startswith("claude-")
    assert _default_model("ollama")  # non-empty


def test_anthropic_message_conversion_round_trips_tools() -> None:
    """OpenAI-shaped assistant.tool_calls + tool messages → Anthropic blocks."""
    from orchestrator.llm import _to_anthropic

    system, msgs = _to_anthropic([
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "meetings today?"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "c1", "type": "function",
             "function": {"name": "list_calendar_events_today", "arguments": "{}"}},
        ]},
        {"role": "tool", "tool_call_id": "c1", "content": "[2 events]"},
    ])

    assert system == "be brief"
    # assistant turn carries a tool_use block with the right id
    asst = next(m for m in msgs if m["role"] == "assistant")
    tool_use = next(b for b in asst["content"] if b["type"] == "tool_use")
    assert tool_use["id"] == "c1" and tool_use["name"] == "list_calendar_events_today"
    # tool result becomes a user turn with a matching tool_result block
    tr = [b for m in msgs if m["role"] == "user" and isinstance(m["content"], list)
          for b in m["content"] if b["type"] == "tool_result"]
    assert tr and tr[0]["tool_use_id"] == "c1"
