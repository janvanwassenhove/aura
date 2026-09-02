"""U289: the realtime session heard Dutch as Spanish.

Reported with a screenshot: a father talking Dutch to his daughter, and the
transcript came back "Papá, ¿cómo creciste?" — question and answer both in
Spanish.

U287 stopped the PIPELINE path re-guessing the language on every clip. This
path was untouched, and it is the one actually in use (voice_engine=realtime).
Its session config named a transcription MODEL and no language, so the API
detected per utterance — the exact behaviour U287 removed everywhere else.

The instructions in the same config do say "reply in the language the user
speaks", but that is a request about the ANSWER. It does nothing about how the
audio was heard in the first place, which is where this went wrong.
"""

from __future__ import annotations

import pytest
from aura_brain.realtime_session import _transcription_config


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for var in ("STT_LANGUAGE", "ASSISTANT_LANGUAGE", "LANGUAGE_FALLBACK", "LANG", "LC_ALL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("locale.getlocale", lambda *a: (None, None))
    from aura_brain import voice
    voice.set_person_language("")


def test_the_session_is_told_which_language_to_expect(monkeypatch) -> None:
    monkeypatch.setenv("ASSISTANT_LANGUAGE", "nl")
    assert _transcription_config()["language"] == "nl"


def test_it_follows_the_person_he_can_see(monkeypatch) -> None:
    """U288: the daughter's own language (U274) reaches the microphone."""
    from aura_brain import voice

    monkeypatch.setenv("ASSISTANT_LANGUAGE", "auto")
    voice.set_person_language("nl")
    assert _transcription_config()["language"] == "nl"


def test_a_multilingual_household_keeps_free_detection(monkeypatch) -> None:
    """`multi` is the deliberate opt-out (U130's reason); the key is omitted
    entirely rather than set to something meaningless."""
    monkeypatch.setenv("ASSISTANT_LANGUAGE", "multi")
    assert "language" not in _transcription_config()


def test_the_model_is_still_configurable(monkeypatch) -> None:
    monkeypatch.setenv("STT_MODEL", "gpt-4o-transcribe")
    assert _transcription_config()["model"] == "gpt-4o-transcribe"


def test_both_realtime_paths_and_the_pipeline_now_agree(monkeypatch) -> None:
    """Three ways in; one answer. Two of them used to disagree in silence."""
    from aura_brain.voice import _stt_language

    monkeypatch.setenv("ASSISTANT_LANGUAGE", "nl")
    assert _transcription_config()["language"] == _stt_language() == "nl"
