"""U371 (audit T6): the robot being behind the laptop is visible in the app.

`deploy_robot.py --check` compares the Pi's commit with the laptop's, and the
Pi's `/health` has reported its `build` since U240. Nothing in the brain or the
console ever showed it. So every "the fix did not work" that was really "the
fix is not on the Pi yet" — the Pi drifted 74 commits behind once (U240), one
behind today — was diagnosed by hand, by someone remembering the script.

`/robot/status` now carries a `build` block: the robot's commit, the laptop's,
and whether the robot is behind. The laptop's commit comes from the checkout
when there is one, from `AURA_BUILD_COMMIT` when the desktop app stamped it
at build time, and is otherwise **absent** — in which case `behind` is None
and the console says it cannot compare. A guess would be worse than the
absence (constitution XI).
"""

from __future__ import annotations

import os

os.environ.setdefault("LLM_PROVIDER", "echo")

import pytest
from aura_brain import robot_api
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROBOT = "f145485aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
LAPTOP = "8f179ce0000000000000000000000000000000000"


class _Robot:
    def __init__(self, commit: str | None = ROBOT) -> None:
        self._build = {"commit": commit, "commit_short": (commit or "")[:7]} if commit else {}

    async def status(self) -> dict:
        return {"connected": True, "mode": "online"}

    async def build(self) -> dict:
        return dict(self._build)


@pytest.fixture()
def client(monkeypatch):
    app = FastAPI()
    app.include_router(robot_api.router)
    monkeypatch.setattr(robot_api, "_robot", _Robot())
    monkeypatch.setattr(robot_api, "_build_cache", None, raising=False)
    return TestClient(app)


def test_status_says_which_build_the_robot_runs_and_whether_it_is_behind(client, monkeypatch) -> None:
    monkeypatch.setattr(robot_api, "laptop_commit", lambda: LAPTOP)
    body = client.get("/robot/status").json()
    assert body["build"]["robot"] == ROBOT[:7]
    assert body["build"]["laptop"] == LAPTOP[:7]
    assert body["build"]["behind"] is True


def test_the_same_commit_is_not_behind(client, monkeypatch) -> None:
    monkeypatch.setattr(robot_api, "laptop_commit", lambda: ROBOT)
    assert client.get("/robot/status").json()["build"]["behind"] is False


def test_an_unknown_laptop_commit_is_an_absence_not_a_guess(client, monkeypatch) -> None:
    """A packaged app with no stamp cannot compare. It must say so, not say
    'in step' because two unknowns happen to be equal."""
    monkeypatch.setattr(robot_api, "laptop_commit", lambda: None)
    build = client.get("/robot/status").json()["build"]
    assert build["laptop"] is None and build["behind"] is None
    assert build["robot"] == ROBOT[:7]


def test_a_robot_too_old_to_report_a_build_is_an_absence_too(client, monkeypatch) -> None:
    monkeypatch.setattr(robot_api, "_robot", _Robot(commit=None))
    monkeypatch.setattr(robot_api, "laptop_commit", lambda: LAPTOP)
    build = client.get("/robot/status").json()["build"]
    assert build["robot"] is None and build["behind"] is None


def test_the_build_is_asked_once_not_on_every_status_poll(client, monkeypatch) -> None:
    """The console polls status every few seconds (U365). A commit does not
    change while the runtime runs; asking /health each time is noise on the
    Pi for nothing."""
    calls = {"n": 0}
    robot = _Robot()
    orig = robot.build

    async def counted():
        calls["n"] += 1
        return await orig()

    robot.build = counted  # type: ignore[assignment]
    monkeypatch.setattr(robot_api, "_robot", robot)
    monkeypatch.setattr(robot_api, "laptop_commit", lambda: LAPTOP)
    for _ in range(4):
        client.get("/robot/status")
    assert calls["n"] == 1


def test_the_laptop_commit_comes_from_the_stamp_when_there_is_no_checkout(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AURA_BUILD_COMMIT", LAPTOP)
    monkeypatch.setattr(robot_api, "_git_head", lambda: None)
    assert robot_api.laptop_commit() == LAPTOP


def test_the_checkout_wins_over_a_stale_stamp(monkeypatch) -> None:
    monkeypatch.setenv("AURA_BUILD_COMMIT", "0000000")
    monkeypatch.setattr(robot_api, "_git_head", lambda: LAPTOP)
    assert robot_api.laptop_commit() == LAPTOP
