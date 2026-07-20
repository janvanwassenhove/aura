"""U36b: /robot/speak accepts base64 PCM and plays it via the adapter."""

from __future__ import annotations

import base64

from fastapi import FastAPI
from fastapi.testclient import TestClient

from robot_runtime import routes
from robot_runtime.adapters.fake import FakeRobotAdapter
from robot_runtime.engine.behavior import BehaviorEngine
from shared_events.bus import AsyncEventBus


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app)


async def _setup() -> tuple[FakeRobotAdapter, AsyncEventBus]:
    adapter = FakeRobotAdapter()
    await adapter.connect()
    bus = AsyncEventBus()
    await bus.start()
    routes.adapter = adapter
    routes.engine = BehaviorEngine(adapter, bus, session_id="t")
    return adapter, bus


async def _teardown(bus: AsyncEventBus) -> None:
    routes.adapter = None
    routes.engine = None
    await bus.stop()


async def test_speak_with_audio_plays_pcm() -> None:
    adapter, bus = await _setup()
    try:
        pcm = b"\x00\x01" * 240
        resp = _client().post("/robot/speak", json={
            "text": "Hello Jan!",
            "audio_b64": base64.b64encode(pcm).decode(),
        })
        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "audio": True}
        assert adapter.spoken_texts == ["Hello Jan!"]
        assert adapter.played_audio == [pcm]
    finally:
        await _teardown(bus)


async def test_speak_without_audio_is_text_only() -> None:
    adapter, bus = await _setup()
    try:
        resp = _client().post("/robot/speak", json={"text": "silent hello"})
        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "audio": False}
        assert adapter.played_audio == []
    finally:
        await _teardown(bus)


async def test_speak_rejects_invalid_base64() -> None:
    adapter, bus = await _setup()
    try:
        resp = _client().post("/robot/speak", json={"text": "x", "audio_b64": "%%%not-b64%%%"})
        assert resp.status_code == 422
    finally:
        await _teardown(bus)


async def test_speak_segment_plays_directly() -> None:
    """U153: segment playback bypasses the behaviour engine, plays via adapter."""
    adapter, bus = await _setup()
    try:
        pcm = b"\x01\x02" * 120
        resp = _client().post("/robot/speak/segment", json={
            "audio_b64": base64.b64encode(pcm).decode()})
        assert resp.status_code == 200
        # U155: default path is the gapless appsrc pipeline.
        assert resp.json() == {"ok": True, "path": "appsrc"}
        assert adapter.played_audio == [pcm]
        assert adapter.spoken_texts == []  # no speak() involved
    finally:
        await _teardown(bus)


async def test_aim_clamps_and_pauses_tracking() -> None:
    """U161: joystick aim — values clamp to -1..1 and follow-me is paused so
    the daemon doesn't pull the head straight back to the nearest face."""
    adapter, bus = await _setup()
    try:
        await adapter.set_tracking(True)
        resp = _client().post("/robot/aim", json={"yaw": 3.0, "pitch": -0.5,
                                                  "body_yaw": 0.25})
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["yaw"] == 1.0            # clamped from 3.0
        assert body["pitch"] == -0.5
        assert body["body_yaw"] == 0.25
        assert body["tracking_paused"] is True
    finally:
        await _teardown(bus)


async def test_aim_leaves_torso_alone_when_omitted() -> None:
    adapter, bus = await _setup()
    try:
        body = _client().post("/robot/aim", json={"yaw": 0.2}).json()
        assert body["body_yaw"] is None      # torso untouched
        assert body["pitch"] == 0.0
    finally:
        await _teardown(bus)


async def test_aim_rejects_junk_values() -> None:
    adapter, bus = await _setup()
    try:
        body = _client().post("/robot/aim", json={"yaw": "left", "pitch": None}).json()
        assert body["yaw"] == 0.0 and body["pitch"] == 0.0   # falls back, no 500
    finally:
        await _teardown(bus)


async def test_audio_stream_yields_pcm_chunks() -> None:
    """U154: the mic stream route emits raw s16le chunks with rate headers."""
    adapter, bus = await _setup()
    try:
        with _client().stream("GET", "/robot/audio/stream") as resp:
            assert resp.status_code == 200
            assert resp.headers["x-sample-rate"] == "16000"
            body = b"".join(resp.iter_bytes())
        # Fake adapter: 10 chunks of 100 ms silence @ 16 kHz s16le.
        assert len(body) == 10 * 1600 * 2
    finally:
        await _teardown(bus)
