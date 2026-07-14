"""U36: /robot proxy — console reaches the robot through the brain."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aura_brain import robot_api


class FakeRobotClient:
    def __init__(self, *, up: bool = True) -> None:
        self.up = up
        self.motions: list = []

    def _check(self) -> None:
        if not self.up:
            raise httpx.ConnectError("robot down")

    async def status(self) -> dict:
        self._check()
        return {"mode": "online", "connected": True, "adapter_name": "reachy"}

    async def camera_frame(self) -> bytes:
        self._check()
        return b"\x89PNG-fake"

    async def execute_motion(self, command) -> bool:
        self._check()
        self.motions.append(command)
        return True


@pytest.fixture()
def client_and_robot():
    robot = FakeRobotClient()
    robot_api.init(robot)
    app = FastAPI()
    app.include_router(robot_api.router)
    yield TestClient(app), robot
    robot_api.init(None)


def test_status_proxies_robot_state(client_and_robot) -> None:
    client, _ = client_and_robot
    body = client.get("/robot/status").json()
    assert body["adapter_name"] == "reachy"


def test_camera_frame_returns_png_bytes(client_and_robot) -> None:
    client, _ = client_and_robot
    resp = client.get("/robot/camera/frame")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content.startswith(b"\x89PNG")


def test_motion_forwards_command(client_and_robot) -> None:
    client, robot = client_and_robot
    resp = client.post("/robot/motion", json={"motion_id": "wave", "amplitude": 0.6})
    assert resp.status_code == 200 and resp.json()["ok"] is True
    assert robot.motions[0].motion_id == "wave"


def test_unreachable_robot_returns_503() -> None:
    robot_api.init(FakeRobotClient(up=False))
    app = FastAPI()
    app.include_router(robot_api.router)
    client = TestClient(app)
    try:
        assert client.get("/robot/status").status_code == 503
        assert client.get("/robot/camera/frame").status_code == 503
        assert client.post("/robot/motion", json={"motion_id": "nod"}).status_code == 503
    finally:
        robot_api.init(None)
