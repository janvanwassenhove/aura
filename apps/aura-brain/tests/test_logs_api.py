"""U56: in-app log viewer — ring buffer over HTTP, no files, no telemetry."""

from __future__ import annotations

import logging

from aura_brain import logs_api
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client() -> TestClient:
    logs_api.install()
    # The app configures INFO via basicConfig; mirror that for the test logger.
    logging.getLogger("aura.test").setLevel(logging.INFO)
    app = FastAPI()
    app.include_router(logs_api.router)
    return TestClient(app)


def test_recent_returns_logged_records() -> None:
    c = _client()
    logging.getLogger("aura.test").info("hello from the log viewer")
    data = c.get("/logs/recent").json()
    messages = [r["message"] for r in data["records"]]
    assert "hello from the log viewer" in messages
    rec = next(r for r in data["records"] if r["message"] == "hello from the log viewer")
    assert rec["level"] == "INFO"
    assert rec["logger"] == "aura.test"


def test_level_filter_and_limit() -> None:
    c = _client()
    logging.getLogger("aura.test").warning("only warning A")
    logging.getLogger("aura.test").info("plain info B")
    warnings = c.get("/logs/recent?level=warning").json()["records"]
    assert all(r["level"] == "WARNING" for r in warnings)
    assert any("only warning A" in r["message"] for r in warnings)
    limited = c.get("/logs/recent?limit=1").json()["records"]
    assert len(limited) == 1


def test_install_is_idempotent() -> None:
    logs_api.install()
    logs_api.install()
    root = logging.getLogger()
    ring_handlers = [h for h in root.handlers if isinstance(h, logs_api._RingBufferHandler)]
    assert len(ring_handlers) == 1
