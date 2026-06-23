"""Phase 1 step-1 scaffold tests: the unified app builds, health works, and the
single shared bus starts/stops cleanly via the app lifespan."""

from __future__ import annotations

import os

# In-memory DB before any import pulls in memory_service.db.session (which reads
# DATABASE_URL at import time). Mirrors the memory-service unit tests.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from fastapi.testclient import TestClient

from aura_brain.main import create_app, ctx


def test_health_and_lifespan() -> None:
    app = create_app()
    # TestClient as a context manager runs the lifespan (starts/stops the bus).
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["service"] == "aura-brain"
        assert ctx.bus._started is True  # bus started by lifespan
    assert ctx.bus._started is False      # and stopped on shutdown


def test_single_shared_bus_instance() -> None:
    # The whole point of the collapse: one bus for the process.
    from aura_brain.main import BrainContext

    c = BrainContext()
    assert c.broadcaster._bus is c.bus


def test_memory_module_mounted() -> None:
    """U1: the memory router is reachable through the unified brain app and a
    todo round-trips against the in-process store."""
    app = create_app()
    with TestClient(app) as client:
        assert client.get("/memory/health").status_code == 200
        created = client.post("/memory/todos", json={"text": "buy milk"})
        assert created.status_code in (200, 201)
        listed = client.get("/memory/todos")
        assert listed.status_code == 200
        assert any(t["text"] == "buy milk" for t in listed.json())
        assert ctx.memory_store is not None  # singleton wired in lifespan


def test_identity_module_mounted() -> None:
    """U2: identity routes (refactored to an APIRouter) are reachable via brain."""
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/identity/persona")
        assert resp.status_code == 200
        body = resp.json()
        assert "persona" in body
        assert "authenticated_providers" in body


def test_connector_module_mounted() -> None:
    """U3: connector routes are reachable via brain and the registry is wired."""
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/connector/health")
        assert resp.status_code == 200
        assert ctx.connector_registry is not None


def test_conversation_module_mounted() -> None:
    """U4: conversation routes mount with the null providers; a text turn
    round-trips (echo fallback, orchestrator unreachable)."""
    app = create_app()
    with TestClient(app) as client:
        created = client.post("/conversation/sessions")
        assert created.status_code == 200
        turn = client.post("/conversation/turn", json={"text": "Hello AURA", "session_id": "s1"})
        assert turn.status_code == 200
        assert "Hello AURA" in turn.json()["reply"]


def test_orchestrator_module_mounted() -> None:
    """U5: orchestrator routes mount; config endpoint + an echo /orchestrate work
    through the unified app, and the pipeline singleton is wired."""
    app = create_app()
    with TestClient(app) as client:
        cfg = client.get("/orchestrator/config/llm")
        assert cfg.status_code == 200
        assert "provider" in cfg.json()
        out = client.post("/orchestrator/turn", json={"text": "hi there", "session_id": "s1"})
        assert out.status_code == 200
        assert "reply" in out.json()
        assert ctx.pipeline is not None
