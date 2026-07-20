"""memory-service FastAPI application."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from shared_events.bus import AsyncEventBus

from memory_service import routes
from memory_service.db.session import init_db
from memory_service.scheduler import ReminderScheduler
from memory_service.store import SQLiteMemoryStore


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_db()

    store = SQLiteMemoryStore()
    routes.set_store(store)

    bus = AsyncEventBus()
    await bus.start()

    session_id = os.environ.get("DEFAULT_SESSION_ID", "default")
    scheduler = ReminderScheduler(store, bus, session_id=session_id)
    await scheduler.start()

    yield

    await scheduler.stop()
    await bus.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title="AURA Memory Service",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(routes.router)
    return app


app = create_app()


def run() -> None:
    import uvicorn
    uvicorn.run(
        "memory_service.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8005)),
        reload=os.environ.get("RELOAD", "false").lower() == "true",
    )
