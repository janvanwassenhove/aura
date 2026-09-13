"""U339: pairing a second laptop with the robot, without editing a file.

Reported from a fresh install on another laptop: every call to the robot comes
back 401, because the robot has a shared secret (U220) and that machine does
not. The diagnosis even says which value to set — and there was nowhere to set
it. `ROBOT_SHARED_SECRET` is read in two places and written by nothing: no
endpoint, no field, no wizard step. The only way to pair a second machine was
to find `%APPDATA%\\aura-desktop\\.env` and type it in by hand, which is the
same "advice with nowhere to act on it" U199 called worse than saying nothing.

It is a credential, so it follows the rule the API keys already follow: stored,
never logged, never echoed back. What the console may know is whether one is
set, which is all it needs to say "paired".
"""

from __future__ import annotations

import os

os.environ.setdefault("LLM_PROVIDER", "echo")

import httpx
import pytest
from aura_brain import setup_api
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AURA_ENV_FILE", str(tmp_path / ".env"))
    monkeypatch.delenv("ROBOT_SHARED_SECRET", raising=False)
    app = FastAPI()
    app.include_router(setup_api.router)   # the router carries its own /setup
    return TestClient(app), tmp_path / ".env"


def test_the_secret_can_be_set_from_the_app(client) -> None:
    c, env_file = client
    resp = c.post("/setup/config", json={"robot_shared_secret": "pair-me-42"})
    assert resp.status_code == 200, resp.text
    assert os.environ["ROBOT_SHARED_SECRET"] == "pair-me-42"
    assert "ROBOT_SHARED_SECRET=pair-me-42" in env_file.read_text(encoding="utf-8")


def test_it_is_never_echoed_back(client) -> None:
    """A credential that comes back out of an endpoint is a credential in a log,
    a screenshot and a bug report."""
    c, _ = client
    body = c.post("/setup/config", json={"robot_shared_secret": "pair-me-42"}).json()
    assert "pair-me-42" not in str(body)
    status = c.get("/setup/status").json()
    assert "pair-me-42" not in str(status)


def test_the_console_can_see_that_one_is_set(client) -> None:
    """Enough to say "paired" and no more."""
    c, _ = client
    assert c.get("/setup/status").json().get("robot_secret_set") is False
    c.post("/setup/config", json={"robot_shared_secret": "pair-me-42"})
    assert c.get("/setup/status").json().get("robot_secret_set") is True


def test_clearing_it_is_possible_for_a_robot_without_one(client) -> None:
    """U220 made the secret opt-in: a robot that has none must still be
    reachable, so a machine must be able to drop the value it holds."""
    c, _ = client
    c.post("/setup/config", json={"robot_shared_secret": "pair-me-42"})
    resp = c.post("/setup/config", json={"robot_shared_secret": "", "clear_robot_secret": True})
    assert resp.status_code == 200, resp.text
    assert os.environ.get("ROBOT_SHARED_SECRET", "") == ""
    assert c.get("/setup/status").json().get("robot_secret_set") is False


# ── the diagnosis that sends you to that field (U339) ──────────────────────

def test_a_rejected_request_is_named_as_a_pairing_problem(monkeypatch) -> None:
    """The fourth cause, missing since U198: he answers perfectly well and
    refuses us. That is not "unreachable (HTTPStatusError)" — it is one
    specific, fixable thing, and the words have to say which."""
    from aura_brain import robot_api

    monkeypatch.setattr(
        robot_api, "_robot",
        type("R", (), {"_base_url": "http://192.168.0.178:8001"})())

    said = robot_api._diagnose(httpx.HTTPStatusError(
        "Client error '401 Unauthorized'",
        request=httpx.Request("GET", "http://192.168.0.178:8001/robot/status"),
        response=httpx.Response(401)))

    assert "192.168.0.178:8001" in said
    assert "401" in said
    assert "pairing key" in said.lower()
    # and where to act on it — U199: advice with nowhere to act is worse than
    # saying nothing.
    assert "connection" in said.lower()


def test_a_different_refusal_is_not_called_a_pairing_problem(monkeypatch) -> None:
    """403 is the robot saying no for its own reasons; 500 is the robot broken.
    Neither is fixed by typing a key, and saying so would send the owner to the
    wrong place."""
    from aura_brain import robot_api

    monkeypatch.setattr(
        robot_api, "_robot",
        type("R", (), {"_base_url": "http://192.168.0.178:8001"})())

    for code in (403, 500):
        said = robot_api._diagnose(httpx.HTTPStatusError(
            f"error {code}",
            request=httpx.Request("GET", "http://192.168.0.178:8001/robot/status"),
            response=httpx.Response(code)))
        assert "pairing key" not in said.lower(), code
        assert str(code) in said, code
