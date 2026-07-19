"""U36h: assistant name + reply language preferences."""

from __future__ import annotations

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aura_brain import setup_api


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # The setup API applies prefs with os.environ.update() (setup_api.py) — e.g.
    # POSTing voice_engine=realtime sets VOICE_ENGINE globally. monkeypatch only
    # tracks keys it set, so snapshot/restore the whole env to keep these tests
    # from leaking VOICE_ENGINE/VOICE_MODE/etc. into unrelated tests (surfaced by
    # pytest-randomly ordering: note_spoken/streaming tests read VOICE_ENGINE).
    _snapshot = dict(os.environ)
    monkeypatch.setenv("AURA_ENV_FILE", str(tmp_path / ".env"))
    monkeypatch.delenv("ASSISTANT_NAME", raising=False)
    monkeypatch.delenv("ASSISTANT_LANGUAGE", raising=False)
    app = FastAPI()
    app.include_router(setup_api.router)
    try:
        yield TestClient(app), tmp_path
    finally:
        os.environ.clear()
        os.environ.update(_snapshot)


def test_defaults(client) -> None:
    c, _ = client
    body = c.get("/setup/prefs").json()
    assert body["assistant_name"] == "AURA"
    assert body["language"] == "auto"
    assert body["voice_mode"] == "off"


def test_set_name_and_language_persists(client) -> None:
    c, tmp_path = client
    resp = c.post("/setup/prefs", json={"assistant_name": "Richie", "language": "nl"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["assistant_name"] == "Richie"
    assert body["language"] == "nl"
    assert body["persisted"] is True
    env = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "ASSISTANT_NAME=Richie" in env
    assert "ASSISTANT_LANGUAGE=nl" in env
    # Reflected on the next GET.
    assert c.get("/setup/prefs").json()["assistant_name"] == "Richie"


def test_rejects_bad_language(client) -> None:
    c, _ = client
    # 'de' is now valid (U130); a genuinely unknown code is still rejected.
    assert c.post("/setup/prefs", json={"language": "de"}).status_code == 200
    assert c.post("/setup/prefs", json={"language": "xx"}).status_code == 422


def test_voice_engine_toggle(client) -> None:
    """U132: the conversation engine is switchable from prefs (Settings UI)."""
    c, _ = client
    assert c.get("/setup/prefs").json()["voice_engine"] == "pipeline"
    r = c.post("/setup/prefs", json={"voice_engine": "realtime"})
    assert r.status_code == 200 and r.json()["voice_engine"] == "realtime"
    assert c.post("/setup/prefs", json={"voice_engine": "bogus"}).status_code == 422


def test_rejects_bad_name(client) -> None:
    c, _ = client
    assert c.post("/setup/prefs", json={"assistant_name": "a/b<script>"}).status_code == 422
    assert c.post("/setup/prefs", json={"assistant_name": ""}).status_code == 422


def test_identity_prefix_reflects_env(monkeypatch) -> None:
    from orchestrator.pipeline import _identity_prefix

    monkeypatch.setenv("ASSISTANT_NAME", "Richie")
    monkeypatch.setenv("ASSISTANT_LANGUAGE", "fr")
    prefix = _identity_prefix()
    assert "Richie" in prefix
    assert "French" in prefix

    monkeypatch.setenv("ASSISTANT_LANGUAGE", "auto")
    assert "language the user is using" in _identity_prefix()
