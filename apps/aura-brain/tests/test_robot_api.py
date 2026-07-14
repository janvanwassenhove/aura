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
        self.spoken: list[tuple[str, str | None]] = []

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

    async def speak(self, text: str, audio_b64: str | None = None) -> bool:
        self._check()
        self.spoken.append((text, audio_b64))
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


def test_say_synthesizes_and_speaks(client_and_robot, monkeypatch) -> None:
    from aura_brain import voice

    async def fake_tts(text: str) -> str:
        return "UEND-b64"

    monkeypatch.setattr(voice, "synthesize_b64", fake_tts)
    client, robot = client_and_robot
    resp = client.post("/robot/say", json={"text": "Hallo Jan!"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "voiced": True}
    assert robot.spoken == [("Hallo Jan!", "UEND-b64")]


def test_say_degrades_to_text_only_without_tts(client_and_robot, monkeypatch) -> None:
    from aura_brain import voice

    async def no_tts(text: str) -> None:
        return None

    monkeypatch.setattr(voice, "synthesize_b64", no_tts)
    client, robot = client_and_robot
    resp = client.post("/robot/say", json={"text": "stil"})
    assert resp.json() == {"ok": True, "voiced": False}
    assert robot.spoken == [("stil", None)]


def test_say_requires_text(client_and_robot) -> None:
    client, _ = client_and_robot
    assert client.post("/robot/say", json={}).status_code == 422


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
