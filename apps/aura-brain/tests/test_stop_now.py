"""U332: Stop means now, and hushed means he does not answer the television.

Two things the owner reported in one breath, both measured from a screenshot of
Present mode with a film playing:

* **Quiet had no effect.** It cannot: a Live (or realtime) session keeps the
  microphone open with no wake word, so the television is what asks the
  questions — and he answered its dialogue, under a header promising "he
  answers when asked and never speaks first".
* **Stop did not stop him.** The panic stop cut the current audio and asked the
  session to end, but the session then waited out the speaker tail (up to
  `REALTIME_TAIL_MAX_S`, 20 s) and its playback queue kept posting the segments
  that were already buffered. So he carried on talking after the button.
"""

from __future__ import annotations

import asyncio
import base64
import os
import time
import types

os.environ.setdefault("LLM_PROVIDER", "echo")

import numpy as np
import pytest
from aura_brain.live_session import LiveMeter, LiveSession
from aura_brain.voice_loop import VoiceLoop


def _voiced(ms: int = 200, amp: int = 3000) -> str:
    return base64.b64encode(np.full(24 * ms, amp, dtype=np.int16).tobytes()).decode()


class _Conn:
    """Streams a long reply, then keeps the connection open."""

    def __init__(self, events) -> None:
        self.sent: list[dict] = []
        self._events = list(events)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def send(self, ev: dict) -> None:
        self.sent.append(ev)

    async def recv(self) -> dict:
        return {"type": "session.started", "session": {"id": "s"}}

    async def __aiter__(self):
        for e in self._events:
            await asyncio.sleep(0.01)
            yield e
        while True:                      # an open session with nothing to say
            await asyncio.sleep(0.02)


class _Robot:
    def __init__(self) -> None:
        self.segments: list[bytes] = []
        self.stopped = 0

    async def stream_audio(self, raw: bool = False):
        while True:
            await asyncio.sleep(0.05)
            yield np.zeros(1600, dtype=np.int16).tobytes()

    async def speak_segment(self, audio_b64: str) -> bool:
        self.segments.append(base64.b64decode(audio_b64))
        return True

    async def stop_audio(self) -> dict:
        self.stopped += 1
        return {"ok": True}


class _Bus:
    async def publish(self, event) -> None: ...


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setenv("SELF_HEARING_COOLDOWN_S", "0")
    monkeypatch.setenv("LIVE_CLOSE_WAIT_S", "0.2")
    monkeypatch.setenv("LIVE_SEGMENT_MS", "100")
    monkeypatch.setenv("LIVE_SESSION_IDLE_S", "30")
    # The point of the test: this cap must NOT be waited out after a Stop.
    monkeypatch.setenv("REALTIME_TAIL_MAX_S", "20")


# ── Stop means now ─────────────────────────────────────────────────────────

async def test_stop_ends_the_session_without_waiting_out_the_reply() -> None:
    """He was mid-sentence with several seconds of audio already buffered."""
    robot = _Robot()
    conn = _Conn([{"type": "session.output_audio.delta", "delta": _voiced(400)}
                  for _ in range(8)])
    sess = LiveSession(robot=robot, bus=_Bus(), conn_factory=lambda: conn,
                       meter=LiveMeter())
    task = asyncio.ensure_future(sess.run())
    await asyncio.sleep(0.25)            # let him start talking
    sess.request_stop()

    started = time.monotonic()
    await asyncio.wait_for(task, timeout=6)
    assert time.monotonic() - started < 3, "it waited out the speaker tail"
    assert sess.closed_reason == "stopped by owner"


async def test_nothing_queued_is_played_after_the_button() -> None:
    """The queue is what kept him talking: the audio was already on its way."""
    robot = _Robot()
    conn = _Conn([{"type": "session.output_audio.delta", "delta": _voiced(400)}
                  for _ in range(10)])
    sess = LiveSession(robot=robot, bus=_Bus(), conn_factory=lambda: conn,
                       meter=LiveMeter())
    task = asyncio.ensure_future(sess.run())
    await asyncio.sleep(0.25)
    sess.request_stop()
    spoken_at_stop = len(robot.segments)
    await asyncio.wait_for(task, timeout=6)
    assert len(robot.segments) == spoken_at_stop, "he kept talking after Stop"


def test_stop_drops_what_is_waiting_and_clears_the_playback_clock() -> None:
    sess = LiveSession(robot=_Robot(), bus=_Bus(), conn_factory=lambda: None,
                       meter=LiveMeter())
    q: asyncio.Queue = asyncio.Queue()
    q.put_nowait(b"\x01\x02")
    q.put_nowait(b"\x03\x04")
    sess._play_q = q
    sess._playing_until = time.monotonic() + 30

    sess.request_stop()

    assert q.empty(), "queued audio survived the stop"
    assert sess._playing_until == 0.0, "the session still thinks it is speaking"


# ── hushed means no open microphone ────────────────────────────────────────

class _QuietPolicy:
    def __init__(self, quiet: bool) -> None:
        self._quiet = quiet

    def quiet(self) -> bool:
        return self._quiet


def _loop() -> VoiceLoop:
    class _R:
        async def stream_audio(self, raw: bool = False):
            if False:
                yield b""

    return VoiceLoop(robot=_R(), pipeline=None, bus=_Bus(), default_wake_word="richie")


async def test_hushed_keeps_the_wake_word_in_charge(monkeypatch) -> None:
    """A session with an open mic makes the television the one asking."""
    import sys

    monkeypatch.setenv("VOICE_ENGINE", "live")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setitem(sys.modules, "orchestrator.mode_policy", _QuietPolicy(True))
    loop = _loop()
    opened: list[int] = []

    async def _fake(wav, command):
        opened.append(1)
        return True

    monkeypatch.setattr(loop, "_live_session_turn", _fake)

    assert await loop._speech_turn(b"wav", "hallo") is False
    assert opened == [], "a hushed robot opened a listening session"


async def test_it_still_answers_when_he_is_not_hushed(monkeypatch) -> None:
    import sys

    monkeypatch.setenv("VOICE_ENGINE", "live")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setitem(sys.modules, "orchestrator.mode_policy", _QuietPolicy(False))
    loop = _loop()

    async def _fake(wav, command):
        return True

    monkeypatch.setattr(loop, "_live_session_turn", _fake)
    assert await loop._speech_turn(b"wav", "hallo") is True


async def test_a_missing_policy_never_silences_him(monkeypatch) -> None:
    """If the policy cannot be read, the engine still works — a broken import
    must not quietly turn the robot into a pipeline-only one."""
    import sys

    monkeypatch.setenv("VOICE_ENGINE", "live")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setitem(sys.modules, "orchestrator.mode_policy",
                        types.SimpleNamespace())      # no quiet() at all
    loop = _loop()

    async def _fake(wav, command):
        return True

    monkeypatch.setattr(loop, "_live_session_turn", _fake)
    assert await loop._speech_turn(b"wav", "hallo") is True


# ── the realtime session has the same shape, and had the same bug ──────────

def test_the_realtime_session_also_drops_what_is_waiting() -> None:
    """Both session engines buffer segments the same way; Stop has to mean the
    same thing in both, or it means nothing in the one you happen to be using."""
    from aura_brain.realtime_session import RealtimeSession

    sess = RealtimeSession(robot=_Robot(), bus=_Bus())
    q: asyncio.Queue = asyncio.Queue()
    q.put_nowait(b"")
    sess._play_q = q
    sess._playing_until = time.monotonic() + 30

    sess.request_stop()

    assert q.empty()
    assert sess._playing_until == 0.0
    assert sess._stopping is True
