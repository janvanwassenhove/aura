"""conversation-runtime FastAPI application."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from conversation_runtime import routes
from conversation_runtime.session_manager import SessionManager
from shared_events.bus import AsyncEventBus
from shared_schemas.voice.providers import STTProvider, TTSProvider


def _build_stt() -> STTProvider:
    provider = os.environ.get("STT_PROVIDER", "local_whisper")
    if provider in ("null", "none"):
        from conversation_runtime.providers.null_provider import NullSTTProvider
        return NullSTTProvider()
    if provider == "openai_realtime":
        from conversation_runtime.providers.openai_provider import OpenAISTTProvider
        return OpenAISTTProvider()
    from conversation_runtime.providers.local_provider import LocalWhisperSTTProvider
    return LocalWhisperSTTProvider(model_size=os.environ.get("WHISPER_MODEL", "base"))


def _build_tts() -> TTSProvider:
    provider = os.environ.get("TTS_PROVIDER", "kokoro")
    if provider in ("null", "none"):
        from conversation_runtime.providers.null_provider import NullTTSProvider
        return NullTTSProvider()
    if provider == "openai":
        from conversation_runtime.providers.openai_provider import OpenAITTSProvider
        return OpenAITTSProvider()
    from conversation_runtime.providers.local_provider import KokoroTTSProvider
    return KokoroTTSProvider()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    bus = AsyncEventBus()
    await bus.start()

    stt = _build_stt()
    tts = _build_tts()
    sessions = SessionManager()

    orchestrator_url = os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:8003")
    memory_url = os.environ.get("MEMORY_SERVICE_URL", "http://memory-service:8005")

    routes.init(stt, tts, bus, sessions, orchestrator_url=orchestrator_url, memory_url=memory_url)

    yield

    await bus.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title="AURA Conversation Runtime",
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
        "conversation_runtime.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8002)),
        reload=os.environ.get("RELOAD", "false").lower() == "true",
    )
