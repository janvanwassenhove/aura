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


# ------------------------------------------------------------------
# U135: hallucination gate on the auto-detect path (verbose_json signals)
# ------------------------------------------------------------------

class _Seg:
    def __init__(self, no_speech_prob=0.1, avg_logprob=-0.3):
        self.no_speech_prob = no_speech_prob
        self.avg_logprob = avg_logprob


class _Res:
    def __init__(self, text, language="dutch", segments=None):
        self.text = text
        self.language = language
        self.segments = segments if segments is not None else [_Seg()]


def test_rejects_language_outside_household(monkeypatch) -> None:
    from aura_brain.voice import _reject_reason

    monkeypatch.setenv("VOICE_LANGUAGES", "nl,en,fr,de")
    # The exact hallucinations seen live: Portuguese + Turkish out of noise.
    assert _reject_reason(_Res("Não me inscreva que", "portuguese"))
    assert _reject_reason(_Res("İyi günler.", "turkish"))
    # Household languages pass.
    assert _reject_reason(_Res("Het is bijna donker.", "dutch")) is None
    assert _reject_reason(_Res("What time is it?", "english")) is None
    assert _reject_reason(_Res("Guten Morgen.", "german")) is None


def test_rejects_silence_signatures(monkeypatch) -> None:
    from aura_brain.voice import _reject_reason

    monkeypatch.setenv("VOICE_LANGUAGES", "nl,en,fr,de")
    # Whisper "hearing" speech in silence → high no_speech_prob.
    assert _reject_reason(_Res("Koffoló bícs", "dutch", [_Seg(no_speech_prob=0.9)]))
    # Very low confidence → gibberish.
    assert _reject_reason(_Res("bla bla", "dutch", [_Seg(avg_logprob=-2.0)]))
    assert _reject_reason(_Res("", "dutch")) == "empty"


def test_keeps_confident_household_speech(monkeypatch) -> None:
    from aura_brain.voice import _reject_reason

    monkeypatch.setenv("VOICE_LANGUAGES", "nl,en,fr,de")
    good = _Res("Richie, zet muziek op.", "dutch", [_Seg(no_speech_prob=0.05, avg_logprob=-0.2)])
    assert _reject_reason(good) is None
