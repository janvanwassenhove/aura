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


def test_mode_and_wake_read_live_from_env(monkeypatch) -> None:
    loop = _loop(monkeypatch, wake="aura")
    assert loop._mode == "wake_word"
    assert loop._wake == "aura"
    monkeypatch.setenv("VOICE_MODE", "off")
    assert loop._mode == "off"
    monkeypatch.setenv("WAKE_WORD", "Richie")
    assert loop._wake == "richie"  # lower-cased for matching
