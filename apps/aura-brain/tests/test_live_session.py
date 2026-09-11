"""U324: the GPT-Live session — all fakes, no network.

Each test pins one of the rules the U321 spikes turned into requirements
(ADR-011): silence is not speech, he is muted while he talks, delegated work
goes through OUR delegate and its result is spoken, a failure is reported
rather than invented, and an open session — billed per minute — closes itself.
"""

from __future__ import annotations

import asyncio
import base64
import os
import time

os.environ.setdefault("LLM_PROVIDER", "echo")

import numpy as np
import pytest
from aura_brain.live_session import (
    LiveMeter,
    LiveSession,
    _clip,
    _rms,
    live_model,
    live_voice,
    probe,
)


def _voiced(ms: int = 100, amp: int = 3000) -> bytes:
    return np.full(24 * ms, amp, dtype=np.int16).tobytes()


def _silent(ms: int = 100) -> bytes:
    return np.zeros(24 * ms, dtype=np.int16).tobytes()


def _audio(pcm: bytes) -> dict:
    return {"type": "session.output_audio.delta", "delta": base64.b64encode(pcm).decode()}


class _FakeLive:
    """Stands in for AsyncLiveConnection: records sends, replays server events.

    Items may be event dicts, ("sleep", s), or ("wait_sent", type) — pause
    until the session has sent an event of that type."""

    def __init__(self, events=(), started: bool = True, hang: bool = False):
        self.sent: list[dict] = []
        self._events = list(events)
        self._hang = hang
        self._first = ({"type": "session.started", "session": {"id": "live_test"}}
                       if started else {"type": "error", "error": {"message": "invalid_model"}})
        self._close_requested = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def send(self, ev: dict) -> None:
        self.sent.append(ev)
        if ev.get("type") == "session.close":
            self._close_requested = True

    async def recv(self) -> dict:
        return self._first

    def types(self) -> list[str]:
        return [e.get("type") for e in self.sent]

    async def __aiter__(self):
        for item in self._events:
            await asyncio.sleep(0.005)
            if isinstance(item, tuple) and item[0] == "sleep":
                await asyncio.sleep(item[1])
                continue
            if isinstance(item, tuple) and item[0] == "wait_sent":
                end = time.monotonic() + 2.0
                while item[1] not in self.types() and time.monotonic() < end:
                    await asyncio.sleep(0.01)
                continue
            yield item
        while self._hang:
            if self._close_requested:
                yield {"type": "session.closed", "reason": "close_requested"}
                return
            await asyncio.sleep(0.02)


class _Robot:
    def __init__(self, chunks: int = 3, gap: float = 0.001, then_wait: float = 0.3):
        self._chunks, self._gap, self._then = chunks, gap, then_wait
        self.segments: list[bytes] = []

    async def stream_audio(self, raw: bool = False):
        for _ in range(self._chunks):
            await asyncio.sleep(self._gap)
            yield (np.ones(1600, dtype=np.int16) * 800).tobytes()   # 100 ms @ 16 kHz
        await asyncio.sleep(self._then)

    async def speak_segment(self, audio_b64: str) -> bool:
        self.segments.append(base64.b64decode(audio_b64))
        return True

    async def stop_audio(self) -> dict:
        return {"ok": True}


class _Bus:
    def __init__(self):
        self.events = []

    async def publish(self, event):
        self.events.append(event)

    def of(self, name: str):
        return [e for e in self.events if type(e).__name__ == name]


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setenv("SELF_HEARING_COOLDOWN_S", "0")
    monkeypatch.setenv("LIVE_CLOSE_WAIT_S", "0.2")
    monkeypatch.setenv("REALTIME_TAIL_MAX_S", "0.1")
    for var in ("LIVE_MODEL", "LIVE_VOICE", "LIVE_BARGE_IN"):
        monkeypatch.delenv(var, raising=False)


def _session(conn, **kw) -> LiveSession:
    kw.setdefault("robot", _Robot())
    kw.setdefault("bus", _Bus())
    return LiveSession(conn_factory=lambda: conn, meter=LiveMeter(), **kw)


# ── what is asked for ──────────────────────────────────────────────────────

