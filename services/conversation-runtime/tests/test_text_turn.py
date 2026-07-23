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


def test_text_turn_says_it_failed_instead_of_echoing(client: TestClient) -> None:
    """U202: with the orchestrator unreachable, SAY so.

    This used to assert the opposite — that the reply contained the question —
    because the fallback echoed it back. That looked like a working assistant
    with a parroting habit, and it hid a real misconfiguration for as long as
    nobody read the log. The turn still succeeds (the session stays usable),
    but the reply admits the failure and never repeats the prompt.
    """
    resp = client.post(
        "/conversation/turn",
        json={"text": "Hello AURA", "session_id": "test-session"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "Hello AURA" not in body["reply"]
    assert "can't answer" in body["reply"]
    assert body["session_id"] == "test-session"


def test_end_session(client: TestClient) -> None:
    # Create a session first
    create_resp = client.post("/conversation/sessions")
    session_id = create_resp.json()["session_id"]

    resp = client.delete(f"/conversation/sessions/{session_id}")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


# ------------------------------------------------------------------
# U202: a failing turn must say so, never imitate a working one
# ------------------------------------------------------------------

def test_failure_messages_name_the_fix() -> None:
    """The old fallback echoed the question and logged a warning nobody reads.

    A misconfigured model therefore looked like a parrot: every question came
    back verbatim, with the real cause ("not a chat model") sitting in a log
    file. Each failure the owner can actually fix now says what to do.
    """
    from conversation_runtime.routes import _explain_failure

    chat = _explain_failure(RuntimeError(
        "Error code: 404 - {'error': {'message': 'This is not a chat model and "
        "thus not supported in the v1/chat/completions endpoint.'}}"))
    assert "speech-to-speech" in chat and "Settings" in chat

    key = _explain_failure(RuntimeError("Error code: 401 - invalid_api_key"))
    assert "API key" in key

    quota = _explain_failure(RuntimeError("Error code: 429 - rate limit reached"))
    assert "quota" in quota or "rate-limit" in quota

    # Anything unrecognised still admits failure rather than faking an answer.
    other = _explain_failure(RuntimeError("something odd"))
    assert "can't answer" in other


def test_a_failed_turn_never_returns_the_question() -> None:
    """The specific deception: the reply must not be the prompt back."""
    from conversation_runtime.routes import _explain_failure

    question = "kan je nummer nofx afspelen in spotify"
    for exc in (RuntimeError("not a chat model"), RuntimeError("boom")):
        assert question not in _explain_failure(exc)
