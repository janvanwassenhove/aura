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