def test_it_asks_for_gpt_live_with_client_delegation() -> None:
    """Client delegation is what keeps tool use in OUR orchestrator, behind
    OUR approval gate — never a backend we do not control."""
    ev = _session(_FakeLive(), instructions="Wees Richie", voice="marin").start_event()
    s = ev["session"]
    assert ev["type"] == "session.start"
    assert s["model"] == "gpt-live-1"
    assert s["delegation"] == {"type": "client"}
    assert s["audio"]["format"] == {"type": "audio/pcm", "rate": 24000}
    assert s["audio"]["output"]["voice"] == "marin"
    assert s["instructions"] == "Wees Richie"


def test_model_and_voice_are_configurable_but_unverified_voices_are_not_passed(monkeypatch) -> None:
    monkeypatch.setenv("LIVE_MODEL", "gpt-live-2")
    assert live_model() == "gpt-live-2"
    # A character keeps its own voice where Live was measured to accept it...
    assert live_voice("Coral") == "coral"
    # ...and one Live refused, or was never seen to accept, would fail the start.
    assert live_voice("nova") == "marin"
    assert live_voice("some-unverified-voice") == "marin"
    monkeypatch.setenv("LIVE_VOICE", "cedar")
    assert live_voice("coral") == "cedar", "an explicit setting wins"


# ── audio in ───────────────────────────────────────────────────────────────

async def test_the_command_he_was_woken_with_is_heard_first() -> None:
    """Live has no text input, so the wake window's audio is sent — first."""
    conn = _FakeLive([])
    seed = _voiced(300)
    await _session(conn, robot=_Robot(chunks=0)).run(initial_pcm=seed, initial_text="hoe laat is het")
    appends = [base64.b64decode(e["audio"]) for e in conn.sent if e["type"] == "session.input_audio.append"]
    assert b"".join(appends)[:len(seed)] == seed


async def test_mic_audio_is_resampled_to_24k_and_forwarded() -> None:
    conn = _FakeLive([("sleep", 0.15)])
    await _session(conn, robot=_Robot(chunks=3)).run()
    appends = [base64.b64decode(e["audio"]) for e in conn.sent if e["type"] == "session.input_audio.append"]
    assert appends and all(len(a) == 2400 * 2 for a in appends)   # 100 ms @ 24 kHz


async def test_he_is_muted_while_he_speaks() -> None:
    """The Pi has no echo cancellation: his own voice must never reach him."""
    conn = _FakeLive()
    sess = _session(conn, robot=_Robot(chunks=3))
    sess._playing_until = time.monotonic() + 60
    await sess._pump_mic(conn)
    assert conn.types() == ["session.input_audio.mute"]
    assert "session.input_audio.append" not in conn.types()


async def test_and_unmuted_once_he_has_finished() -> None:
    conn = _FakeLive()
    sess = _session(conn, robot=_Robot(chunks=2))
    sess._muted = True
    await sess._pump_mic(conn)
    assert conn.types()[0] == "session.input_audio.unmute"
    assert "session.input_audio.append" in conn.types()


async def test_with_barge_in_he_keeps_listening(monkeypatch) -> None:
    monkeypatch.setenv("LIVE_BARGE_IN", "true")          # only with AEC on the robot
    conn = _FakeLive()
    sess = _session(conn, robot=_Robot(chunks=2))
    sess._playing_until = time.monotonic() + 60
    await sess._pump_mic(conn)
    assert "session.input_audio.mute" not in conn.types()
    assert "session.input_audio.append" in conn.types()


# ── audio out ──────────────────────────────────────────────────────────────

async def test_silence_is_not_played_and_does_not_count_as_speaking() -> None:
    """Measured: 74-81 % of what GPT-Live streams is digital silence. Treating
    it as speech keeps the mic gate shut forever — a deaf robot."""
    conn = _FakeLive([_audio(_silent()) for _ in range(10)])
    robot = _Robot(chunks=0)
    sess = _session(conn, robot=robot)
    await sess.run()
    assert robot.segments == []
    assert sess._playing_until == 0.0
    assert sess.turns == 0


