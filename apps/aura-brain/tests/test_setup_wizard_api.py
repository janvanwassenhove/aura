"""U34/U53: in-app onboarding API — status, config (write-only secrets), test-robot."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aura_brain import setup_api


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AURA_ENV_FILE", str(tmp_path / ".env"))
    for var in ("SETUP_DONE", "OPENAI_API_KEY", "ROBOT_RUNTIME_URL", "LLM_PROVIDER"):
        monkeypatch.delenv(var, raising=False)
    app = FastAPI()
    app.include_router(setup_api.router)
    return TestClient(app), tmp_path


def test_status_reports_incomplete_setup(client) -> None:
    c, _ = client
    body = c.get("/setup/status").json()
    assert body["setup_done"] is False
    assert body["openai_key_set"] is False
    assert "people_count" in body


def test_config_sets_and_persists_without_echoing_secrets(client) -> None:
    c, tmp_path = client
    resp = c.post("/setup/config", json={
        "robot_url": "http://192.168.0.178:8001",
        "openai_api_key": "sk-supersecret",
        "setup_done": True,
    })
    assert resp.status_code == 200
    body = resp.json()
    # Secret value never appears anywhere in the response.
    assert "sk-supersecret" not in resp.text
    assert body["secrets_set"] == ["openai_api_key"]
    assert "ROBOT_RUNTIME_URL" in body["applied"]
    # Persisted to the env file + effective in the process.
    env = (tmp_path / ".env").read_text()
    assert "OPENAI_API_KEY=sk-supersecret" in env
    assert "SETUP_DONE=true" in env
    status = c.get("/setup/status").json()
    assert status["setup_done"] is True
    assert status["openai_key_set"] is True


def test_config_rejects_empty_body(client) -> None:
    c, _ = client
    assert c.post("/setup/config", json={}).status_code == 422


def test_test_robot_reports_unreachable(client) -> None:
    c, _ = client
    body = c.post("/setup/test-robot", json={"url": "http://127.0.0.1:9"}).json()
    assert body["ok"] is False
    assert body["url"] == "http://127.0.0.1:9"


def test_test_robot_requires_a_url(client) -> None:
    c, _ = client
    assert c.post("/setup/test-robot", json={}).status_code == 422
