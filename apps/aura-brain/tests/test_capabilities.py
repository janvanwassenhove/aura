"""U40: capabilities center — toggle grants, persist, live-apply hooks."""

from __future__ import annotations

import pytest
from aura_brain import capabilities_api
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AURA_ENV_FILE", str(tmp_path / ".env"))
    for _key, (env_var, _d, _l, _de, _live) in capabilities_api._CAPS.items():
        monkeypatch.delenv(env_var, raising=False)
    monkeypatch.setenv("ALLOWED_APPS", "vscode=code;spotify=spotify")
    capabilities_api._live_hooks.clear()
    app = FastAPI()
    app.include_router(capabilities_api.router)
    return TestClient(app), tmp_path


def test_list_reports_defaults_and_apps(client) -> None:
    c, _ = client
    body = c.get("/capabilities").json()
    keys = {cap["key"] for cap in body["capabilities"]}
    assert {"dev_agent", "app_launch", "follow_me", "recognition"} <= keys
    assert set(body["allowed_apps"]) == {"vscode", "spotify"}


def test_toggle_persists_and_fires_live_hook(client, monkeypatch) -> None:
    c, tmp_path = client
    fired = {}
    capabilities_api.set_live_hook("dev_agent", lambda on: fired.update(on=on))

    resp = c.post("/capabilities/dev_agent", json={"enabled": False})
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is False
    assert body["applied_live"] is True
    assert body["restart_required"] is False
    assert fired == {"on": False}
    # Persisted + reflected on the next GET.
    env = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "DEV_AGENT_ENABLED=false" in env
    caps = {c2["key"]: c2 for c2 in c.get("/capabilities").json()["capabilities"]}
    assert caps["dev_agent"]["enabled"] is False


def test_restart_only_capability_flags_restart(client) -> None:
    c, _ = client
    body = c.post("/capabilities/recognition", json={"enabled": False}).json()
    assert body["restart_required"] is True
    assert body["applied_live"] is False


def test_unknown_capability_404s(client) -> None:
    c, _ = client
    assert c.post("/capabilities/teleport", json={"enabled": True}).status_code == 404
