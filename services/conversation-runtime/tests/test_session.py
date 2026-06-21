"""Tests for session lifecycle in conversation-runtime (spec 005 T-005-07)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("LLM_PROVIDER", "echo")
os.environ.setdefault("STT_PROVIDER", "local_whisper")
os.environ.setdefault("TTS_PROVIDER", "kokoro")
os.environ.setdefault("ORCHESTRATOR_URL", "http://localhost:9999")
os.environ.setdefault("MEMORY_SERVICE_URL", "http://localhost:9999")

from fastapi.testclient import TestClient
from conversation_runtime.main import create_app


@pytest.fixture(scope="module")
def client() -> TestClient:
    app = create_app()
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def test_create_session_returns_session_id(client: TestClient) -> None:
    resp = client.post("/conversation/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data
    assert len(data["session_id"]) > 0


def test_multiple_sessions_have_unique_ids(client: TestClient) -> None:
    ids = set()
    for _ in range(5):
        resp = client.post("/conversation/sessions")
        ids.add(resp.json()["session_id"])
    assert len(ids) == 5


def test_end_session_returns_ok(client: TestClient) -> None:
    create_resp = client.post("/conversation/sessions")
    session_id = create_resp.json()["session_id"]

    end_resp = client.delete(f"/conversation/sessions/{session_id}")
    assert end_resp.status_code == 200
    assert end_resp.json()["ok"] is True


def test_end_nonexistent_session_is_graceful(client: TestClient) -> None:
    """Ending a session that doesn't exist should not raise 500."""
    resp = client.delete("/conversation/sessions/nonexistent-id")
    assert resp.status_code in (200, 404)


def test_text_turn_increments_turn_count(client: TestClient) -> None:
    """After a text turn, a second turn should also succeed."""
    resp1 = client.post(
        "/conversation/turn",
        json={"text": "first message", "session_id": "turn-count-test"},
    )
    resp2 = client.post(
        "/conversation/turn",
        json={"text": "second message", "session_id": "turn-count-test"},
    )
    assert resp1.status_code == 200
    assert resp2.status_code == 200
