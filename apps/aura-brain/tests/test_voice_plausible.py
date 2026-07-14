"""U49: voice-loop hallucination filter."""

from __future__ import annotations

import pytest

from aura_brain.voice_loop import is_plausible_command


@pytest.fixture(autouse=True)
def _lang(monkeypatch):
    monkeypatch.setenv("ASSISTANT_LANGUAGE", "nl")


def test_rejects_cyrillic_hallucination() -> None:
    assert is_plausible_command("Бурын") is False


def test_rejects_known_hallucinations() -> None:
    for h in ("Thank you", "Thanks for watching", "...", "you", "字幕"):
        assert is_plausible_command(h) is False


def test_rejects_too_short() -> None:
    assert is_plausible_command("hi") is False
    assert is_plausible_command("") is False


def test_accepts_real_dutch_command() -> None:
    assert is_plausible_command("vertel een mop") is True
    assert is_plausible_command("wat staat er in mijn agenda?") is True


def test_accepts_real_english() -> None:
    assert is_plausible_command("play some music") is True


def test_accented_latin_is_fine() -> None:
    assert is_plausible_command("qué hora es") is True
