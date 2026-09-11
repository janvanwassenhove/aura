"""U36h: assistant name + reply language preferences."""

from __future__ import annotations

import os

import pytest
from aura_brain import setup_api
from fastapi import FastAPI
from fastapi.testclient import TestClient


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


# ------------------------------------------------------------------
# U202: the model roles must not accept a model the role cannot run
# ------------------------------------------------------------------

def test_realtime_model_is_its_own_role(client) -> None:
    """Voice and text need different endpoints, so they need separate settings."""
    c, _ = client
    assert c.get("/setup/prefs").json()["realtime_model"] == ""

    assert c.post("/setup/prefs", json={"realtime_model": "gpt-realtime-2.1"}).status_code == 200
    assert c.get("/setup/prefs").json()["realtime_model"] == "gpt-realtime-2.1"
    assert os.environ["REALTIME_MODEL"] == "gpt-realtime-2.1"


@pytest.mark.parametrize("role", ["chat_model", "agent_model"])
@pytest.mark.parametrize("model", ["gpt-realtime-2.1", "gpt-4o-realtime-preview",
                                   "gpt-4o-audio-preview"])
def test_a_speech_model_is_refused_for_a_text_role(client, role, model) -> None:
    """The exact failure the owner hit.

    U191's settings offered ONLY realtime models for the Conversation role, but
    that role feeds round one of every turn through chat-completions — typed
    messages included. Picking one made OpenAI answer 404 "not a chat model" for
    every single turn, which the old echo fallback then disguised as the
    assistant repeating the question back.
    """
    c, _ = client
    resp = c.post("/setup/prefs", json={role: model})
    assert resp.status_code == 422
    assert "speech-to-speech" in resp.json()["error"]
    # Refused means unchanged — a rejected value must not be half-applied.
    assert os.environ.get(
        {"chat_model": "CHAT_MODEL", "agent_model": "AGENT_MODEL"}[role], "") != model


def test_a_normal_chat_model_still_saves(client) -> None:
    c, _ = client
    assert c.post("/setup/prefs", json={"chat_model": "gpt-4o-mini"}).status_code == 200
    assert os.environ["CHAT_MODEL"] == "gpt-4o-mini"


# ------------------------------------------------------------------
# U321: a model that serves NEITHER endpoint, refused in either role
# ------------------------------------------------------------------

@pytest.mark.parametrize("role", ["chat_model", "agent_model"])
def test_a_live_voice_model_is_refused_for_a_text_role(client, role) -> None:
    """The guard kept its own copy of the classifier — "realtime" or "-audio"
    in the name — and `gpt-live-1` matches neither, so it was accepted as a
    chat model: U202 again, through a different door."""
    c, _ = client
    resp = c.post("/setup/prefs", json={role: "gpt-live-1"})
    assert resp.status_code == 422
    assert "Live API" in resp.json()["error"], "and it says WHY, not just no"


@pytest.mark.parametrize("model", ["gpt-live-1", "gpt-realtime-translate",
                                   "gpt-4o-mini-transcribe"])
def test_the_voice_role_refuses_models_that_cannot_hold_a_conversation(client, model) -> None:
    """Measured on the owner's key: each of these connects or 404s but never
    answers a voice turn. Accepting one would silently drop every realtime turn
    to the pipeline — "natural voice" gone, and nothing on screen saying why."""
    c, _ = client
    resp = c.post("/setup/prefs", json={"realtime_model": model})
    assert resp.status_code == 422
    assert os.environ.get("REALTIME_MODEL", "") != model


@pytest.mark.parametrize("model", ["gpt-realtime-2", "gpt-realtime-2.1-mini", ""])
def test_the_voice_role_still_takes_real_voice_models(client, model) -> None:
    """Empty means "automatic" and must keep working; a future realtime model
    with an unexpected name is not refused — the probe is the ground truth."""
    c, _ = client
    assert c.post("/setup/prefs", json={"realtime_model": model}).status_code == 200
