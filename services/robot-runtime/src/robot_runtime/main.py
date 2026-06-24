"""robot-runtime FastAPI application."""

from __future__ import annotations

import os

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from robot_runtime import routes
from robot_runtime.adapters.fake import FakeRobotAdapter
from robot_runtime.engine.behavior import BehaviorEngine
from shared_events.broadcaster import WebSocketBroadcaster
from shared_events.bus import AsyncEventBus
from shared_personas import Persona


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    bus = AsyncEventBus()
    await bus.start()

    adapter_type = os.environ.get("ROBOT_ADAPTER", "fake")
    if adapter_type == "fake":
        adapter = FakeRobotAdapter()
    else:
        raise ValueError(f"Unknown ROBOT_ADAPTER: {adapter_type!r}")

    await adapter.connect()

    persona_str = os.environ.get("ACTIVE_PERSONA", "work")
    try:
        persona = Persona(persona_str)
    except ValueError:
        persona = Persona.WORK

    session_id = os.environ.get("DEFAULT_SESSION_ID", "default")
    engine = BehaviorEngine(adapter, bus, session_id=session_id, persona=persona)
    await engine.start()

    broadcaster = WebSocketBroadcaster(bus)

    # On-device offline behavior when the brain link drops (U15).
    from robot_runtime.offline_loop import OfflineBehaviorLoop

    offline_loop = OfflineBehaviorLoop(
        engine, bus, session_id=session_id,
        timeout_s=float(os.environ.get("BRAIN_LINK_TIMEOUT_S", "15")),
    )
    offline_loop.start()

    # Inject into routes module
    routes.adapter = adapter
    routes.engine = engine
    routes.broadcaster = broadcaster
    routes.offline_loop = offline_loop

    yield

    await offline_loop.stop()
    await engine.stop()
    await adapter.disconnect()
    await bus.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title="AURA Robot Runtime",
        version="0.1.0",
        lifespan=lifespan,
    )
    origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(routes.router)
    return app


app = create_app()


def run() -> None:
    import uvicorn
    uvicorn.run(
        "robot_runtime.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8001)),
        reload=os.environ.get("RELOAD", "false").lower() == "true",
    )