async def test_a_reply_is_played_with_its_pauses_and_published(monkeypatch) -> None:
    monkeypatch.setenv("LIVE_SEGMENT_MS", "10000")      # one segment per utterance
    monkeypatch.setenv("LIVE_VOICE_HANGOVER_S", "0.25")
    events = [
        _audio(_silent()),
        {"type": "session.output_transcript.delta", "delta": "Goeiemorgen! "},
        _audio(_voiced(200)),
        _audio(_silent(100)),                           # a pause INSIDE the sentence
        _audio(_voiced(200)),
        {"type": "session.output_transcript.delta", "delta": "Ik kijk het na."},
        _audio(_silent(300)),                           # longer than the hangover
    ]
    conn = _FakeLive(events)
    robot, bus, heard = _Robot(chunks=0), _Bus(), []
    sess = _session(conn, robot=robot, bus=bus, on_reply=heard.append)
    await sess.run()
    await asyncio.sleep(0.02)
    assert b"".join(robot.segments) == _voiced(200) + _silent(100) + _voiced(200)
    drafted = bus.of("ResponseDrafted")
    assert [d.response_text for d in drafted] == ["Goeiemorgen! Ik kijk het na."]
    assert drafted[0].already_voiced is True
    assert heard == ["Goeiemorgen! Ik kijk het na."], "the echo guard is fed"
    assert sess.turns == 1


# ── delegation ─────────────────────────────────────────────────────────────

async def test_delegated_work_runs_through_our_delegate_and_the_result_is_spoken() -> None:
    """The whole point of U324: a natural voice that can still use tools."""
    asked: list[str] = []

    async def delegate(text: str) -> str:
        asked.append(text)
        return "Om tien uur de tandarts; vanaf twee uur regen in Gent."

    events = [
        {"type": "session.input_transcript.delta", "delta": "Wat staat er "},
        {"type": "session.input_transcript.delta", "delta": "vandaag op mijn agenda?"},
        {"type": "session.delegation.created",
         "delegation": {"id": "item_1", "type": "delegation", "target": "client"}},
        ("wait_sent", "session.commentary.append"),
    ]
    conn, bus = _FakeLive(events), _Bus()
    sess = _session(conn, bus=bus, delegate=delegate, robot=_Robot(chunks=0))
    await sess.run()
    assert asked == ["Wat staat er vandaag op mijn agenda?"]
    [result] = [e for e in conn.sent if e["type"] == "session.commentary.append"]
    assert result["delegation_id"] == "item_1"
    assert result["content"] == "Om tien uur de tandarts; vanaf twee uur regen in Gent."
    assert [t.transcript for t in bus.of("TranscriptUpdated")] == ["Wat staat er vandaag op mijn agenda?"]
    assert sess.delegations == 1


async def test_a_failed_lookup_is_reported_never_invented() -> None:
    async def delegate(text: str) -> str:
        raise ConnectionError("calendar unreachable")

    events = [
        {"type": "session.input_transcript.delta", "delta": "Wat staat er op mijn agenda?"},
        {"type": "session.delegation.created", "delegation": {"id": "item_2"}},
        ("wait_sent", "session.thinking.append"),
    ]
    conn = _FakeLive(events)
    await _session(conn, delegate=delegate, robot=_Robot(chunks=0)).run()
    assert "session.commentary.append" not in conn.types(), "no invented result"
    [note] = [e for e in conn.sent if e["type"] == "session.thinking.append"]
    assert note["delegation_id"] == "item_2"
    assert "failed" in note["content"]


async def test_without_a_delegate_it_does_not_pretend() -> None:
    events = [
        {"type": "session.input_transcript.delta", "delta": "Stuur een mail naar Jan"},
        {"type": "session.delegation.created", "delegation": {"id": "item_3"}},
        ("wait_sent", "session.thinking.append"),
    ]
    conn = _FakeLive(events)
    await _session(conn, delegate=None, robot=_Robot(chunks=0)).run()
    assert "session.commentary.append" not in conn.types()
    assert any("No tools" in e.get("content", "") for e in conn.sent)


def test_a_long_result_is_clipped_to_what_one_append_carries() -> None:
    """500 tokens per append; a rejected append would lose the whole answer."""
    long = "Dit is een zin. " * 400
    out = _clip(long)
    assert len(out) <= 1800
    assert out.endswith(".")
    assert _clip("x" * 5000).endswith("…")
    assert _clip("kort") == "kort"


# ── lifecycle and money ────────────────────────────────────────────────────

async def test_an_idle_session_closes_itself_and_tells_the_server(monkeypatch) -> None:
    """Billed per minute while open: idle must end it, and end it server-side."""
    monkeypatch.setenv("LIVE_SESSION_IDLE_S", "0.2")
    conn = _FakeLive(hang=True)
    sess = _session(conn, robot=_Robot(chunks=0, then_wait=5))
    t0 = time.monotonic()
    await asyncio.wait_for(sess.run(), timeout=5)
    assert "idle" in sess.closed_reason
    assert "session.close" in conn.types()
    assert time.monotonic() - t0 < 3


