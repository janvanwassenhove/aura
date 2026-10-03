"""Tests for shared-personas configs."""

from shared_personas import Persona, get_persona_config


def test_all_personas_have_configs():
    for p in Persona:
        cfg = get_persona_config(p)
        assert cfg.name == p


def test_silent_desk_has_zero_amplitude():
    cfg = get_persona_config(Persona.SILENT_DESK)
    assert cfg.gesture_profile.amplitude == 0.0
    assert cfg.gesture_profile.motion_ids == []


def test_demo_has_max_amplitude():
    cfg = get_persona_config(Persona.DEMO)
    assert cfg.gesture_profile.amplitude == 1.0


def test_get_persona_config_from_string():
    cfg = get_persona_config("work")
    assert cfg.name == Persona.WORK


def test_invalid_persona_raises():
    import pytest
    with pytest.raises(ValueError):
        get_persona_config("nonexistent")


def test_the_stand_persona_keeps_the_owner_private():
    """U397: at a stand everyone is a stranger."""
    cfg = get_persona_config("stand")
    prompt = cfg.system_prompt_template.lower()
    assert "stranger" in prompt
    assert "never" in prompt and "owner" in prompt
    assert "{context}" in cfg.system_prompt_template
