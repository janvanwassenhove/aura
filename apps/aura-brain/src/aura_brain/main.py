"""aura-brain — unified FastAPI process for the laptop-side modules.

Phase 1, step 1 (this file): the inert SCAFFOLD — one FastAPI app that owns the
single shared ``AsyncEventBus`` and the ``WebSocketBroadcaster``, exposing
``/health`` and ``/ws/events``. No service routers are mounted yet.

Phase 1, step 2 (next): mount each module's router against THIS shared bus, in
the order below (smallest blast radius first). See ``docs/phase-1-design.md``.

    MOUNT ORDER (step 2):
      1. memory      — routes.init(store, bus);            include_router
      2. identity    — refactor app-level routes -> APIRouter; include_router
      3. connector   — routes.init(registry, bus);         include_router
      4. conversation— routes.init(stt, tts, bus, ...);     include_router
      5. orchestrator— routes.init(pipeline, ... bus);      include_router

Each module's ``routes.init(...)`` is called with the ONE bus created here so the
broadcaster carries the whole event stream (today each service has its own bus).
The seams (in-process vs HTTP) are flipped per ``docs/phase-1-design.md`` step 3 —
NOT in this scaffold.

The brain↔robot-runtime boundary stays a network hop (the Pi) and is never merged.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from shared_events.bus import AsyncEventBus
from shared_events.broadcaster import WebSocketBroadcaster


class BrainContext:
    """Holds the process-wide singletons shared by all mounted modules.

    In step 2 this grows to own the MemoryStore, TokenStore, connector registry,
    pipeline, persona manager, heartbeat, etc. — all built once and shared in
    process instead of reached over HTTP.
    """

    def __init__(self) -> None:
        self.bus = AsyncEventBus()
        self.broadcaster = WebSocketBroadcaster(self.bus)
        # Module singletons (populated in lifespan as modules are mounted).
        self.memory_store = None
        self._reminder_scheduler = None


ctx = BrainContext()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await ctx.bus.start()

    # --- U1: memory module (shares ctx.bus) ---
    # Ensure the default file-backed SQLite dir exists for real runs (tests
    # override DATABASE_URL with :memory:).
    if "/:memory:" not in os.environ.get("DATABASE_URL", ""):
        os.makedirs("./data", exist_ok=True)

    from memory_service import routes as memory_routes
    from memory_service.db.session import init_db
    from memory_service.scheduler import ReminderScheduler
    from memory_service.store import SQLiteMemoryStore

    await init_db()
    ctx.memory_store = SQLiteMemoryStore()
    memory_routes.set_store(ctx.memory_store)
    session_id = os.environ.get("DEFAULT_SESSION_ID", "default")
    ctx._reminder_scheduler = ReminderScheduler(ctx.memory_store, ctx.bus, session_id=session_id)
    await ctx._reminder_scheduler.start()

    # step 2 (next units): identity, connector, conversation, orchestrator
    # step 2: start heartbeat (brain↔robot link), offline queue

    yield

    if ctx._reminder_scheduler is not None:
        await ctx._reminder_scheduler.stop()
    await ctx.bus.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="AURA Brain", version="0.1.0", lifespan=lifespan)

    origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok", "service": "aura-brain", "phase": "1-scaffold"})

    @app.websocket("/ws/events")
    async def ws_events(websocket: WebSocket) -> None:
        await ctx.broadcaster.connect(websocket)
        try:
            await websocket.receive_text()
        finally:
            ctx.broadcaster.disconnect(websocket)

    # --- step 2 mounts (see module docstring for order) ---
    from memory_service import routes as memory_routes
    app.include_router(memory_routes.router)  # U1

    from identity_service.main import router as identity_router
    app.include_router(identity_router)  # U2

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run(
        "aura_brain.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        reload=os.environ.get("RELOAD", "false").lower() == "true",
    )
