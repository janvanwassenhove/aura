"""U18: GET /robot/camera/frame serves one PNG frame from the adapter."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from robot_runtime import routes
from robot_runtime.adapters.fake import FakeRobotAdapter


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app)


async def test_camera_frame_returns_png() -> None:
    adapter = FakeRobotAdapter()
    await adapter.connect()
    routes.adapter = adapter
    try:
        resp = _client().get("/robot/camera/frame")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        assert resp.content.startswith(b"\x89PNG")
    finally:
        routes.adapter = None


async def test_camera_unavailable_returns_503() -> None:
    class NoCamera(FakeRobotAdapter):
        async def get_camera_frame(self) -> bytes:
            raise RuntimeError("camera unavailable: media backend disabled")

    adapter = NoCamera()
    await adapter.connect()
    routes.adapter = adapter
    try:
        resp = _client().get("/robot/camera/frame")
        assert resp.status_code == 503
        assert "camera" in resp.json()["error"]
    finally:
        routes.adapter = None
