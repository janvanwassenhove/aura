"""U393: the brain's half of wandering — when it is on, and what he may say.

Agreed as (translated): a switch next to follow-me, "but review that this
cannot conflict with other settings and modes"; and when someone speaks to him
while he wanders, "he looks at them, but only speaks if the sound mode is on".

The robot decides how to wander and refuses to while asleep. The brain decides
WHETHER: the owner's switch, paused while a presentation runs (until U394 lets a
scenario decide), and re-asserted whenever the robot comes back, because the
robot does not remember it across a restart.
"""

from __future__ import annotations

import httpx
import pytest
from aura_brain import wander


class _Robot:
    def __init__(self, *, status: int = 200) -> None:
        self.calls: list[bool] = []
        self.status = status

    async def set_wander(self, enabled: bool) -> dict:
        self.calls.append(enabled)
        if self.status != 200:
            req = httpx.Request("POST", "http://robot/robot/wander")
            raise httpx.HTTPStatusError(
                "nope", request=req, response=httpx.Response(self.status, request=req))
        return {"enabled": enabled, "active": enabled, "sound_direction": True}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("WANDER_ENABLED", raising=False)
    monkeypatch.delenv("WANDER_SOUND", raising=False)
    from aura_brain import presentation_api
    monkeypatch.setattr(presentation_api, "is_active", lambda: False)
    wander.forget()
    yield
    wander.forget()


def test_off_unless_the_owner_turns_it_on(monkeypatch) -> None:
    assert wander.effective() is False
    monkeypatch.setenv("WANDER_ENABLED", "true")
    assert wander.effective() is True


def test_a_presentation_pauses_it(monkeypatch) -> None:
    from aura_brain import presentation_api

    monkeypatch.setenv("WANDER_ENABLED", "true")
    monkeypatch.setattr(presentation_api, "is_active", lambda: True)
    assert wander.effective() is False
    assert wander.status()["paused"] == "presentation"


async def test_apply_tells_the_robot_what_is_in_force(monkeypatch) -> None:
    robot = _Robot()
    monkeypatch.setenv("WANDER_ENABLED", "true")
    await wander.apply(robot)
    monkeypatch.setenv("WANDER_ENABLED", "false")
    await wander.apply(robot)
    assert robot.calls == [True, False]
    assert wander.status()["note"] == ""


async def test_a_robot_too_old_to_wander_is_said_so_not_failed(monkeypatch) -> None:
    """The Pi is older than the app: a 404 from the robot is a degradation the
    owner can act on, never an error that breaks the switch."""
    monkeypatch.setenv("WANDER_ENABLED", "true")
    await wander.apply(_Robot(status=404))
    assert "update" in wander.status()["note"]


async def test_an_unreachable_robot_is_said_so(monkeypatch) -> None:
    class _Gone:
        async def set_wander(self, enabled):
            raise httpx.ConnectError("no route")

    monkeypatch.setenv("WANDER_ENABLED", "true")
    await wander.apply(_Gone())
    assert "reach" in wander.status()["note"]


def test_quiet_unless_his_wander_sound_allows_it(monkeypatch) -> None:
    monkeypatch.setenv("WANDER_ENABLED", "true")
    assert wander.sound() == "silent"
    assert wander.silences_speech() is True
    monkeypatch.setenv("WANDER_SOUND", "talk")
    assert wander.silences_speech() is False


def test_a_sound_setting_that_is_not_one_is_silent(monkeypatch) -> None:
    """A typo must never be the reason he starts talking."""
    monkeypatch.setenv("WANDER_ENABLED", "true")
    monkeypatch.setenv("WANDER_SOUND", "lound")
    assert wander.sound() == "silent"


def test_not_wandering_never_silences_him(monkeypatch) -> None:
    assert wander.silences_speech() is False


def test_the_switch_sits_next_to_follow_me() -> None:
    from aura_brain.capabilities_api import _CAPS

    keys = list(_CAPS)
    assert "wander" in keys
    assert keys.index("wander") == keys.index("body_follow") + 1
    env, default, *_ = _CAPS["wander"]
    assert (env, default) == ("WANDER_ENABLED", "false")


def _client(monkeypatch, tmp_path):
    from aura_brain import setup_api
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    monkeypatch.setenv("AURA_ENV_FILE", str(tmp_path / "dev.env"))
    (tmp_path / "dev.env").write_text("", encoding="utf-8")
    app = FastAPI()
    app.include_router(setup_api.router)
    return TestClient(app)


def test_the_wander_sound_is_a_setting(monkeypatch, tmp_path) -> None:
    c = _client(monkeypatch, tmp_path)
    assert c.post("/setup/prefs", json={"wander_sound": "talk"}).status_code == 200
    assert c.get("/setup/prefs").json()["wander_sound"] == "talk"
    assert c.post("/setup/prefs", json={"wander_sound": "shout"}).status_code == 422
