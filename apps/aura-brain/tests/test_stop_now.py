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


class _RtConn:
    """The realtime client's shape, reduced to what a session touches."""

    def __init__(self, events) -> None:
        self._events = list(events)
        self.session = types.SimpleNamespace(update=self._noop)
        self.conversation = types.SimpleNamespace(
            item=types.SimpleNamespace(create=self._noop))
        self.response = types.SimpleNamespace(create=self._noop, cancel=self._noop)
        self.input_audio_buffer = types.SimpleNamespace(append=self._noop)

    async def _noop(self, *a, **k): ...

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def __aiter__(self):
        for e in self._events:
            await asyncio.sleep(0.01)
            yield e
        while True:                      # an open session with nothing to say
            await asyncio.sleep(0.02)


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


# ── U366: and it has to keep being true while he is already talking ────────
#
# Reported again, after U332: "quiet mode and stop still seem not to work
# (although activated he keeps going)" (translated), with the instruction to
# make sure the regression cannot come back.
#
# U332 put the Quiet gate at the START of a turn, which is where a turn is
# decided — and that is exactly why it looked like it did nothing. An open Live
# session is not a turn: it holds the microphone for up to LIVE_SESSION_MAX_S
# (ten minutes by default), and the supervising loop that ticks every second
# asked whether the owner had pressed Stop but never whether he was still
# allowed to speak. So switching Quiet on mid-conversation changed the header
# and nothing else, for up to ten minutes.
#
# These tests drive the REAL policy — the same module the console's Quiet
# switch writes through — so a future change that keeps the gate but loses the
# chain still fails.


@pytest.fixture()
def policy(tmp_path, monkeypatch):
    """The actual policy the console writes, on a throwaway path."""
    monkeypatch.setenv("MODE_POLICY_PATH", str(tmp_path / "mode-policy.json"))
    from orchestrator import mode_policy

    mode_policy.set_quiet(False)
    mode_policy.set_active("work")
    return mode_policy


async def _open_session(robot=None):
    robot = robot or _Robot()
    conn = _Conn([{"type": "session.output_audio.delta", "delta": _voiced(400)}
                  for _ in range(8)])
    sess = LiveSession(robot=robot, bus=_Bus(), conn_factory=lambda: conn,
                       meter=LiveMeter())
    task = asyncio.ensure_future(sess.run())
    await asyncio.sleep(0.25)            # he is mid-sentence
    return sess, task, robot


async def test_quiet_switched_on_mid_conversation_ends_it(policy) -> None:
    """The reported case: he is talking, Quiet goes on, and he keeps going."""
    sess, task, robot = await _open_session()
    spoken = len(robot.segments)

    policy.set_quiet(True)

    await asyncio.wait_for(task, timeout=5)
    assert "quiet" in sess.closed_reason.lower(), sess.closed_reason
    assert len(robot.segments) <= spoken + 1, "he kept playing what was queued"


async def test_present_mode_ends_an_open_conversation(policy) -> None:
    """U334 closed the door an open session walks through: on stage only the
    scenario speaks, and a session that is already running was never asked."""
    sess, task, _ = await _open_session()

    policy.set_active("presentation")
    assert policy.presenting(), "the test did not actually put him on stage"

    await asyncio.wait_for(task, timeout=5)
    assert "present" in sess.closed_reason.lower(), sess.closed_reason


async def test_a_policy_that_cannot_be_read_never_ends_a_conversation(monkeypatch) -> None:
    """The mirror of U332's rule: a policy we cannot read must not take his
    voice away. Silence is the failure mode nobody can diagnose."""
    from aura_brain import hush

    monkeypatch.setattr(hush, "_ask", lambda: (_ for _ in ()).throw(RuntimeError("no policy")))
    sess, task, _ = await _open_session()

    await asyncio.sleep(0.6)
    assert not task.done(), "an unreadable policy silenced him"
    sess.request_stop()
    await asyncio.wait_for(task, timeout=5)


async def test_quiet_is_checked_within_a_tick_not_at_the_end(policy) -> None:
    """Within about a second — the same promise Stop makes. Ten minutes later
    is not a different speed, it is a different feature."""
    sess, task, _ = await _open_session()

    policy.set_quiet(True)
    started = time.monotonic()
    await asyncio.wait_for(task, timeout=5)

    assert time.monotonic() - started < 2.5, "he took too long to fall silent"


async def test_the_realtime_session_falls_silent_too(policy) -> None:
    """Whichever engine is running, the switch means the same thing. Quiet that
    works on one engine and not the other is worse than neither, because it
    teaches the owner to trust it."""
    from aura_brain.realtime_session import RealtimeSession

    robot = _Robot()
    conn = _RtConn([types.SimpleNamespace(type="response.output_audio.delta",
                                          delta=_voiced(400)) for _ in range(8)])
    sess = RealtimeSession(robot=robot, bus=_Bus(), conn_factory=lambda m: conn)
    task = asyncio.ensure_future(sess.run())
    await asyncio.sleep(0.25)

    policy.set_quiet(True)

    await asyncio.wait_for(task, timeout=5)
    assert "quiet" in sess.closed_reason.lower(), sess.closed_reason


async def test_a_session_ended_by_quiet_does_not_hand_the_turn_to_the_pipeline(monkeypatch) -> None:
    """The mechanism behind "he keeps going anyway", and the nastier half.

    A Live session that produced no reply is treated as a failure, and the
    pipeline answers instead — which is right when the model fell over, and
    exactly wrong when the session ended BECAUSE the owner asked for silence.
    The test drives the real decision: a session that says it was stopped must
    be accepted as handled, not retried out loud.
    """
    monkeypatch.setenv("VOICE_ENGINE", "live")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    loop = _loop()

    class _StoppedSession:
        turns = 0
        delegations = 0
        stopped = True
        closed_reason = "quiet switched on"

        def __init__(self, **kw) -> None: ...
        async def run(self, **kw) -> None: ...
        def request_stop(self, reason: str = "") -> None: ...

    from aura_brain import live_session as _ls

    monkeypatch.setattr(_ls, "LiveSession", _StoppedSession)
    async def _instructions(*a, **k) -> str:
        return "be brief"

    monkeypatch.setattr(loop, "_instructions", _instructions)

    assert await loop._live_session_turn(b"", "hallo") is True, \
        "the pipeline was about to answer a question the owner had silenced"


def test_every_open_listening_session_asks_whether_it_may_still_speak() -> None:
    """The regression guard the owner asked for, in the shape that fits.

    This defect was not a wrong line; it was a rule implemented in one place
    and needed in three. U256 wrote the switch, U332 taught the turn gate about
    it, U334 did the same for Present — and the sessions, which are the only
    things that hold a microphone open for ten minutes, were never told.

    So the rule lives in `hush` now, and this is what notices when something
    that listens forgets to ask. A new session type added next year fails here
    rather than in the owner's living room.
    """
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "src" / "aura_brain"
    for name in ("live_session.py", "realtime_session.py"):
        text = (src / name).read_text(encoding="utf-8")
        assert "hush.silence_reason()" in text, (
            f"{name} holds the microphone open and never asks whether he may "
            f"still speak — see aura_brain/hush.py")
