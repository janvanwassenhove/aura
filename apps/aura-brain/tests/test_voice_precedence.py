"""U273: three screens each offer a "Voice"; one of them decides.

Asked as "the default voice in settings, whats difference in between the one
selected in robot? how are they used? can we make it more clearer".

The honest answer was uncomfortable: the persona's own voice wins, every
built-in character ships with one (Friendly Assistant is `coral`), so the
Settings dropdown reading `alloy` had never once been used — and its own
caption said only "modes can override it in Modes", naming one of the two
things that outrank it and omitting the one that actually decides.

Worse, the mode voice could not be found either. Modes writes
TTS_VOICE_<MODE>; resolve_voice read TTS_VOICE_<PERSONA>. Those agree only
while a mode still uses the persona named after it, so giving Home the
"Friendly Assistant" persona silently orphaned the voice set in Modes.
"""

from __future__ import annotations

import pytest
from aura_brain.voice import explain_voice, resolve_voice


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in ("TTS_VOICE", "TTS_VOICE_HOME", "TTS_VOICE_WORK",
                "TTS_VOICE_PRESENTATION", "TTS_VOICE_FRIENDLY ASSISTANT"):
        monkeypatch.delenv(var, raising=False)


def test_the_personas_own_voice_wins(monkeypatch):
    monkeypatch.setenv("TTS_VOICE", "alloy")
    monkeypatch.setenv("TTS_VOICE_HOME", "nova")
    v, why = explain_voice(persona="Friendly Assistant", mode="home",
                           character_voice="coral")
    assert v == "coral"
    assert "persona" in why


def test_the_mode_voice_is_found_even_when_the_persona_was_renamed(monkeypatch):
    """The reported break, as a test. Modes writes TTS_VOICE_HOME; the lookup
    used the persona's name, so a mode with a custom persona lost its voice."""
    monkeypatch.setenv("TTS_VOICE", "alloy")
    monkeypatch.setenv("TTS_VOICE_HOME", "nova")
    v, why = explain_voice(persona="Friendly Assistant", mode="home")
    assert v == "nova", "the voice set in Modes must survive a renamed persona"
    assert "home" in why


def test_settings_is_the_fallback_not_the_rule(monkeypatch):
    monkeypatch.setenv("TTS_VOICE", "sage")
    v, why = explain_voice(persona="Friendly Assistant", mode="home")
    assert v == "sage"
    assert "Settings" in why


def test_nothing_configured_still_speaks(monkeypatch):
    v, why = explain_voice()
    assert v == "alloy"
    assert "built-in" in why


def test_an_unknown_voice_name_is_ignored_rather_than_spoken(monkeypatch):
    """A hand-edited env or a stale persona must not silence him."""
    monkeypatch.setenv("TTS_VOICE", "alloy")
    assert resolve_voice(character_voice="not-a-voice") == "alloy"
    monkeypatch.setenv("TTS_VOICE", "also-not-a-voice")
    assert resolve_voice() == "alloy"


def test_the_old_positional_call_still_means_persona(monkeypatch):
    """`resolve_voice(persona)` is called positionally in the speak path."""
    monkeypatch.setenv("TTS_VOICE_WORK", "onyx")
    assert resolve_voice("work") == "onyx"
