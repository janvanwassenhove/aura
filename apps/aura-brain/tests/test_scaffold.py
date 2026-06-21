"""Phase 1 step-1 scaffold tests: the unified app builds, health works, and the
single shared bus starts/stops cleanly via the app lifespan."""

from __future__ import annotations

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
