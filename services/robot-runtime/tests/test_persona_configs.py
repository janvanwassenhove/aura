"""Tests for persona configurations (spec 004 T015)."""

from __future__ import annotations

from shared_personas import Persona, get_persona_config
from shared_personas.configs import PERSONA_CONFIGS


def test_all_5_personas_defined() -> None:
    assert set(PERSONA_CONFIGS.keys()) == {
        Persona.WORK,
        Persona.HOME,
        Persona.PRESENTATION,
        Persona.SILENT_DESK,
        Persona.DEMO,
    }


def test_silent_desk_no_motion_ids() -> None:
    cfg = get_persona_config(Persona.SILENT_DESK)
    assert cfg.gesture_profile.motion_ids == []


def test_silent_desk_amplitude_zero() -> None:
    cfg = get_persona_config(Persona.SILENT_DESK)
    assert cfg.gesture_profile.amplitude == 0.0


def test_demo_has_highest_amplitude() -> None:
    demo_cfg = get_persona_config(Persona.DEMO)
    for persona in (Persona.WORK, Persona.HOME, Persona.PRESENTATION):
        other_cfg = get_persona_config(persona)
        assert demo_cfg.gesture_profile.amplitude >= other_cfg.gesture_profile.amplitude


def test_all_personas_have_voice_style() -> None:
    for persona, cfg in PERSONA_CONFIGS.items():
        assert cfg.voice_style, f"Persona {persona} missing voice_style"


def test_get_persona_config_returns_correct_type() -> None:
    from shared_personas.models import PersonaConfig
    cfg = get_persona_config(Persona.WORK)
    assert isinstance(cfg, PersonaConfig)
