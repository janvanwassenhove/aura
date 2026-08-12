"""U238: a newer brain must still work against an older robot.

The laptop updates itself; the Pi is flashed by hand. A brain that is newer
than the runtime it talks to is the NORMAL state of this system, not an edge
case — so a call the robot has never heard of must degrade, not abort.

U237 added `POST /robot/sleep` on the runtime and called it first from the
brain's sleep endpoint, inside the same try as the pose. Against a robot that
predates it, the 404 raised on the first line and the rest — stop tracking,
lie down — never ran. The endpoint still returned `{"asleep": true}`, so the
app reported success while the robot did precisely nothing.
"""

from __future__ import annotations

import httpx
import pytest
from aura_brain import robot_api
from fastapi import FastAPI
from fastapi.testclient import TestClient


class OlderRobot:
    """A runtime from before U237: everything works except the sleep route."""

    def __init__(self) -> None:
        self.motions: list = []
        self.tracking: list[bool] = []

    async def set_asleep(self, asleep: bool) -> bool:
        request = httpx.Request("POST", "http://robot/robot/sleep")
        response = httpx.Response(404, request=request)
        raise httpx.HTTPStatusError("Not Found", request=request, response=response)

    async def set_tracking(self, enabled: bool) -> dict:
        self.tracking.append(enabled)
        return {"tracking": enabled}

    async def execute_motion(self, command) -> bool:
        self.motions.append(command.motion_id)
        return True


class CurrentRobot(OlderRobot):
    """A runtime that knows about sleep."""

    def __init__(self) -> None:
        super().__init__()
        self.asleep: list[bool] = []

    async def set_asleep(self, asleep: bool) -> bool:
        self.asleep.append(asleep)
        return True


def _client(robot):
    robot_api.init(robot)
    app = FastAPI()
    app.include_router(robot_api.router)
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset():
    yield
    robot_api.init(None)


def test_sleep_still_poses_the_robot_when_the_route_is_missing() -> None:
    robot = OlderRobot()
    client = _client(robot)

    body = client.post("/robot/sleep").json()

    assert robot.motions == ["sleep"], "the robot must still be told to lie down"
    assert robot.tracking == [False], "and head tracking must still stop"
    assert body["asleep"] is True
    assert body["stays_down"] is False, (
        "and the app must say this is the lesser sleep — the robot will get "
        "back up by itself until the Pi is redeployed"
    )


def test_sleep_reports_the_full_thing_against_a_current_runtime() -> None:
    robot = CurrentRobot()
    client = _client(robot)

    body = client.post("/robot/sleep").json()

    assert robot.asleep == [True]
    assert robot.motions == ["sleep"]
    assert body["stays_down"] is True


def test_wake_still_works_when_the_route_is_missing() -> None:
    robot = OlderRobot()
    client = _client(robot)

    body = client.post("/robot/wake").json()

    assert robot.motions == ["wake_up"], "waking must not depend on the new route"
    assert robot.tracking == [True]
    assert body["asleep"] is False
