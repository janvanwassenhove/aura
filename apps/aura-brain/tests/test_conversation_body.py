"""U326: the conversation engines use their body.

Driving the two session event pumps with fake connections: the realtime
session and the GPT-Live session both have to acknowledge the person while
they speak, and move while they answer. Neither commanded a single motion
before this unit.
"""

from __future__ import annotations

import asyncio
import base64
import os
import types

os.environ.setdefault("LLM_PROVIDER", "echo")

import numpy as np
import pytest
from aura_brain.live_session import LiveSession
from aura_brain.realtime_session import RealtimeSession


class _Robot:
    def __init__(self) -> None:
        self.motions: list[str] = []
        self.segments: list[bytes] = []

    async def execute_motion(self, command) -> bool:
        self.motions.append(command.motion_id)
        return True

    async def speak_segment(self, audio_b64: str) -> bool:
        self.segments.append(base64.b64decode(audio_b64))
        return True

    async def stop_audio(self) -> dict:
        return {"ok": True}

    async def stream_audio(self, raw: bool = False):
        if False:
            yield b""


class _Bus:
    def __init__(self) -> None:
        self.events = []

    async def publish(self, event) -> None:
        self.events.append(event)


class _RealtimeConn:
    """Enough of the Realtime connection for _pump_events."""

    def __init__(self, events) -> None:
        self._events = list(events)
        self.response = types.SimpleNamespace(cancel=self._noop, create=self._noop)

    async def _noop(self, *a, **k): ...

    async def __aiter__(self):
        for e in self._events:
            await asyncio.sleep(0.005)
            yield e


class _Ev:
    def __init__(self, type, **kw) -> None:
        self.type = type
        for k, v in kw.items():
            setattr(self, k, v)


class _LiveConn:
    def __init__(self, events) -> None:
        self._events = list(events)
        self.sent: list[dict] = []

    async def send(self, ev: dict) -> None:
        self.sent.append(ev)

    async def __aiter__(self):
        for e in self._events:
            await asyncio.sleep(0.005)
            yield e


def _voiced(ms: int = 200) -> str:
    return base64.b64encode(np.full(24 * ms, 3000, dtype=np.int16).tobytes()).decode()


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setenv("BACKCHANNEL_MIN_S", "0.01")
    monkeypatch.setenv("TALK_GESTURE_MIN_S", "0")
    monkeypatch.setenv("LIVE_SEGMENT_MS", "10000")
    monkeypatch.setenv("LIVE_VOICE_HANGOVER_S", "0.05")


# ── the realtime session ───────────────────────────────────────────────────

async def test_realtime_acknowledges_while_you_speak_and_moves_while_it_answers() -> None:
    robot, bus = _Robot(), _Bus()
    sess = RealtimeSession(robot=robot, bus=bus)
    conn = _RealtimeConn([
        _Ev("input_audio_buffer.speech_started"),
        _Ev("input_audio_buffer.speech_started"),   # still talking
        _Ev("input_audio_buffer.speech_stopped"),
        _Ev("response.output_audio_transcript.delta", delta="Hallo Jan, goedemorgen!"),
        _Ev("response.done"),
    ])
    await sess._pump_events(conn)
    assert robot.motions, "he stood still through the whole exchange"
    assert "wave" in robot.motions, "the greeting he spoke shapes the move"


async def test_realtime_stops_acknowledging_when_you_stop_talking() -> None:
    robot = _Robot()
    sess = RealtimeSession(robot=robot, bus=_Bus())
    conn = _RealtimeConn([
        _Ev("input_audio_buffer.speech_started"),
        _Ev("input_audio_buffer.speech_stopped"),
    ])
    await sess._pump_events(conn)
    settled = len(robot.motions)
    await asyncio.sleep(0.08)
    assert len(robot.motions) == settled, "nodding at nobody"


# ── the GPT-Live session ───────────────────────────────────────────────────

async def test_live_acknowledges_while_you_speak() -> None:
    robot = _Robot()
    sess = LiveSession(robot=robot, bus=_Bus(), conn_factory=lambda: None)
    conn = _LiveConn([
        {"type": "session.input_transcript.delta", "delta": "Wat staat er "},
        {"type": "session.input_transcript.delta", "delta": "vandaag op mijn agenda?"},
    ])
    await sess._pump_events(conn)
    assert robot.motions, "GPT-Live commanded no motion at all"


async def test_live_moves_while_it_answers() -> None:
    robot = _Robot()
    sess = LiveSession(robot=robot, bus=_Bus(), conn_factory=lambda: None)
    conn = _LiveConn([
        {"type": "session.output_transcript.delta", "delta": "Hallo, goedemorgen!"},
        {"type": "session.output_audio.delta", "delta": _voiced(200)},
        {"type": "session.output_audio.delta", "delta": base64.b64encode(
            np.zeros(24 * 200, dtype=np.int16).tobytes()).decode()},
    ])
    await sess._pump_events(conn)
    assert "wave" in robot.motions
