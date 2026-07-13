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
        self.connector_registry = None
        self.knowledge_store = None
        self.pipeline = None
        self._perception = None
        self._offline_queue = None
        self._webhook_dispatcher = None
        self._heartbeat = None
        # One ASGI client routes all intra-brain HTTP-shaped calls in-process
        # (connector, memory, orchestrator) — the Phase 1 seams.
        self._inproc_client = None


ctx = BrainContext()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await ctx.bus.start()

    # One in-process ASGI client for all intra-brain seams (U8/U9): connector,
    # memory, orchestrator calls route back into THIS app — no network hop.
    import httpx
    ctx._inproc_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://aura-brain",
    )

    # --- U1: memory module (shares ctx.bus) ---
    # Ensure the default file-backed SQLite dir exists for real runs (tests
    # override DATABASE_URL with :memory:).
    if "/:memory:" not in os.environ.get("DATABASE_URL", ""):
        os.makedirs("./data", exist_ok=True)

    from memory_service import routes as memory_routes
    from memory_service.db.session import init_db
    from memory_service.scheduler import ReminderScheduler
    from memory_service.store import SQLiteMemoryStore

    # --- U19d: knowledge store (ADR-008). Encrypted at rest if a passphrase is
    # set (OMK via scrypt), else in-memory for dev. ---
    from aura_brain import knowledge_api
    from shared_schemas.knowledge import (
        EncryptedKnowledgeStore,
        InMemoryKnowledgeStore,
        crypto,
    )

    _kpass = os.environ.get("KNOWLEDGE_PASSPHRASE")
    if _kpass:
        _salt = os.environ.get("KNOWLEDGE_SALT", "aura-knowledge").encode().ljust(16, b"0")[:16]
        # U29: ciphertext bundles persist across restarts (ciphertext-only file).
        _kpath = os.environ.get("KNOWLEDGE_DB_PATH", "./data/knowledge.enc.json")
        ctx.knowledge_store = EncryptedKnowledgeStore(
            crypto.derive_omk(_kpass, _salt), path=_kpath,
        )
    else:
        ctx.knowledge_store = InMemoryKnowledgeStore()
    knowledge_api.set_store(ctx.knowledge_store)
    knowledge_api.set_omk_loaded(bool(_kpass))

    # U19c: step-up gate for destructive knowledge operations (ADR-008 §9).
    from aura_brain.stepup_gate import StepUpGate

    _stepup_gate = StepUpGate()  # reads STEP_UP_WEBHOOK_URL + BRAIN_BASE_URL from env
    knowledge_api.set_stepup_gate(_stepup_gate)

    await init_db()
    ctx.memory_store = SQLiteMemoryStore()
    memory_routes.set_store(ctx.memory_store)
    session_id = os.environ.get("DEFAULT_SESSION_ID", "default")
    ctx._reminder_scheduler = ReminderScheduler(ctx.memory_store, ctx.bus, session_id=session_id)
    await ctx._reminder_scheduler.start()

    # --- U3: connector module ---
    from connector_service import routes as connector_routes
    from connector_service.registry import ConnectorRegistry
    from shared_config import ConnectorServiceSettings

    # U7 seam: connectors fetch tokens from identity in-process (no HTTP hop).
    from identity_service.main import get_valid_token as _identity_token

    connector_registry = ConnectorRegistry(
        settings=ConnectorServiceSettings(), token_fetcher=_identity_token,
    )
    connector_registry.build()
    primary = connector_registry.get_primary_m365()
    if primary is not None:
        connector_routes.set_connector(primary)
    connector_routes.set_registry(connector_registry)
    ctx.connector_registry = connector_registry

    # --- U4: conversation module (shares ctx.bus) ---
    # Default to the lightweight null STT/TTS in-process; real transport (Realtime)
    # is selected via STT_PROVIDER/TTS_PROVIDER. orchestrator/memory stay URL-based
    # here; in-process seams are flipped in later units.
    os.environ.setdefault("STT_PROVIDER", "null")
    os.environ.setdefault("TTS_PROVIDER", "null")
    from conversation_runtime import routes as conversation_routes
    from conversation_runtime.main import _build_stt, _build_tts
    from conversation_runtime.session_manager import SessionManager

    conversation_routes.init(
        _build_stt(), _build_tts(), ctx.bus, SessionManager(),
        orchestrator_url=os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:8003"),
        memory_url=os.environ.get("MEMORY_SERVICE_URL", "http://memory-service:8005"),
        inproc_client=ctx._inproc_client,  # U9: memory + orchestrator in-process
    )

    # --- U5: orchestrator module (shares ctx.bus) ---
    from orchestrator import routes as orchestrator_routes
    from orchestrator.approval_manager import ApprovalManager
    from orchestrator.context_builder import ContextBuilder
    from orchestrator.fallback_agent import FallbackAgent
    from orchestrator.gateway import GatewayManager
    from orchestrator.intent_router import IntentRouter
    from orchestrator.offline_queue import OfflineQueue
    from orchestrator.persona_manager import PersonaManager
    from orchestrator.pipeline import OrchestratorPipeline
    from orchestrator.presentation import PresentationManager
    from orchestrator.webhook_dispatcher import WebhookDispatcher
    from shared_personas import Persona

    mode = os.environ.get("ACTIVE_PERSONA", "work")
    try:
        persona = Persona(mode)
    except ValueError:
        persona = Persona.WORK

    intent_router = IntentRouter(mode=mode)
    approval_mgr = ApprovalManager(ctx.bus, session_id=session_id)
    context_builder = ContextBuilder()
    persona_mgr = PersonaManager(initial_persona=persona)
    fallback_agent = FallbackAgent(memory_client=ctx._inproc_client)  # U9

    ctx._offline_queue = OfflineQueue(ctx.bus)
    await ctx._offline_queue.open()

    # U8 seam: the pipeline calls the connector module in-process via ASGI.
    ctx.pipeline = OrchestratorPipeline(
        ctx.bus, intent_router, approval_mgr, context_builder, persona_mgr,
        fallback_agent=fallback_agent, offline_queue=ctx._offline_queue,
        connector_client=ctx._inproc_client,
    )

    # U20: outbound dev-agent tool (gated by DEV_AGENT_ENABLED env var).
    if os.environ.get("DEV_AGENT_ENABLED", "false").lower() == "true":
        from orchestrator.dev_agent import DevAgentTool

        ctx.pipeline._dev_agent = DevAgentTool(approval_mgr, ctx.bus)

    # U19e: judgment/anticipation layer — injects minimal personal context per turn.
    from shared_schemas.knowledge import JudgmentLayer
    from shared_schemas.events.perception import PersonRecognized

    _judgment = JudgmentLayer(ctx.knowledge_store)
    ctx.pipeline.set_judgment_layer(_judgment)

    async def _on_person_recognized(event: PersonRecognized) -> None:
        ctx.pipeline.set_active_person(event.person_id if event.known else None)

    ctx.bus.subscribe(PersonRecognized, _on_person_recognized)

    # U27: the presenter drives the robot (speech + synced gesture) over the
    # brain↔robot boundary via RobotClient.
    from aura_brain.robot_client import RobotClient

    presentation_mgr = PresentationManager(
        ctx.bus, session_id=session_id, robot=RobotClient(),
    )

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
    ctx._webhook_dispatcher = WebhookDispatcher(ctx.bus)

    orchestrator_routes.init(
        intent_router, approval_mgr, context_builder, persona_mgr, ctx.pipeline,
        presentation_mgr,
        gateway_mgr=gateway_mgr, webhook_dispatcher=ctx._webhook_dispatcher,
    )

    # --- U18: live perception loop — camera → face embedding → PersonRecognized.
    # Needs encryption (embeddings are biometric data) so it requires the
    # knowledge passphrase; gated by RECOGNITION_ENABLED.
    from aura_brain import recognition_api

    if os.environ.get("RECOGNITION_ENABLED", "false").lower() == "true" and _kpass:
        from aura_brain.perception import PerceptionLoop, build_embedder
        from shared_schemas.knowledge.recognition import EmbeddingMatcher

        _rec_matcher = EmbeddingMatcher(
            crypto.derive_omk(_kpass, _salt),
            path=os.environ.get("RECOGNITION_DB_PATH", "./data/recognition.enc.json"),
        )
        _rec_embedder = build_embedder(os.environ.get("FACE_EMBEDDER", "null"))
        _rec_robot = RobotClient()
        ctx._perception = PerceptionLoop(
            ctx.bus, _rec_matcher, _rec_robot, _rec_embedder,
            knowledge_store=ctx.knowledge_store,
            interval_s=float(os.environ.get("RECOGNITION_INTERVAL_S", "2.0")),
            session_id=session_id,
        )
        ctx._perception.start()
        recognition_api.init(
            _rec_matcher, _rec_embedder, _rec_robot, ctx.knowledge_store,
            loop=ctx._perception,
        )

    # --- U14: heartbeat watches the REAL failure surface — the brain↔robot link
    # and upstream internet — not sibling containers (which no longer exist after
    # the collapse). Gated by env so it doesn't flap during tests.
    if os.environ.get("HEARTBEAT_ENABLED", "false").lower() == "true":
        from orchestrator.heartbeat import HeartbeatMonitor

        robot_url = os.environ.get("ROBOT_RUNTIME_URL", "http://robot-runtime:8001")
        hb_services = {"robot": f"{robot_url.rstrip('/')}/health"}
        upstream = os.environ.get("UPSTREAM_HEALTH_URL")  # e.g. the LLM/API endpoint
        if upstream:
            hb_services["upstream"] = upstream
        ctx._heartbeat = HeartbeatMonitor(ctx.bus, hb_services)
        ctx._heartbeat.start()
        ctx.pipeline.set_heartbeat_monitor(ctx._heartbeat)

    yield

    if ctx._perception is not None:
        await ctx._perception.stop()
    if ctx._heartbeat is not None:
        await ctx._heartbeat.stop()
    if ctx._inproc_client is not None:
        await ctx._inproc_client.aclose()
    if ctx._webhook_dispatcher is not None:
        await ctx._webhook_dispatcher.close()
    if ctx._offline_queue is not None:
        await ctx._offline_queue.close()
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

    from connector_service import routes as connector_routes
    app.include_router(connector_routes.router)  # U3

    from conversation_runtime import routes as conversation_routes
    app.include_router(conversation_routes.router)  # U4

    from orchestrator import routes as orchestrator_routes
    app.include_router(orchestrator_routes.router)  # U5

    from aura_brain import knowledge_api
    app.include_router(knowledge_api.router)  # U19d

    from aura_brain import recognition_api
    app.include_router(recognition_api.router)  # U18

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
