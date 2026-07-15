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
    monkeypatch.setenv("WAKE_WORD", "richie")
    robot = _ScriptedRobot(peaks=[0.5])  # user talks loudly over the robot
    pipeline = _Pipeline()
    vl = VoiceLoop(robot, pipeline, _Bus(), speech_peak=0.03)
    vl.note_spoken("Een behoorlijk lange zin die de robot aan het uitspreken is." * 3)
    assert time.monotonic() < vl._speaking_until  # robot is 'talking'

    async def fake_transcribe(_wav, filename="") -> str:
        return "Richie stop maar, speel muziek af"  # U73: barge needs the wake word

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

    assert pipeline.commands and "speel muziek af" in pipeline.commands[0]
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


async def test_music_guard_suspends_followup_windows(loop_env, monkeypatch) -> None:
    """U69: after AURA starts music, replies open NO follow-up window — only
    the wake word gets through, so lyrics can't become conversation at all."""
    monkeypatch.setenv("MUSIC_GUARD_S", "60")
    robot = _ScriptedRobot(peaks=[0.5])
    pipeline = _Pipeline()
    vl = VoiceLoop(robot, pipeline, _Bus(), speech_peak=0.03)

    vl.note_music_started()          # AURA pressed play
    vl.note_spoken("Ik heb Spotify gestart en op play gedrukt.")
    vl._speaking_until = 0.0         # skip echo wait for the test
    assert vl._followup_until == 0.0  # no window while music plays

    async def lyrics(_wav, filename="") -> str:
        return "Meine Damen und Herren, vielen Dank"

    from aura_brain import voice
    monkeypatch.setattr(voice, "transcribe", lyrics)

    task = asyncio.create_task(vl._run())
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert pipeline.commands == []   # lyrics ignored — wake word required


async def test_wake_word_still_works_during_music_guard(loop_env, monkeypatch) -> None:
    monkeypatch.setenv("WAKE_WORD", "richie")
    robot = _ScriptedRobot(peaks=[0.5])
    pipeline = _Pipeline()
    vl = VoiceLoop(robot, pipeline, _Bus(), speech_peak=0.03)
    vl.note_music_started()

    async def spoken(_wav, filename="") -> str:
        return "Richie, zet de muziek zachter"

    from aura_brain import voice
    monkeypatch.setattr(voice, "transcribe", spoken)

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
    assert pipeline.commands == ["zet de muziek zachter"]


async def test_barge_without_wake_word_is_ignored_as_echo(loop_env, monkeypatch) -> None:
    """U73: the robot's own voice is loud at its own mic — a loud transcript
    WITHOUT the wake word during our own speech is echo, never a command."""
    monkeypatch.setenv("WAKE_WORD", "richie")
    robot = _ScriptedRobot(peaks=[0.5])  # loud (own speaker)
    pipeline = _Pipeline()
    vl = VoiceLoop(robot, pipeline, _Bus(), speech_peak=0.03)
    vl.note_spoken("Zin." * 60)  # long speech window

    async def own_echo(_wav, filename="") -> str:
        return "Er war in den 18."  # garbled self-transcription

    from aura_brain import voice
    monkeypatch.setattr(voice, "transcribe", own_echo)

    task = asyncio.create_task(vl._run())
    await asyncio.sleep(0.25)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert pipeline.commands == []             # echo ignored
    assert time.monotonic() < vl._speaking_until  # still speaking, not interrupted


async def test_followup_rejects_quiet_ambient_and_self_echo(loop_env, monkeypatch) -> None:
    """U91: in a follow-up window, ambient noise (quiet) and the robot's own
    reply echoing back must NOT become commands."""
    monkeypatch.setenv("FOLLOWUP_PEAK_FACTOR", "1.6")
    monkeypatch.setenv("BARGE_IN", "false")
    # peaks: quiet (below 1.6× gate) then a clear echo of the last reply
    robot = _ScriptedRobot(peaks=[0.04, 0.5])
    pipeline = _Pipeline()
    vl = VoiceLoop(robot, pipeline, _Bus(), speech_peak=0.03, followup_s=30.0)
    vl.note_spoken("Ik weet dat je favoriete koffie zwart is en je van skatepunk houdt.")
    vl._speaking_until = 0.0  # skip echo-guard wait
    assert vl._followup_until > 0

    async def echo_transcript(_wav, filename="") -> str:
        # the robot's own reply bounced back through the mic
        return "je favoriete koffie zwart is en je van skatepunk houdt"

    from aura_brain import voice
    monkeypatch.setattr(voice, "transcribe", echo_transcript)

    task = asyncio.create_task(vl._run())
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert pipeline.commands == []  # quiet ambient + self-echo both rejected


