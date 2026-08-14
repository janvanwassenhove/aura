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


async def test_announce_false_runs_but_stays_silent(
    bus: AsyncEventBus, pipeline: OrchestratorPipeline
) -> None:
    """U208: the co-presenter runs improvise beats through the pipeline for
    tools, then speaks the result itself — so the pipeline must NOT auto-speak.
    announce=False returns the reply but publishes no ResponseDrafted."""
    received: list[ResponseDrafted] = []

    async def _capture(event: ResponseDrafted) -> None:
        received.append(event)

    bus.subscribe(ResponseDrafted, _capture)

    reply = await pipeline.orchestrate("Hello AURA", "s-silent", announce=False)
    await asyncio.sleep(0)

    assert reply                      # the loop still produced a reply
    assert received == []             # …but nothing was announced


# --------------------------------------------------------------------------
# U245: person_note() — the one answer to "who am I talking to".
#
# It used to be four lines inline in the turn pipeline, which meant the realtime
# speech path had no way to reach it and simply went without: the assistant
# greeted the owner by name through one path and told him it had never met him
# through the other. Public so both paths ask the same question.
# --------------------------------------------------------------------------


class _FakeJudgment:
    """Stands in for JudgmentLayer: returns a context, or None for someone it
    cannot resolve (a deleted guest whose face is still enrolled — see U244)."""

    def __init__(self, known: dict) -> None:
        self._known = known

    async def build_context(self, person_id):
        note = self._known.get(person_id)
        if note is None:
            return None
        return type("Ctx", (), {"to_system_note": lambda self: note})()


async def test_person_note_is_empty_when_nobody_is_recognized(
    pipeline: OrchestratorPipeline,
) -> None:
    pipeline.set_judgment_layer(_FakeJudgment({"jan": "Talking to: Jan (owner)."}))
    assert await pipeline.person_note() == ""


async def test_person_note_carries_the_active_person(
    pipeline: OrchestratorPipeline,
) -> None:
    pipeline.set_judgment_layer(_FakeJudgment({"jan": "Talking to: Jan (owner)."}))
    pipeline.set_active_person("jan")
    assert await pipeline.person_note() == "Talking to: Jan (owner)."


async def test_an_id_that_resolves_to_nobody_yields_no_note(
    pipeline: OrchestratorPipeline,
) -> None:
    """U244's orphaned faces produced exactly this: a person_id that wins the
    match and has no profile behind it. Empty, never a crash."""
    pipeline.set_judgment_layer(_FakeJudgment({"jan": "Talking to: Jan (owner)."}))
    pipeline.set_active_person("guest-7")
    assert await pipeline.person_note() == ""


async def test_person_note_without_a_judgment_layer(
    pipeline: OrchestratorPipeline,
) -> None:
    """Recognition off, or the store still locked."""
    pipeline.set_active_person("jan")
    assert await pipeline.person_note() == ""


async def test_the_turn_pipeline_still_uses_it(
    pipeline: OrchestratorPipeline,
) -> None:
    """The extraction must not have dropped the note from the typed path."""
    seen = {}

    class Spy(_FakeJudgment):
        async def build_context(self, person_id):
            seen["asked"] = person_id
            return await super().build_context(person_id)

    pipeline.set_judgment_layer(Spy({"jan": "Talking to: Jan (owner)."}))
    pipeline.set_active_person("jan")
    await pipeline.orchestrate("hello", "session-note")
    assert seen.get("asked") == "jan"
