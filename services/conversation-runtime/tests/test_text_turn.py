"""Tests for conversation-runtime text turn endpoint."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("LLM_PROVIDER", "echo")
os.environ.setdefault("STT_PROVIDER", "local_whisper")
os.environ.setdefault("TTS_PROVIDER", "kokoro")
os.environ.setdefault("ORCHESTRATOR_URL", "http://localhost:9999")  # unreachable → echo fallback
os.environ.setdefault("MEMORY_SERVICE_URL", "http://localhost:9999")  # unreachable → skip


from conversation_runtime.main import create_app


@pytest.fixture(scope="module")
def client() -> TestClient:
    app = create_app()
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def test_health(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_create_session(client: TestClient) -> None:
    resp = client.post("/conversation/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data
    assert len(data["session_id"]) > 0


def test_text_turn_missing_text(client: TestClient) -> None:
    resp = client.post("/conversation/turn", json={"session_id": "s1"})
    assert resp.status_code == 422


def test_text_turn_echo_fallback(client: TestClient) -> None:
    """With orchestrator unreachable, the echo fallback is returned."""
    resp = client.post(
        "/conversation/turn",
        json={"text": "Hello AURA", "session_id": "test-session"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "reply" in body
    assert "Hello AURA" in body["reply"]
    assert body["session_id"] == "test-session"


def test_end_session(client: TestClient) -> None:
    # Create a session first
    create_resp = client.post("/conversation/sessions")
    session_id = create_resp.json()["session_id"]

    resp = client.delete(f"/conversation/sessions/{session_id}")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