async def test_a_lookup_in_flight_is_not_idleness(monkeypatch) -> None:
    """The approval gate may take a while to be answered."""
    monkeypatch.setenv("LIVE_SESSION_IDLE_S", "0.1")

    async def slow(text: str) -> str:
        await asyncio.sleep(0.4)
        return "klaar"

    events = [
        {"type": "session.input_transcript.delta", "delta": "zoek iets op"},
        {"type": "session.delegation.created", "delegation": {"id": "item_4"}},
    ]
    conn = _FakeLive(events, hang=True)
    await asyncio.wait_for(_session(conn, delegate=slow, robot=_Robot(chunks=0, then_wait=5)).run(), 5)
    assert "session.commentary.append" in conn.types()


async def test_the_panic_stop_ends_it() -> None:
    conn = _FakeLive(hang=True)
    sess = _session(conn, robot=_Robot(chunks=0, then_wait=5))
    asyncio.get_running_loop().call_later(0.1, sess.request_stop)
    await asyncio.wait_for(sess.run(), timeout=5)
    assert sess.closed_reason == "stopped by owner"
    assert "session.close" in conn.types()


async def test_a_session_that_does_not_start_raises() -> None:
    with pytest.raises(RuntimeError, match="did not start"):
        await _session(_FakeLive(started=False)).run()


async def test_a_refused_command_of_ours_does_not_end_the_conversation() -> None:
    conn = _FakeLive([{"type": "error", "error": {"event_id": "aura_d_7", "message": "stale"}}])
    await _session(conn, robot=_Robot(chunks=0)).run()          # no raise


async def test_a_real_server_error_does() -> None:
    conn = _FakeLive([{"type": "error", "error": {"message": "boom"}}])
    with pytest.raises(RuntimeError, match="boom"):
        await _session(conn, robot=_Robot(chunks=0)).run()


async def test_the_meter_counts_open_time_not_turns(monkeypatch) -> None:
    monkeypatch.setenv("LIVE_SESSION_IDLE_S", "0.2")
    meter = LiveMeter()
    sess = LiveSession(robot=_Robot(chunks=0, then_wait=5), bus=_Bus(),
                       conn_factory=lambda: _FakeLive(hang=True), meter=meter)
    await asyncio.wait_for(sess.run(), 5)
    s = meter.summary()
    assert s["sessions"] == 1 and s["seconds"] > 0
    assert s["estimated_usd"] == round(meter.seconds / 60 * 0.05, 4)
    assert "orchestrator" in s["excludes"], "and it says what it leaves out"


async def test_a_changed_room_is_appended_not_the_whole_prompt(monkeypatch) -> None:
    monkeypatch.setenv("REALTIME_CONTEXT_REFRESH_S", "0.01")
    monkeypatch.setenv("LIVE_SESSION_IDLE_S", "0.6")
    calls = {"n": 0}

    async def room() -> str:
        calls["n"] += 1
        return "Jan staat voor je." if calls["n"] == 1 else "Jan en Elke staan voor je."

    conn = _FakeLive(hang=True)
    await asyncio.wait_for(_session(conn, context_provider=room,
                                    robot=_Robot(chunks=0, then_wait=5)).run(), 5)
    updates = [e for e in conn.sent if e["type"] == "session.instructions.append"]
    assert len(updates) == 1, "the first note was already in the instructions"
    assert "Elke" in updates[0]["content"]


def test_rms_tells_silence_from_voice() -> None:
    assert _rms(_silent()) == 0.0
    assert _rms(_voiced(amp=3000)) == pytest.approx(3000)
    assert _rms(b"") == 0.0


# ── the self-check ─────────────────────────────────────────────────────────

async def test_probe_without_a_key_says_so(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    r = await probe()
    assert r["ok"] is False and "OPENAI_API_KEY" in r["reason"]


async def test_probe_reports_a_working_account(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    conn = _FakeLive()
    r = await probe(conn_factory=lambda: conn)
    assert r["ok"] is True and r["model"] == "gpt-live-1"
    assert "per minute" in r["hint"]
    assert "session.close" in conn.types(), "a probe must not leave a billed session open"


async def test_probe_reports_the_api_reason(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    r = await probe(conn_factory=lambda: _FakeLive(started=False))
    assert r["ok"] is False and "invalid_model" in r["reason"]
