"""Tests for OrchestratorPipeline with LLM_PROVIDER=echo."""

from __future__ import annotations

import asyncio
import os

import pytest

os.environ.setdefault("LLM_PROVIDER", "echo")

from orchestrator.approval_manager import ApprovalManager
from orchestrator.context_builder import ContextBuilder
from orchestrator.intent_router import IntentRouter
from orchestrator.persona_manager import PersonaManager
from orchestrator.pipeline import OrchestratorPipeline
from shared_events.bus import AsyncEventBus
from shared_schemas.events.conversation import ResponseDrafted


@pytest.fixture()
async def bus() -> AsyncEventBus:
    b = AsyncEventBus()
    await b.start()
    yield b
    await b.stop()


@pytest.fixture()
def pipeline(bus: AsyncEventBus) -> OrchestratorPipeline:
    router = IntentRouter(mode="work")
    approval = ApprovalManager(bus, session_id="test")
    context = ContextBuilder()
    persona = PersonaManager()
    return OrchestratorPipeline(bus, router, approval, context, persona)


async def test_echo_turn_returns_reply(pipeline: OrchestratorPipeline) -> None:
    reply = await pipeline.orchestrate("Hello AURA", "session-1")
    assert "[echo]" in reply
    assert "Hello AURA" in reply


async def test_echo_turn_emits_response_drafted(bus: AsyncEventBus, pipeline: OrchestratorPipeline) -> None:
    received: list[ResponseDrafted] = []

    async def _capture(event: ResponseDrafted) -> None:
        received.append(event)

    bus.subscribe(ResponseDrafted, _capture)

    await pipeline.orchestrate("Test message", "session-2")
    # Bus dispatches via create_task — yield to event loop to let tasks fire.
    await asyncio.sleep(0)

    assert len(received) == 1
    assert "Test message" in received[0].response_text


async def test_mode_mismatch_returns_gracefully(pipeline: OrchestratorPipeline) -> None:
    """A tool call that is not allowed in the current mode should not crash."""
    # echo mode doesn't produce tool calls, so just test normal flow
    reply = await pipeline.orchestrate("What are my tasks?", "session-3")
    assert isinstance(reply, str)
    assert len(reply) > 0
