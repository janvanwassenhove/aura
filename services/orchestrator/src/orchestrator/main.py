"""orchestrator FastAPI application."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from shared_events.bus import AsyncEventBus
from shared_personas import Persona

from orchestrator import routes
from orchestrator.approval_manager import ApprovalManager
from orchestrator.context_builder import ContextBuilder
from orchestrator.fallback_agent import FallbackAgent
from orchestrator.gateway import GatewayManager
from orchestrator.heartbeat import HeartbeatMonitor
from orchestrator.intent_router import IntentRouter
from orchestrator.offline_queue import OfflineQueue
from orchestrator.persona_manager import PersonaManager
from orchestrator.pipeline import OrchestratorPipeline
from orchestrator.presentation import PresentationManager
from orchestrator.webhook_dispatcher import WebhookDispatcher


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    bus = AsyncEventBus()
    await bus.start()

    mode = os.environ.get("ACTIVE_PERSONA", "work")
    try:
        persona = Persona(mode)
    except ValueError:
        persona = Persona.WORK

    intent_router = IntentRouter(mode=mode)
    session_id = os.environ.get("DEFAULT_SESSION_ID", "default")
    approval_mgr = ApprovalManager(bus, session_id=session_id)
    context_builder = ContextBuilder()
    persona_mgr = PersonaManager(initial_persona=persona)
    fallback_agent = FallbackAgent()

    # Offline queue — uses in-memory DB by default; override with OFFLINE_QUEUE_DB
    offline_queue = OfflineQueue(bus)
    await offline_queue.open()

    pipeline = OrchestratorPipeline(
        bus, intent_router, approval_mgr, context_builder, persona_mgr,
        fallback_agent=fallback_agent,
        offline_queue=offline_queue,
    )

    # Heartbeat monitor — only start if service URLs are configured
    hb_services: dict[str, str] = {}
    for svc, env in [
        ("llm", "LLM_HEALTH_URL"),
        ("connector", "CONNECTOR_HEALTH_URL"),
        ("memory", "MEMORY_HEALTH_URL"),
    ]:
        url = os.environ.get(env)
        if url:
            hb_services[svc] = url

    heartbeat: HeartbeatMonitor | None = None
    if hb_services:
        heartbeat = HeartbeatMonitor(bus, hb_services)
        heartbeat.start()
        pipeline.set_heartbeat_monitor(heartbeat)

    presentation_mgr = PresentationManager(bus, session_id=session_id)

    # Gateway — load API keys from env; format: GATEWAY_KEYS="id1:key1,id2:key2"
    api_keys: dict[str, str] = {}
    for pair in os.environ.get("GATEWAY_KEYS", "").split(","):
        pair = pair.strip()
        if ":" in pair:
            kid, raw = pair.split(":", 1)
            api_keys[kid.strip()] = raw.strip()
    gateway_mgr = GatewayManager(
        api_keys=api_keys,
        rate_limit=int(os.environ.get("GATEWAY_RATE_LIMIT", "10")),
    )
    webhook_dispatcher = WebhookDispatcher(bus)

    routes.init(
        intent_router,
        approval_mgr,
        context_builder,
        persona_mgr,
        pipeline,
        presentation_mgr,
        gateway_mgr=gateway_mgr,
        webhook_dispatcher=webhook_dispatcher,
    )

    yield

    if heartbeat:
        await heartbeat.stop()
    await offline_queue.close()
    await webhook_dispatcher.close()
    await bus.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title="AURA Orchestrator",
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
        "orchestrator.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8003)),
        reload=os.environ.get("RELOAD", "false").lower() == "true",
    )
