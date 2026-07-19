"""U47: wake-word voice loop — command extraction + follow-up logic."""

from __future__ import annotations

import time

import pytest

from aura_brain.voice_loop import VoiceLoop


def _loop(monkeypatch, wake="richie") -> VoiceLoop:
    monkeypatch.setenv("WAKE_WORD", wake)
    monkeypatch.setenv("VOICE_MODE", "wake_word")
    return VoiceLoop(robot=None, pipeline=None, bus=None, default_wake_word=wake)


def test_wake_word_extracts_following_command(monkeypatch) -> None:
    loop = _loop(monkeypatch)
    assert loop._extract_command("Richie, what's the weather?", in_followup=False) == "what's the weather?"


def test_wake_word_alone_returns_empty(monkeypatch) -> None:
    loop = _loop(monkeypatch)
    assert loop._extract_command("Richie", in_followup=False) == ""


def test_without_wake_word_and_not_followup_is_ignored(monkeypatch) -> None:
    loop = _loop(monkeypatch)
    assert loop._extract_command("play some music", in_followup=False) is None


def test_followup_accepts_without_wake_word(monkeypatch) -> None:
    loop = _loop(monkeypatch)
    assert loop._extract_command("yes please, teal", in_followup=True) == "yes please, teal"


def test_note_spoken_opens_followup_and_guards_echo(monkeypatch) -> None:
    loop = _loop(monkeypatch)
    loop.note_spoken("Hello Jan, good to see you again!")
    now = time.monotonic()
    assert loop._speaking_until > now          # don't listen while speaking
    assert loop._followup_until > loop._speaking_until  # then a follow-up window


def test_local_wake_confirmed_treats_transcript_as_command(monkeypatch) -> None:
    """U128: when the local detector fired, the wake word counts as said even
    if STT dropped it — the whole transcript is the command."""
    loop = _loop(monkeypatch)
    # STT transcribed only the command (no 'Richie'), but wake was confirmed
    # locally → in_followup-style handling returns the text as-is.
    assert loop._extract_command("zet de champions op", in_followup=True) == "zet de champions op"
    # Without a wake (transcript path) the same text is ignored.
    assert loop._extract_command("zet de champions op", in_followup=False) is None


def test_default_build_has_no_local_detector(monkeypatch) -> None:
    """U128: default install keeps the STT-fuzzy path (no local detector)."""
    loop = _loop(monkeypatch)
    assert loop._wake_detector is None


def test_mode_and_wake_read_live_from_env(monkeypatch) -> None:
    loop = _loop(monkeypatch, wake="aura")
    assert loop._mode == "wake_word"
    assert loop._wake == "aura"
    monkeypatch.setenv("VOICE_MODE", "off")
    assert loop._mode == "off"
    monkeypatch.setenv("WAKE_WORD", "Richie")
    assert loop._wake == "richie"  # lower-cased for matching


# ------------------------------------------------------------------
# U148 (voice-brief §6.1): self-hearing guards
# ------------------------------------------------------------------

def test_echo_guard_checks_recent_reply_history(monkeypatch) -> None:
    loop = _loop(monkeypatch)
    loop.note_spoken("Waarom kon de fiets niet rechtop staan? Hij was te moe!")
    loop.note_spoken("Iets heel anders over het weer vandaag.")
    # A transcript matching an EARLIER reply (not just the last) is still echo.
    assert loop._is_echo_of_last_reply("waarom kon de fiets niet rechtop staan hij was moe") is True
    assert loop._is_echo_of_last_reply("zet de verwarming hoger alsjeblieft") is False


def test_self_hearing_cooldown_after_speaking(monkeypatch) -> None:
    monkeypatch.setenv("SELF_HEARING_COOLDOWN_S", "2.0")
    loop = _loop(monkeypatch)
    loop.note_spoken("Hallo daar!")
    # Right after speaking we're still in the speaker-tail cooldown.
    assert loop._in_self_hearing_cooldown() is True
    # Simulate the robot having finished speaking well in the past.
    loop._speaking_until = time.monotonic() - 10.0
    assert loop._in_self_hearing_cooldown() is False


# ------------------------------------------------------------------
# U153: streaming Realtime playback (segments, not a buffered utterance)
# ------------------------------------------------------------------

class _SegRobot:
    """Records streamed segments vs. whole-utterance speak calls."""

    def __init__(self) -> None:
        self.segments: list[str] = []
        self.whole: list[str] = []

    async def speak_segment(self, audio_b64: str) -> bool:
        self.segments.append(audio_b64)
        return True

    async def speak(self, text: str, audio_b64: str | None = None) -> bool:
        self.whole.append(text)
        return True


class _NullBus:
    async def publish(self, *_a, **_k) -> None: ...


