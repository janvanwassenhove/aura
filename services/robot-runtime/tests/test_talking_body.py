"""U407: in Present, he moves as he speaks — antennae, and a nodding head.

Asked for as: *"in present mode -> when the robot has to say anything
(following the scenario) -> ensure while talking antenna's are moving and head
moving up & down while looking to audience (as if actually talking)"*.

He did not, on either speaker:

* **On his own speaker** a talk's line is one whole utterance (`POST
  /robot/speak`), and `play_audio` holds the motion lock for all of it so that
  no gesture can cut the line. The U157 antenna loop was only ever started by
  the streamed path — and it stands down while the lock is held. So during a
  talk the antennae never moved; the head had the SDK's audio-reactive sway,
  and that was all.
* **On the laptop** (U364) the robot was told nothing at all, and stood still
  while the room heard him.

Now a line he plays himself keeps the antennae going for as long as it lasts —
it is his own voice holding the lock, and antennae cannot cut it. A line the
laptop plays is handed to him as it starts, to move along with rather than to
play: the antennae as above, and the head nods through the channel the SDK's
own sway uses — composed on top of wherever follow-me points it, so he never
looks away from the room to do it.
"""

from __future__ import annotations

import asyncio
import base64
import os
import sys
import tempfile
import time
import types

import numpy as np
import pytest
from robot_runtime import sleep_state

RATE = 24_000
ZERO = [0.0] * 6


class FakeMini:
    """Records what the adapter asks of the SDK, and when."""

    def __init__(self, **kwargs) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.sent: list[tuple[float, object]] = []
        self.client = types.SimpleNamespace(
            disconnect=lambda: None,
            send_command=lambda cmd: self.sent.append((time.monotonic(), cmd)))

    def goto_target(self, head=None, antennas=None, duration=0.5, body_yaw=0.0) -> None:
        self.calls.append(("goto_target", {"head": head, "antennas": antennas,
                                           "at": time.monotonic()}))

    def wake_up(self) -> None: ...

    def goto_sleep(self) -> None: ...

    def start_head_tracking(self, weight: float = 1.0) -> None: ...

    def stop_head_tracking(self) -> None: ...

    def get_tracked_face(self, wait: bool = True, timeout: float = 5.0):
        return types.SimpleNamespace(detected=False)

    def set_automatic_body_yaw(self, enabled: bool) -> None: ...

    def set_target_body_yaw(self, yaw: float) -> None: ...

    def release_media(self) -> None: ...

    def acquire_media(self) -> None: ...


