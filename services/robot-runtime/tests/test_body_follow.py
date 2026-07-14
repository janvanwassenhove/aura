"""U37: POST /robot/body_follow — torso turns with the tracked face."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from robot_runtime import routes
from robot_runtime.adapters.fake import FakeRobotAdapter


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app)


async def test_body_follow_toggles_adapter() -> None:
    adapter = FakeRobotAdapter()
    await adapter.connect()
    routes.adapter = adapter
    try:
        resp = _client().post("/robot/body_follow", json={"enabled": True})
        assert resp.status_code == 200
        assert resp.json() == {"body_follow": True}
        assert adapter._body_follow is True

        resp = _client().post("/robot/body_follow", json={"enabled": False})
        assert resp.json() == {"body_follow": False}
        assert adapter._body_follow is False
    finally:
        routes.adapter = None


async def test_body_follow_501_without_capability() -> None:
    class NoBodyFollow(FakeRobotAdapter):
        set_body_follow = None  # type: ignore[assignment]

    adapter = NoBodyFollow()
    await adapter.connect()
    routes.adapter = adapter
    try:
        resp = _client().post("/robot/body_follow", json={"enabled": True})
        assert resp.status_code == 501
    finally:
        routes.adapter = None


async def test_tracking_route_works_on_fake_adapter() -> None:
    """U36g regression: the fake adapter now implements set_tracking too."""
    adapter = FakeRobotAdapter()
    await adapter.connect()
    routes.adapter = adapter
    try:
        resp = _client().post("/robot/tracking", json={"enabled": True})
        assert resp.status_code == 200
        assert adapter._tracking is True
    finally:
        routes.adapter = None
