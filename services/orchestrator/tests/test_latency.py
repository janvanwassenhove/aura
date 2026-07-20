"""U23: every turn emits TurnLatencyMeasured with full-turn + stage timings."""

from __future__ import annotations

import asyncio
import os

os.environ.setdefault("LLM_PROVIDER", "echo")

from orchestrator.approval_manager import ApprovalManager
from orchestrator.context_builder import ContextBuilder
from orchestrator.intent_router import IntentRouter
from orchestrator.persona_manager import PersonaManager
from orchestrator.pipeline import OrchestratorPipeline
from shared_events.bus import AsyncEventBus
from shared_schemas.events.system import TurnLatencyMeasured


async def test_turn_emits_latency_event() -> None:
    bus = AsyncEventBus()
    await bus.start()
    measured: list[TurnLatencyMeasured] = []

    async def cap(e: TurnLatencyMeasured) -> None:
        measured.append(e)

    bus.subscribe(TurnLatencyMeasured, cap)

    pipeline = OrchestratorPipeline(
        bus, IntentRouter(mode="work"), ApprovalManager(bus, session_id="t"),
        ContextBuilder(), PersonaManager(),
    )
    await pipeline.orchestrate("hello", "s1")
    # U168: bounded wait instead of a single sleep(0) — bus dispatch may need
    # more than one scheduler hop; on Linux CI one yield wasn't always enough.
    for _ in range(200):
        if measured:
            break
        await asyncio.sleep(0.01)

    assert len(measured) == 1
    evt = measured[0]
    assert evt.total_ms >= 0
    assert evt.llm_ms >= 0          # echo LLM time captured
    assert evt.total_ms >= evt.llm_ms  # total includes the LLM stage
    await bus.stop()