class _Sway:
    """The SDK's speech tapper, reduced to what matters here: speech sways the
    head, silence does not. One result per 50 ms hop, like the real one."""

    def __init__(self, rng_seed: int = 7, sample_rate: int = 16_000) -> None:
        self.hop = int(sample_rate * 50 / 1000)

    def feed(self, pcm) -> list[dict]:
        out = []
        for i in range(0, len(pcm) - self.hop + 1, self.hop):
            loud = float(np.max(np.abs(pcm[i:i + self.hop])))
            pitch = 0.07 * loud * (1.0 if (i // self.hop) % 2 else -1.0)
            out.append({"pitch_rad": pitch, "yaw_rad": 0.0, "roll_rad": 0.0,
                        "x_mm": 0.0, "y_mm": 0.0, "z_mm": 0.0})
        return out


class SetSpeechOffsetsCmd:
    def __init__(self, offsets) -> None:
        self.offsets = list(offsets)


class FakeMedia:
    def __init__(self) -> None:
        self.played: list[float] = []

    def play_sound(self, path: str) -> None:
        self.played.append(time.monotonic())

    def clear_player(self) -> None: ...


@pytest.fixture()
def adapter(monkeypatch):
    for var, value in {"HEAD_TRACKING": "false", "IDLE_SCAN_S": "0",
                       "TRACKING_WATCHDOG_S": "0", "HEAD_WOBBLE": "false",
                       "BODY_FOLLOW": "false", "TALK_ANTENNAS": "true"}.items():
        monkeypatch.setenv(var, value)
    root = types.ModuleType("reachy_mini")
    root.ReachyMini = lambda **kw: FakeMini(**kw)
    motion = types.ModuleType("reachy_mini.motion")
    tapper = types.ModuleType("reachy_mini.motion.speech_tapper")
    tapper.HOP_MS = 50
    tapper.SwayRollRT = _Sway
    motion.speech_tapper = tapper
    io = types.ModuleType("reachy_mini.io")
    protocol = types.ModuleType("reachy_mini.io.protocol")
    protocol.SetSpeechOffsetsCmd = SetSpeechOffsetsCmd
    io.protocol = protocol
    root.motion, root.io = motion, io
    for name, module in {"reachy_mini": root, "reachy_mini.motion": motion,
                         "reachy_mini.motion.speech_tapper": tapper,
                         "reachy_mini.io": io, "reachy_mini.io.protocol": protocol}.items():
        monkeypatch.setitem(sys.modules, name, module)

    from robot_runtime.adapters.reachy import ReachyRobotAdapter

    # On the robot the antennae move every 1.2–2.4 s; a test cannot wait that long.
    monkeypatch.setattr(ReachyRobotAdapter, "TALK_GAP_S", (0.05, 0.08), raising=False)
    sleep_state.set_asleep(False)
    yield ReachyRobotAdapter(host="stub", connection_mode="network", media_backend="no_media")
    sleep_state.set_asleep(False)


@pytest.fixture()
def speaker(adapter, monkeypatch) -> FakeMedia:
    """His own speaker. The line is written to /dev/shm on the Pi; elsewhere
    the temp dir does."""
    real = tempfile.NamedTemporaryFile

    def _ntf(*args, dir=None, **kw):  # noqa: A002 — tempfile's own name
        return real(*args, dir=dir if dir and os.path.isdir(dir) else None, **kw)

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", _ntf)
    media = FakeMedia()
    monkeypatch.setattr(adapter, "_media", lambda: media)
    return media


def _tone(seconds: float, peak: float = 0.6) -> bytes:
    n = int(RATE * seconds)
    t = np.arange(n, dtype=np.float32) / RATE
    return (np.sin(2 * np.pi * 220 * t) * peak * 32767).astype(np.int16).tobytes()


def _antennae(mini: FakeMini, since: float = 0.0, until: float = float("inf")) -> list[dict]:
    return [c for name, c in mini.calls
            if name == "goto_target" and c["antennas"]
            and any(abs(a) > 0.01 for a in c["antennas"]) and since <= c["at"] <= until]


def _head_targets(mini: FakeMini) -> list[dict]:
    return [c for name, c in mini.calls if name == "goto_target" and c["head"] is not None]


# ── on his own speaker ───────────────────────────────────────────────────────

async def test_a_line_he_plays_himself_moves_his_antennae_while_it_plays(adapter, speaker) -> None:
    await adapter.connect()
    mini = adapter._mini
    started = time.monotonic()
    await adapter.speak("Goedemorgen, Devoxx.", _tone(0.8))
    moved = _antennae(mini, started, time.monotonic())
    assert speaker.played, "the line was played"
    assert moved, "his antennae stood still for the whole line"
    assert all(c["head"] is None for c in moved), \
        "antennae only: the head stays with follow-me and the SDK's own sway"
    await adapter.disconnect()


async def test_his_antennae_still_wait_for_a_gesture(adapter) -> None:
    """Only his own voice lets them through the lock. A gesture holding it is
    not cut into (U157's rule, unchanged)."""
    await adapter.connect()
    mini = adapter._mini
    async with adapter._motion_lock:
        adapter._talk_until = time.monotonic() + 0.4
        adapter._ensure_talk_task()
        await asyncio.sleep(0.3)
        assert _antennae(mini) == []
    await adapter.disconnect()


# ── through the laptop ───────────────────────────────────────────────────────

async def test_a_line_on_the_laptop_nods_his_head(adapter) -> None:
    await adapter.connect()
    mini = adapter._mini
    result = await adapter.talk_along(_tone(0.6), RATE)
    assert result["moving"] is True
    assert result["seconds"] == pytest.approx(0.6, abs=0.01)
    await asyncio.sleep(0.9)
    pitches = [cmd.offsets[4] for _, cmd in mini.sent]
    assert any(p > 0.01 for p in pitches) and any(p < -0.01 for p in pitches), \
        "his head did not go up and down with the line"
    assert mini.sent[-1][1].offsets == ZERO, "and it comes to rest when the line ends"
    await adapter.disconnect()


async def test_the_nod_is_laid_over_where_he_looks_not_instead_of_it(adapter) -> None:
    """Speech offsets are composed with the tracker's aim on the daemon — the
    channel the SDK's own sway uses. A head target would take his eyes off the
    face follow-me has found, which is who he is talking to."""
    await adapter.connect()
    mini = adapter._mini
    await adapter.talk_along(_tone(0.5), RATE)
    await asyncio.sleep(0.8)
    assert mini.sent, "nothing nodded"
    assert _head_targets(mini) == []
    await adapter.disconnect()


async def test_the_nodding_lasts_as_long_as_the_line(adapter) -> None:
    """One offset per 50 ms hop, spread over the line — not a burst at its start."""
    await adapter.connect()
    mini = adapter._mini
    start = time.monotonic()
    await adapter.talk_along(_tone(0.6), RATE)
    await asyncio.sleep(0.9)
    moving = [at - start for at, cmd in mini.sent if any(cmd.offsets)]
    assert moving and moving[-1] >= 0.4
    await adapter.disconnect()


async def test_a_line_on_the_laptop_moves_his_antennae_too(adapter) -> None:
    await adapter.connect()
    mini = adapter._mini
    start = time.monotonic()
    await adapter.talk_along(_tone(0.6), RATE)
    await asyncio.sleep(0.8)
    assert _antennae(mini, start), "antennae still"
    await adapter.disconnect()


async def test_stop_stops_the_nodding_too(adapter) -> None:
    await adapter.connect()
    mini = adapter._mini
    await adapter.talk_along(_tone(2.0), RATE)
    await asyncio.sleep(0.2)
    adapter.stop_audio()
    await asyncio.sleep(0.05)
    count = len(mini.sent)
    await asyncio.sleep(0.3)
    assert len(mini.sent) == count, "still nodding after Stop"
    assert mini.sent[-1][1].offsets == ZERO
    await adapter.disconnect()


async def test_asleep_he_does_not_talk_along(adapter) -> None:
    await adapter.connect()
    mini = adapter._mini
    sleep_state.set_asleep(True)
    result = await adapter.talk_along(_tone(0.4), RATE)
    assert result["moving"] is False and "asleep" in result["reason"]
    await asyncio.sleep(0.3)
    assert mini.sent == [] and _antennae(mini) == []
    await adapter.disconnect()


async def test_without_the_sdks_speech_tapper_he_says_his_head_stays_still(adapter, monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "reachy_mini.motion.speech_tapper")
    monkeypatch.delattr(sys.modules["reachy_mini.motion"], "speech_tapper")
    await adapter.connect()
    result = await adapter.talk_along(_tone(0.4), RATE)
    assert result["moving"] is True, "the antennae still move"
    assert "still" in result["head"]
    await adapter.disconnect()


# ── the route ────────────────────────────────────────────────────────────────

def _client(adapter):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from robot_runtime import routes

    routes.adapter = adapter
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app)


async def test_the_route_hands_the_line_to_his_body_and_not_his_speaker() -> None:
    from robot_runtime import routes
    from robot_runtime.adapters.fake import FakeRobotAdapter

    fake = FakeRobotAdapter()
    await fake.connect()
    try:
        r = _client(fake).post("/robot/speak/along",
                               json={"audio_b64": base64.b64encode(_tone(0.5)).decode()})
        assert r.status_code == 200
        assert r.json()["seconds"] == pytest.approx(0.5, abs=0.01)
        assert fake.talked_along == [pytest.approx(0.5, abs=0.01)]
        assert fake._played_audio == [], "moved along with, never played"
    finally:
        routes.adapter = None


def test_the_route_wants_audio() -> None:
    from robot_runtime import routes
    from robot_runtime.adapters.fake import FakeRobotAdapter

    try:
        client = _client(FakeRobotAdapter())
        assert client.post("/robot/speak/along", json={}).status_code == 422
        assert client.post("/robot/speak/along", json={"audio_b64": "%%%"}).status_code == 422
    finally:
        routes.adapter = None


def test_a_body_that_cannot_says_so() -> None:
    from robot_runtime import routes

    class _Asleep:
        async def talk_along(self, audio: bytes, sample_rate: int = RATE) -> dict:
            return {"moving": False, "seconds": 0.0, "reason": "asleep"}

    try:
        audio = {"audio_b64": base64.b64encode(_tone(0.2)).decode()}
        r = _client(_Asleep()).post("/robot/speak/along", json=audio)
        assert r.status_code == 409 and "asleep" in r.json()["error"]
        assert _client(object()).post("/robot/speak/along", json=audio).status_code == 501
    finally:
        routes.adapter = None
