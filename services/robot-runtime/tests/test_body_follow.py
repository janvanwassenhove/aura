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


# --- U395: an emotion, asked for by the brain ---------------------------------

async def test_the_emotion_route_plays_one() -> None:
    adapter = FakeRobotAdapter()
    await adapter.connect()
    routes.adapter = adapter
    try:
        resp = _client().post("/robot/emotion", json={"name": "laughing2"})
        assert resp.status_code == 200
        assert resp.json()["played"] == "laughing2"
        assert adapter.emotions == ["laughing2"]
    finally:
        routes.adapter = None


async def test_the_emotion_route_says_why_not() -> None:
    class Picky(FakeRobotAdapter):
        async def play_emotion(self, name: str) -> dict:
            if name == "asleep":
                return {"played": None, "reason": "asleep"}
            if name == "bad/name":
                raise ValueError("not an emotion name")
            raise LookupError("no such emotion")

    adapter = Picky()
    await adapter.connect()
    routes.adapter = adapter
    try:
        assert _client().post("/robot/emotion", json={"name": "asleep"}).status_code == 409
        assert _client().post("/robot/emotion", json={"name": "bad/name"}).status_code == 422
        assert _client().post("/robot/emotion", json={"name": "sneezing9"}).status_code == 404
    finally:
        routes.adapter = None


async def test_the_emotion_route_501_on_an_adapter_without_them() -> None:
    class Mute(FakeRobotAdapter):
        play_emotion = None  # type: ignore[assignment]

    adapter = Mute()
    await adapter.connect()
    routes.adapter = adapter
    try:
        assert _client().post("/robot/emotion", json={"name": "laughing2"}).status_code == 501
    finally:
        routes.adapter = None


async def test_wandering_is_told_whether_emotions_are_allowed() -> None:
    adapter = FakeRobotAdapter()
    await adapter.connect()
    routes.adapter = adapter
    try:
        body = _client().post("/robot/wander", json={"enabled": True, "emotions": True}).json()
        assert body["enabled"] is True and body["emotions"] is True
        body = _client().post("/robot/wander", json={"enabled": True}).json()
        assert body["emotions"] is False, "not saying is not allowing"
    finally:
        routes.adapter = None
