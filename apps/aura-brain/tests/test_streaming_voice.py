"""U54: streamed TTS chunks + barge-in while the robot is speaking."""

from __future__ import annotations

import asyncio
import time

import pytest

from aura_brain.streaming import split_speech_chunks, stream_speech
from aura_brain.voice_loop import VoiceLoop


# ── chunker ──────────────────────────────────────────────────────────

def test_short_text_is_one_chunk() -> None:
    assert split_speech_chunks("Hallo daar!") == ["Hallo daar!"]


def test_sentences_merge_to_min_chars() -> None:
    text = ("Dit is zin een die best wel lang is en op zichzelf staat. Kort. "
            "En dan nog een derde zin die ook een behoorlijke lengte heeft, zeker weten.")
    chunks = split_speech_chunks(text, min_chars=60)
    assert len(chunks) == 2
    assert chunks[0].startswith("Dit is zin een")
    assert "".join(chunks).replace(" ", "") == text.replace(" ", "")


def test_empty_text_yields_nothing() -> None:
    assert split_speech_chunks("") == []


def test_chunk_cap_absorbs_tail() -> None:
    text = " ".join(f"Zin nummer {i} met genoeg lengte om een chunk te zijn, ja echt waar." for i in range(12))
    chunks = split_speech_chunks(text, min_chars=10, max_chunks=6)
    assert len(chunks) == 6
    assert "nummer 11" in chunks[-1]


# ── pipelined speaking ───────────────────────────────────────────────

async def test_stream_speech_pipelines_synthesis_ahead_of_playback() -> None:
    events: list[str] = []

    async def synth(chunk: str) -> str:
        events.append(f"synth:{chunk[:6]}")
        await asyncio.sleep(0.01)
        return f"b64({chunk[:6]})"

    async def speak(chunk: str, audio: str) -> None:
        events.append(f"speak:{chunk[:6]}")
        await asyncio.sleep(0.02)

    text = ("Eerste zin die lang genoeg is om een eigen chunk te vormen hier. "
            "Tweede zin die ook makkelijk lang genoeg is voor een eigen chunk ja.")
    n = await stream_speech(text, synth, speak, min_chars=40)
    assert n == 2
    # Chunk 2's synthesis starts BEFORE chunk 1 finished speaking.
    assert events.index("synth:Tweede") < events.index("speak:Tweede")
    assert events[0] == "synth:Eerste"


async def test_stream_speech_empty_is_noop() -> None:
    async def boom(*_a):  # pragma: no cover - must not be called
        raise AssertionError
    assert await stream_speech("", boom, boom) == 0


# ── barge-in ─────────────────────────────────────────────────────────

class _ScriptedRobot:
    """listen() returns scripted (wav, peak) tuples."""

    def __init__(self, peaks: list[float]) -> None:
        self._peaks = peaks
        self.calls = 0

    async def listen(self, duration_s: float) -> tuple[bytes, float]:
        await asyncio.sleep(0.001)  # yield — a sync-completing fake starves the test
        peak = self._peaks[min(self.calls, len(self._peaks) - 1)]
        self.calls += 1
        return b"wav", peak


class _Pipeline:
    def __init__(self) -> None:
        self.commands: list[str] = []

    async def orchestrate(self, text: str, session_id: str) -> str:
        self.commands.append(text)
        return "ok"


class _Bus:
    async def publish(self, _event) -> None:
        pass


@pytest.fixture()
def loop_env(monkeypatch):
    monkeypatch.setenv("VOICE_MODE", "wake_word")
    monkeypatch.setenv("BARGE_IN", "true")
    monkeypatch.setenv("BARGE_IN_FACTOR", "2.5")
    monkeypatch.setenv("ASSISTANT_LANGUAGE", "nl")


async def test_barge_in_interrupts_speaking_window(loop_env, monkeypatch) -> None:
    robot = _ScriptedRobot(peaks=[0.5])  # user talks loudly over the robot
    pipeline = _Pipeline()
    vl = VoiceLoop(robot, pipeline, _Bus(), speech_peak=0.03)
    vl.note_spoken("Een behoorlijk lange zin die de robot aan het uitspreken is." * 3)
    assert time.monotonic() < vl._speaking_until  # robot is 'talking'

    async def fake_transcribe(_wav, filename="") -> str:
        return "stop maar, speel muziek af"

    from aura_brain import voice
    monkeypatch.setattr(voice, "transcribe", fake_transcribe)

    task = asyncio.create_task(vl._run())
    try:
        for _ in range(200):
            if pipeline.commands:
                break
            await asyncio.sleep(0.01)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert pipeline.commands == ["stop maar, speel muziek af"]
    assert vl._speaking_until == 0.0  # wait was cut by the barge-in


async def test_soft_echo_does_not_barge_in(loop_env) -> None:
    # Peak above the normal gate but below the barge factor → ignored (echo).
    robot = _ScriptedRobot(peaks=[0.05])
    pipeline = _Pipeline()
    vl = VoiceLoop(robot, pipeline, _Bus(), speech_peak=0.03)
    vl.note_spoken("Zin." * 40)

    task = asyncio.create_task(vl._run())
    await asyncio.sleep(0.15)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert pipeline.commands == []
    assert time.monotonic() < vl._speaking_until  # still in the speaking window


async def test_followup_chain_caps_self_conversation(loop_env, monkeypatch) -> None:
    """U67: music/lyrics near the mic must not talk to Richie forever —
    after FOLLOWUP_CHAIN_MAX wake-word-less turns the wake word is required."""
    monkeypatch.setenv("FOLLOWUP_CHAIN_MAX", "2")
    monkeypatch.setenv("BARGE_IN", "false")
    robot = _ScriptedRobot(peaks=[0.5])  # 'speech' every window (music playing)
    pipeline = _Pipeline()
    vl = VoiceLoop(robot, pipeline, _Bus(), speech_peak=0.03, followup_s=30.0)

    async def fake_transcribe(_wav, filename="") -> str:
        return "kommen von Nordmeer über"  # lyrics, no wake word

    from aura_brain import voice
    monkeypatch.setattr(voice, "transcribe", fake_transcribe)

    # Simulate the conversation flow: reply → follow-up window → lyric turn.
    vl._speaking_until = 0.0
    vl.note_spoken("x")            # turn 1 reply → window opens (chain 0)
    assert vl._followup_until > 0

    task = asyncio.create_task(vl._run())
    try:
        for _ in range(300):
            if len(pipeline.commands) >= 1:
                break
            await asyncio.sleep(0.01)
        vl._speaking_until = 0.0   # skip echo-guard wait in the test
        vl.note_spoken("y")        # turn 2 reply (chain 1) → window still opens
        vl._speaking_until = 0.0
        for _ in range(300):
            if len(pipeline.commands) >= 2:
                break
            await asyncio.sleep(0.01)
        vl._speaking_until = 0.0
        vl.note_spoken("z")        # chain hit the cap → NO new window
        vl._speaking_until = 0.0
        assert vl._followup_until == 0.0
        # More lyrics arrive but there's no follow-up window and no wake word:
        before = len(pipeline.commands)
        await asyncio.sleep(0.2)
        assert len(pipeline.commands) == before  # the self-conversation stopped
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
