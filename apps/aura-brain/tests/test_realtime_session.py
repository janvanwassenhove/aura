"""U154: conversation-session mode — persistent Realtime connection, server VAD.

All fakes, no network: a fake robot mic stream + a fake Realtime connection.
"""

from __future__ import annotations

import asyncio
import base64
import os
import time

os.environ.setdefault("LLM_PROVIDER", "echo")

import numpy as np
import pytest
from aura_brain.realtime_session import (
    RealtimeSession,
    _resample_16k_to_24k,
    session_enabled,
)
from aura_brain.realtime_voice import CostMeter

# ------------------------------------------------------------------
# Helpers / fakes
# ------------------------------------------------------------------

class _Ev:
    def __init__(self, type, **kw):
        self.type = type
        for k, v in kw.items():
            setattr(self, k, v)


class _FakeConn:
    """Stands in for the OpenAI Realtime connection; records appends."""

    def __init__(self, events, hang_after: bool = False):
        self._events = events
        self._hang = hang_after
        self.appended: list[bytes] = []
        self.cancelled = 0
        import types as _t
        self.session = _t.SimpleNamespace(update=self._noop)
        self.conversation = _t.SimpleNamespace(item=_t.SimpleNamespace(create=self._noop))
        self.response = _t.SimpleNamespace(create=self._noop, cancel=self._cancel)
        self.input_audio_buffer = _t.SimpleNamespace(append=self._append)

    async def _noop(self, *a, **k): ...

    async def _cancel(self, *a, **k):
        self.cancelled += 1

    async def _append(self, audio: str = "", **k):
        self.appended.append(base64.b64decode(audio))

    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False

    async def __aiter__(self):
        for e in self._events:
            await asyncio.sleep(0.01)  # realistic pacing: mic pumps in between
            yield e
        while self._hang:  # simulate an open connection with no traffic
            await asyncio.sleep(0.05)


class _FakeRobot:
    def __init__(self, chunks: int = 5, chunk: bytes | None = None):
        self._chunks = chunks
        # Non-silent int16 so resampling has real content.
        self._chunk = chunk if chunk is not None else (
            (np.ones(1600, dtype=np.int16) * 1000).tobytes())
        self.segments: list[bytes] = []

    async def stream_audio(self, raw: bool = False):
        for _ in range(self._chunks):
            await asyncio.sleep(0.001)
            yield self._chunk
        # keep the "mic" open a little so the events task decides the ending
        await asyncio.sleep(0.3)

    async def speak_segment(self, audio_b64: str) -> bool:
        self.segments.append(base64.b64decode(audio_b64))
        return True

    async def stop_audio(self) -> dict:
        self.stopped = getattr(self, "stopped", 0) + 1
        return {"ok": True}


class _Bus:
    def __init__(self):
        self.events = []

    async def publish(self, event):
        self.events.append(event)


# ------------------------------------------------------------------
# Unit bits
# ------------------------------------------------------------------

def test_session_enabled_default_on(monkeypatch) -> None:
    monkeypatch.delenv("REALTIME_SESSION", raising=False)
    assert session_enabled() is True
    monkeypatch.setenv("REALTIME_SESSION", "false")
    assert session_enabled() is False


def test_resample_16k_to_24k_length() -> None:
    pcm16 = (np.ones(1600, dtype=np.int16) * 500).tobytes()  # 100 ms @ 16 kHz
    out = _resample_16k_to_24k(pcm16)
    assert len(out) == 2400 * 2  # 100 ms @ 24 kHz, s16le
    assert _resample_16k_to_24k(b"") == b""


# ------------------------------------------------------------------
# Full session flow
# ------------------------------------------------------------------