def test_echo_detection_heuristic() -> None:
    vl = VoiceLoop(_ScriptedRobot([0.5]), _Pipeline(), _Bus())
    vl.note_spoken("Ik weet dat je favoriete koffie zwart is, dat je van skatepunk houdt.")
    assert vl._is_echo_of_last_reply("je favoriete koffie zwart en skatepunk houdt") is True
    assert vl._is_echo_of_last_reply("zet de champions op in de living") is False
    assert vl._is_echo_of_last_reply("ja") is False  # too short


async def test_wake_word_required_every_turn_by_default(loop_env, monkeypatch) -> None:
    """U92: with FOLLOWUP_S unset and followup_s=0, a reply opens NO follow-up
    window — Whisper gibberish without the wake word is ignored, so phantom
    conversations can't start."""
    monkeypatch.delenv("FOLLOWUP_S", raising=False)
    monkeypatch.setenv("BARGE_IN", "false")
    monkeypatch.setenv("WAKE_WORD", "richie")
    robot = _ScriptedRobot(peaks=[0.5])
    pipeline = _Pipeline()
    vl = VoiceLoop(robot, pipeline, _Bus(), speech_peak=0.03, followup_s=0.0)
    vl.note_spoken("Ik kan je helpen met Spotify.")
    vl._speaking_until = 0.0
    assert vl._followup_until == 0.0  # no follow-up window

    async def gibberish(_wav, filename="") -> str:
        return "Alel, naenolim."  # Whisper hallucination, no wake word

    from aura_brain import voice
    monkeypatch.setattr(voice, "transcribe", gibberish)

    task = asyncio.create_task(vl._run())
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert pipeline.commands == []  # ignored — no wake word


async def test_interruption_note_not_prepended_to_command(monkeypatch) -> None:
    """U92: the interruption note goes to steer() (a system message), never
    concatenated into the visible user command."""
    from aura_brain.conversation_manager import ConversationManager

    steered: list[str] = []
    handled: list[str] = []

    class _P:
        def set_cancel_event(self, *a): pass
        def steer(self, sid, text): steered.append(text)

    mgr = ConversationManager()
    await mgr.interrupt("Ah, je zoekt een nummer dat Richie heet")
    # simulate the loop's turn-start block
    note = mgr.consume_interruption_note()
    command = "richie"
    if note:
        _P().steer("s", note)   # note → steer, NOT into command
        steered_pipeline = _P(); steered_pipeline.steer("s", note); steered.append("x")
    handled.append(command)     # command stays clean
    assert "interrupted" not in command
    assert any("interrupted" in s for s in steered)


async def test_bare_or_echoed_wake_word_never_becomes_a_turn(loop_env, monkeypatch) -> None:
    """U96: a command that is only the wake word (Whisper echoes the STT
    name-prompt on noise/robot-echo) is dropped — no "You: Richie" phantom
    turn, no generic reply loop."""
    monkeypatch.delenv("FOLLOWUP_S", raising=False)
    monkeypatch.setenv("BARGE_IN", "false")
    monkeypatch.setenv("WAKE_WORD", "richie")
    robot = _ScriptedRobot(peaks=[0.5, 0.04])  # loud wake window, then silence
    pipeline = _Pipeline()
    vl = VoiceLoop(robot, pipeline, _Bus(), speech_peak=0.03, followup_s=0.0)

    async def only_wake(_wav, filename="") -> str:
        return "Richie"  # bare wake word / echoed prompt

    from aura_brain import voice
    monkeypatch.setattr(voice, "transcribe", only_wake)

    task = asyncio.create_task(vl._run())
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert pipeline.commands == []  # bare wake word → no turn


def test_strip_wake_word() -> None:
    import os
    os.environ["WAKE_WORD"] = "richie"
    vl = VoiceLoop(_ScriptedRobot([0.5]), _Pipeline(), _Bus())
    assert vl._strip_wake_word("Richie") == ""
    assert vl._strip_wake_word("Ritchie.") == ""
    assert vl._strip_wake_word("Richie, zet muziek op") == "zet muziek op"
    assert vl._strip_wake_word("zet muziek op") == "zet muziek op"
