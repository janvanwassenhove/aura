"""U203: the voice engine follows the active persona.

The owner wanted voice (with tools) by default and realtime on demand — a
"presentation" persona that chats along fluidly, giving up tools willingly.
So the engine is not one global switch: an active character can override it,
and the everyday default stays pipeline (voice + skills).
"""

from __future__ import annotations

from aura_brain.characters import CharacterPersona, CharacterStore
from aura_brain.voice_loop import VoiceLoop


class _Manager:
    def __init__(self, character=None) -> None:
        self.character = character


def _loop(character=None) -> VoiceLoop:
    return VoiceLoop(robot=object(), pipeline=object(), bus=object(),
                     manager=_Manager(character))


def test_default_is_pipeline_so_tools_survive(monkeypatch) -> None:
    monkeypatch.delenv("VOICE_ENGINE", raising=False)
    assert _loop().engine_for_test() == "pipeline"


def test_global_env_still_switches_everything(monkeypatch) -> None:
    monkeypatch.setenv("VOICE_ENGINE", "realtime")
    assert _loop().engine_for_test() == "realtime"


def test_active_character_overrides_the_global(monkeypatch) -> None:
    """A presentation persona goes realtime even while the global stays pipeline."""
    monkeypatch.setenv("VOICE_ENGINE", "pipeline")
    char = CharacterPersona(id="coach", voice_engine="realtime")
    assert _loop(char).engine_for_test() == "realtime"


def test_a_character_can_force_pipeline_against_a_realtime_global(monkeypatch) -> None:
    monkeypatch.setenv("VOICE_ENGINE", "realtime")
    char = CharacterPersona(id="butler", voice_engine="pipeline")
    assert _loop(char).engine_for_test() == "pipeline"


def test_a_character_without_a_preference_inherits(monkeypatch) -> None:
    monkeypatch.setenv("VOICE_ENGINE", "realtime")
    char = CharacterPersona(id="plain", voice_engine="")   # inherit
    assert _loop(char).engine_for_test() == "realtime"


def test_the_shipped_presentation_persona_uses_realtime(tmp_path) -> None:
    """workshop_coach ships as the chat-along presentation persona."""
    store = CharacterStore(str(tmp_path))
    coach = store.get("workshop_coach")
    assert coach is not None
    assert coach.voice_engine == "realtime"


def test_an_invalid_engine_is_refused_not_stored(tmp_path) -> None:
    """A bad value would silently break every turn — ignore it."""
    store = CharacterStore(str(tmp_path))
    store.update("friendly_assistant", {"voice_engine": "nonsense"})
    assert store.get("friendly_assistant").voice_engine == ""
    store.update("friendly_assistant", {"voice_engine": "realtime"})
    assert store.get("friendly_assistant").voice_engine == "realtime"