async def test_session_streams_mic_plays_segments_and_publishes(monkeypatch) -> None:
    monkeypatch.setenv("REALTIME_SEGMENT_MS", "1")  # tiny → every delta flushes
    monkeypatch.setenv("SELF_HEARING_COOLDOWN_S", "0")
    reply_audio = base64.b64encode(b"\x01\x02" * 60).decode()
    events = [
        _Ev("input_audio_buffer.speech_started"),
        _Ev("conversation.item.input_audio_transcription.completed",
            transcript="vertel eens een mop"),
        _Ev("response.output_audio_transcript.delta", delta="Waarom fietst een kip?"),
        _Ev("response.output_audio.delta", delta=reply_audio),
        _Ev("response.done", response=type("R", (), {"usage": {
            "input_token_details": {"audio_tokens": 100},
            "output_token_details": {"audio_tokens": 200},
        }})()),
    ]
    conn = _FakeConn(events)
    robot = _FakeRobot()
    bus = _Bus()
    meter = CostMeter()
    heard: list[str] = []
    sess = RealtimeSession(robot=robot, bus=bus, instructions="Wees Richie",
                           conn_factory=lambda m: conn, meter=meter,
                           on_reply=heard.append)
    await sess.run(initial_text="")
    await asyncio.sleep(0.01)  # let fire-and-forget speak_segment land

    assert conn.appended, "mic chunks must reach input_audio_buffer.append"
    assert robot.segments and robot.segments[0] == b"\x01\x02" * 60
    types = [type(e).__name__ for e in bus.events]
    assert "TranscriptUpdated" in types      # the user's words (server STT)
    assert "ResponseDrafted" in types        # Richie's reply, already voiced
    drafted = next(e for e in bus.events if type(e).__name__ == "ResponseDrafted")
    assert drafted.already_voiced is True
    assert sess.turns == 1 and meter.turns == 1
    assert heard == ["Waarom fietst een kip?"]  # echo guard was fed


async def test_session_gates_mic_while_playing(monkeypatch) -> None:
    """§6.1 half-duplex: mic chunks during playback are dropped, not appended."""
    monkeypatch.setenv("SELF_HEARING_COOLDOWN_S", "0")
    conn = _FakeConn([])
    robot = _FakeRobot(chunks=3)
    sess = RealtimeSession(robot=robot, bus=_Bus(), conn_factory=lambda m: conn)
    sess._playing_until = time.monotonic() + 60  # Richie is "speaking"
    await sess._pump_mic(conn)
    assert conn.appended == []


async def test_session_idle_timeout_closes(monkeypatch) -> None:
    monkeypatch.setenv("REALTIME_SESSION_IDLE_S", "0.2")
    conn = _FakeConn([], hang_after=True)   # open connection, no traffic
    robot = _FakeRobot(chunks=2)
    sess = RealtimeSession(robot=robot, bus=_Bus(), conn_factory=lambda m: conn)
    t0 = time.monotonic()
    await asyncio.wait_for(sess.run(), timeout=5.0)
    assert "idle" in sess.closed_reason or "mic stream ended" in sess.closed_reason
    assert time.monotonic() - t0 < 4.0


async def test_session_barge_in_cuts_playback(monkeypatch) -> None:
    """U156: with AEC full duplex, speech during playback cuts Richie off."""
    monkeypatch.setenv("REALTIME_BARGE_IN", "true")
    monkeypatch.setenv("REALTIME_SEGMENT_MS", "1")
    # U168e: ~1.25 s of audio, NOT 120 bytes (2.5 ms). The barge branch needs
    # monotonic() < playing_until when speech_started arrives ~10 ms later —
    # a 2.5 ms window only "passed" on Windows because its clock ticks in
    # ~15 ms steps; Linux's precise clock exposed the race.
    reply_audio = base64.b64encode(b"\x01\x02" * 30_000).decode()
    events = [
        _Ev("response.output_audio.delta", delta=reply_audio),  # playing…
        _Ev("input_audio_buffer.speech_started"),               # user interrupts
        _Ev("response.done", response=type("R", (), {"usage": {}})()),
    ]
    conn = _FakeConn(events)
    robot = _FakeRobot(chunks=2)
    sess = RealtimeSession(robot=robot, bus=_Bus(), conn_factory=lambda m: conn)
    await sess.run()
    assert getattr(robot, "stopped", 0) == 1     # playback was cut
    assert conn.cancelled == 1                   # response cancelled server-side
    assert sess._playing_until == 0.0


