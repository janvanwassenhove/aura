"""U6: verify the single shared bus carries the whole event stream.

Deterministic proof of the collapse's core invariant: an event produced by the
orchestrator module is delivered on `ctx.bus`, and the WebSocket broadcaster is
wired to that same bus — so one /ws/events carries every module's events.
"""

from __future__ import annotations

import asyncio
import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("LLM_PROVIDER", "echo")
os.environ.setdefault("STT_PROVIDER", "null")
os.environ.setdefault("TTS_PROVIDER", "null")

from aura_brain.main import create_app, ctx
from shared_schemas.events.conversation import ResponseDrafted


async def test_orchestrator_event_lands_on_shared_bus() -> None:
    app = create_app()
    async with app.router.lifespan_context(app):
        received: list[ResponseDrafted] = []

        async def probe(event: ResponseDrafted) -> None:
            received.append(event)

        ctx.bus.subscribe(ResponseDrafted, probe)

        # The orchestrator pipeline (mounted in the brain) runs an echo turn.
        await ctx.pipeline.orchestrate("ping", "sx")
        await asyncio.sleep(0)  # let bus create_task handlers run

        assert received and received[0].response_text  # event delivered on ctx.bus
        # The broadcaster fans out THAT bus → one /ws/events carries everything.
        assert ctx.broadcaster._bus is ctx.bus
        assert ctx.pipeline._bus is ctx.bus


async def test_pipeline_calls_connector_in_process() -> None:
    """U8: the pipeline reaches the mounted (mock) connector in-process via ASGI
    — a real tool call returns mock data, no network, correct /connector prefix."""
    app = create_app()
    async with app.router.lifespan_context(app):
        assert ctx.pipeline._connector_client is not None  # in-process client wired
        result = await ctx.pipeline._call_connector("list_calendar_events_today", {})
        assert "Standup" in result  # mock connector calendar data, end-to-end


def test_conversation_persists_to_memory_in_process() -> None:
    """U9: a conversation turn persists to memory in-process (conversation→memory
    seam), reachable via /memory/turns on the same app — no network hop."""
    from fastapi.testclient import TestClient

    app = create_app()
    with TestClient(app) as client:
        sid = "u9-session"
        turn = client.post("/conversation/turn", json={"text": "remember this", "session_id": sid})
        assert turn.status_code == 200
        stored = client.get(f"/memory/turns/{sid}")
        assert stored.status_code == 200
        contents = [t["content"] for t in stored.json()]
        assert any("remember this" in c for c in contents)  # user turn persisted in-process
