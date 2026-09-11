"""U324: a confirmed turn goes to the engine the resolver names.

Two findings in one file. The new fourth engine (GPT-Live) is routed; and the
dispatch that existed before it NEVER asked the resolver: `_realtime_turn`
gated on the global VOICE_ENGINE only, so U203's promise — the character
chooses the engine — held in `_engine()`'s tests and nowhere else.
"""

from __future__ import annotations

import os

os.environ.setdefault("LLM_PROVIDER", "echo")

import pytest
from aura_brain.voice_loop import VoiceLoop


class _Robot:
    def __init__(self):
        self.whole, self.segments = [], []

    async def stream_audio(self, raw: bool = False):
        if False:
            yield b""

    async def speak(self, text: str, audio_b64: str | None = None, **kw) -> bool:
        self.whole.append(text)
        return True

    async def speak_segment(self, audio_b64: str) -> bool:
        self.segments.append(audio_b64)
        return True

    async def stop_audio(self) -> dict:
        return {"ok": True}


class _Bus:
    async def publish(self, event):
        pass


def _loop() -> VoiceLoop:
    return VoiceLoop(robot=_Robot(), pipeline=None, bus=_Bus(), default_wake_word="richie")


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("LISTENING_CUE", "false")


async def test_the_live_engine_routes_to_a_live_session(monkeypatch) -> None:
    monkeypatch.setenv("VOICE_ENGINE", "live")
    loop, seen = _loop(), []

    async def fake(wav, command):
        seen.append(command)
        return True

    monkeypatch.setattr(loop, "_live_session_turn", fake)
    assert await loop._speech_turn(b"w", "hallo") is True
    assert seen == ["hallo"]


async def test_the_pipeline_engine_is_not_intercepted(monkeypatch) -> None:
    monkeypatch.setenv("VOICE_ENGINE", "pipeline")
    assert await _loop()._speech_turn(b"w", "hallo") is False


async def test_a_realtime_character_is_honoured_while_the_global_says_pipeline(monkeypatch) -> None:
    """The U203 promise, finally kept by the dispatch and not only the resolver."""
    from aura_brain import realtime_voice

    monkeypatch.setenv("VOICE_ENGINE", "pipeline")
    monkeypatch.setenv("REALTIME_SESSION", "false")
    monkeypatch.setenv("REALTIME_STREAMING", "false")
    monkeypatch.setattr(realtime_voice, "wav_to_pcm24k", lambda wav: b"\x00" * 48)

    async def fake_turn(pcm, **kw):
        return "Hallo!", b"\x09" * 16

    monkeypatch.setattr(realtime_voice, "run_realtime_turn", fake_turn)
    loop = _loop()
    monkeypatch.setattr(loop, "_engine", lambda: "realtime")     # the character's choice
    assert await loop._realtime_turn(b"fakewav", command="zeg hallo") is True
    assert loop._robot.whole == ["Hallo!"]


async def test_a_live_turn_seeds_the_session_with_the_wake_audio(monkeypatch) -> None:
    from aura_brain import live_session, realtime_voice

    monkeypatch.setattr(realtime_voice, "wav_to_pcm24k", lambda wav: b"\x07" * 48)
    made = {}

    class FakeSession:
        def __init__(self, **kw):
            made["kw"] = kw
            self.turns, self.delegations, self.closed_reason = 1, 0, "idle 45s"

        async def run(self, initial_pcm=b"", initial_text=""):
            made["run"] = (initial_pcm, initial_text)

    monkeypatch.setattr(live_session, "LiveSession", FakeSession)
    loop = _loop()
    assert await loop._live_session_turn(b"wav", "wat staat er vandaag") is True
    assert made["run"] == (b"\x07" * 48, "wat staat er vandaag")
    assert made["kw"]["delegate"] == loop._live_delegate
    assert made["kw"]["context_provider"] == loop._room_note
    assert made["kw"]["voice"] == "marin"


async def test_a_failing_live_session_falls_back_and_two_trip_the_breaker(monkeypatch) -> None:
    from aura_brain import live_session

    class Boom:
        def __init__(self, **kw):
            self.turns, self.delegations, self.closed_reason = 0, 0, ""

        async def run(self, **kw):
            raise RuntimeError("invalid_model")

    monkeypatch.setattr(live_session, "LiveSession", Boom)
    loop = _loop()
    assert await loop._live_session_turn(b"", "a") is False
    assert await loop._live_session_turn(b"", "a") is False
    assert loop._live_broken is True
    assert await loop._live_session_turn(b"", "a") is False     # stays on the pipeline


async def test_the_delegate_runs_the_orchestrator_without_announcing() -> None:
    """Tools and the approval gate as always — but the LIVE voice speaks it."""
    calls = []

    class Pipeline:
        async def orchestrate(self, text, session_id, announce=True, from_user=True):
            calls.append((text, announce, from_user))
            return "resultaat"

    loop = VoiceLoop(robot=_Robot(), pipeline=Pipeline(), bus=_Bus(), default_wake_word="richie")
    assert await loop._live_delegate("wat is het weer") == "resultaat"
    assert calls == [("wat is het weer", False, True)]
