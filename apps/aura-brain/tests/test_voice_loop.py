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