async def test_session_barge_in_off_keeps_gate(monkeypatch) -> None:
    """Default (no AEC): mic gated during playback; no barge-in triggers."""
    monkeypatch.delenv("REALTIME_BARGE_IN", raising=False)
    monkeypatch.setenv("REALTIME_TAIL_MAX_S", "0.2")  # fake 60s playback clock
    events = [
        _Ev("input_audio_buffer.speech_started"),
        _Ev("response.done", response=type("R", (), {"usage": {}})()),
    ]
    conn = _FakeConn(events)
    robot = _FakeRobot(chunks=2)
    sess = RealtimeSession(robot=robot, bus=_Bus(), conn_factory=lambda m: conn)
    sess._playing_until = time.monotonic() + 60
    await sess.run()
    assert getattr(robot, "stopped", 0) == 0
    assert conn.cancelled == 0


async def test_turn_detection_is_not_trigger_happy(monkeypatch) -> None:
    """U163: the default eagerness fired on any pause, so noise became turns."""
    from aura_brain.realtime_session import _turn_detection

    monkeypatch.delenv("REALTIME_VAD_EAGERNESS", raising=False)
    assert _turn_detection("semantic_vad") == {
        "type": "semantic_vad", "eagerness": "low"}

    monkeypatch.setenv("REALTIME_VAD_EAGERNESS", "high")
    assert _turn_detection("semantic_vad")["eagerness"] == "high"

    server = _turn_detection("server_vad")
    assert server["type"] == "server_vad"
    assert server["silence_duration_ms"] >= 500      # don't cut on a breath
    assert server["threshold"] > 0.5                 # above room tone


async def test_seed_utterance_tail_cannot_trigger_a_second_reply(monkeypatch) -> None:
    """U163: seeding with initial_text answers the sentence; the mic then opens
    on its TAIL and produced a duplicate answer to the same sentence."""
    monkeypatch.setenv("REALTIME_SEED_MUTE_S", "60")   # still muted during test
    monkeypatch.setenv("SELF_HEARING_COOLDOWN_S", "0")
    conn = _FakeConn([_Ev("response.done", response=type("R", (), {"usage": {}})())])
    robot = _FakeRobot(chunks=5)
    sess = RealtimeSession(robot=robot, bus=_Bus(), conn_factory=lambda m: conn)

    await sess.run(initial_text="vertel eens een mop")
    assert conn.appended == []          # nothing from the mic reached the server


async def test_mic_opens_after_the_seed_mute_expires(monkeypatch) -> None:
    monkeypatch.setenv("REALTIME_SEED_MUTE_S", "0")    # expired immediately
    monkeypatch.setenv("SELF_HEARING_COOLDOWN_S", "0")
    conn = _FakeConn([])
    robot = _FakeRobot(chunks=3)
    sess = RealtimeSession(robot=robot, bus=_Bus(), conn_factory=lambda m: conn)
    await sess._pump_mic(conn)
    assert conn.appended, "the mic must resume once the seed tail has passed"


async def test_session_raises_on_error_event() -> None:
    conn = _FakeConn([_Ev("error", error="model_not_found")])
    robot = _FakeRobot(chunks=1)
    sess = RealtimeSession(robot=robot, bus=_Bus(), conn_factory=lambda m: conn)
    with pytest.raises(RuntimeError):
        await sess.run()


async def test_request_stop_ends_the_session_promptly(monkeypatch) -> None:
    """U184: the panic stop must end a session that is otherwise idling."""
    monkeypatch.setenv("REALTIME_SESSION_IDLE_S", "600")   # would never time out
    conn = _FakeConn([], hang_after=True)
    # The mic must outlive the test: with a short stream CI finished it first
    # and run() returned "mic stream ended" before the stop was observed —
    # a race in the TEST, not in the panic stop.
    robot = _FakeRobot(chunks=100_000)
    sess = RealtimeSession(robot=robot, bus=_Bus(), conn_factory=lambda m: conn)

    async def stop_soon():
        await asyncio.sleep(0.15)
        sess.request_stop()

    t0 = time.monotonic()
    await asyncio.gather(asyncio.wait_for(sess.run(), timeout=10.0), stop_soon())
    assert sess.closed_reason == "stopped by owner"
    assert time.monotonic() - t0 < 5.0
