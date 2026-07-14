"""U51: per-mode behavior profiles — embodiment follows the active persona."""

from __future__ import annotations

from shared_personas import Persona, get_persona_config

from aura_brain.embodiment import embodiment_plan, gesture_for


def _plan(text: str, persona: Persona):
    return embodiment_plan(text, get_persona_config(persona))


def test_silent_desk_is_mute_and_still() -> None:
    speak, gesture, amplitude = _plan("Hello there!", Persona.SILENT_DESK)
    assert speak is False
    assert gesture is None
    assert amplitude == 0.0


def test_work_mode_restrains_to_a_nod() -> None:
    # Content says "wave" (greeting) but work mode only allows nod.
    speak, gesture, amplitude = _plan("Hello! Good morning!", Persona.WORK)
    assert speak is True
    assert gesture == "nod"
    assert amplitude == 0.4


def test_home_mode_allows_tilt_for_questions() -> None:
    speak, gesture, amplitude = _plan("Shall I add that to your list?", Persona.HOME)
    assert speak is True
    assert gesture == "tilt"
    assert amplitude == 0.6


def test_presentation_mode_gestures_expressively() -> None:
    speak, gesture, amplitude = _plan("Great! Amazing results!", Persona.PRESENTATION)
    assert speak is True
    assert gesture == "gesture"
    assert amplitude == 0.8


def test_demo_mode_keeps_the_wave_for_greetings() -> None:
    speak, gesture, amplitude = _plan("Hello everyone!", Persona.DEMO)
    assert speak is True
    assert gesture == "wave"
    assert amplitude == 1.0


def test_no_persona_config_defaults_to_content_gesture() -> None:
    speak, gesture, amplitude = embodiment_plan("Hello!", None)
    assert speak is True
    assert gesture == gesture_for("Hello!")
    assert amplitude == 0.5