async def test_realtime_turn_streams_segments(monkeypatch) -> None:
    monkeypatch.setenv("VOICE_ENGINE", "realtime")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("REALTIME_STREAMING", "true")
    monkeypatch.setenv("REALTIME_SESSION", "false")  # U153 per-turn path
    monkeypatch.setenv("LISTENING_CUE", "false")

    from aura_brain import realtime_voice

    robot = _SegRobot()
    loop = VoiceLoop(robot=robot, pipeline=None, bus=_NullBus(),
                     default_wake_word="richie")

    monkeypatch.setattr(realtime_voice, "wav_to_pcm24k", lambda _w: b"\x00" * 10)

    async def _fake_turn(pcm, *, text, instructions, voice, on_segment=None, **_k):
        # Emit two segments as the reply "generates".
        if on_segment is not None:
            await on_segment(b"\x01" * 8)
            await on_segment(b"\x02" * 8)
        return "Waarom fietst een kip? Om aan de overkant te komen!", b"\x01" * 8 + b"\x02" * 8

    monkeypatch.setattr(realtime_voice, "run_realtime_turn", _fake_turn)

    handled = await loop._realtime_turn(b"fakewav", command="vertel een mop")
    assert handled is True
    # Streamed as two segments; the whole-utterance speak path was NOT used.
    assert len(robot.segments) == 2
    assert robot.whole == []


async def test_realtime_turn_falls_back_to_whole_without_streaming(monkeypatch) -> None:
    monkeypatch.setenv("VOICE_ENGINE", "realtime")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("REALTIME_STREAMING", "false")
    monkeypatch.setenv("REALTIME_SESSION", "false")  # U153 per-turn path
    monkeypatch.setenv("LISTENING_CUE", "false")

    from aura_brain import realtime_voice

    robot = _SegRobot()
    loop = VoiceLoop(robot=robot, pipeline=None, bus=_NullBus(),
                     default_wake_word="richie")
    monkeypatch.setattr(realtime_voice, "wav_to_pcm24k", lambda _w: b"\x00" * 10)

    async def _fake_turn(pcm, *, text, instructions, voice, on_segment=None, **_k):
        assert on_segment is None  # streaming disabled → no segment callback
        return "Hallo!", b"\x09" * 16

    monkeypatch.setattr(realtime_voice, "run_realtime_turn", _fake_turn)

    handled = await loop._realtime_turn(b"fakewav", command="zeg hallo")
    assert handled is True
    assert robot.segments == []
    assert len(robot.whole) == 1  # one whole-utterance speak


# ------------------------------------------------------------------
# U154: conversation-session mode routes through RealtimeSession
# ------------------------------------------------------------------

class _StreamRobot(_SegRobot):
    async def stream_audio(self):  # marks session capability
        yield b"\x00\x00"


async def test_realtime_turn_uses_session_when_enabled(monkeypatch) -> None:
    monkeypatch.setenv("VOICE_ENGINE", "realtime")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("REALTIME_SESSION", "true")
    monkeypatch.setenv("LISTENING_CUE", "false")

    from aura_brain import realtime_session

    runs: list[str] = []

    class _FakeSession:
        def __init__(self, **kw):
            self.turns = 0
            self.closed_reason = ""

        async def run(self, initial_text: str = "") -> None:
            runs.append(initial_text)
            self.turns = 2  # a real back-and-forth happened

    monkeypatch.setattr(realtime_session, "RealtimeSession", _FakeSession)

    robot = _StreamRobot()
    loop = VoiceLoop(robot=robot, pipeline=None, bus=_NullBus(),
                     default_wake_word="richie")
    handled = await loop._realtime_turn(b"fakewav", command="vertel een mop")
    assert handled is True
    assert runs == ["vertel een mop"]  # first command seeds the session


async def test_realtime_session_failure_counts_toward_breaker(monkeypatch) -> None:
    monkeypatch.setenv("VOICE_ENGINE", "realtime")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("REALTIME_SESSION", "true")
    monkeypatch.setenv("LISTENING_CUE", "false")

    from aura_brain import realtime_session

    class _DeadSession:
        def __init__(self, **kw):
            self.turns = 0
            self.closed_reason = ""

        async def run(self, initial_text: str = "") -> None:
            raise RuntimeError("connection refused")

    monkeypatch.setattr(realtime_session, "RealtimeSession", _DeadSession)

    loop = VoiceLoop(robot=_StreamRobot(), pipeline=None, bus=_NullBus(),
                     default_wake_word="richie")
    assert await loop._realtime_turn(b"w", command="mop") is False
    assert await loop._realtime_turn(b"w", command="mop") is False
    assert loop._realtime_broken is True  # two failures trip the breaker
