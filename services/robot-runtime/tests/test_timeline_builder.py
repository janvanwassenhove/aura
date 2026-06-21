"""Tests for timeline_builder helpers (spec 004 T014)."""

from __future__ import annotations

from shared_personas import Persona, get_persona_config
from robot_runtime.behavior.timeline_builder import (
    create_idle_timeline,
    create_speaking_timeline,
)


def test_short_text_produces_at_least_one_cue() -> None:
    cfg = get_persona_config(Persona.WORK)
    timeline = create_speaking_timeline("Hello", cfg)
    assert len(timeline.cues) >= 1


def test_long_text_produces_multiple_cues() -> None:
    cfg = get_persona_config(Persona.WORK)
    text = " ".join(["word"] * 40)  # 40 words → at least 5 cues
    timeline = create_speaking_timeline(text, cfg)
    assert len(timeline.cues) >= 5


def test_silent_desk_speaking_timeline_is_empty() -> None:
    cfg = get_persona_config(Persona.SILENT_DESK)
    timeline = create_speaking_timeline("Hello world", cfg)
    assert len(timeline.cues) == 0


def test_cue_amplitude_matches_persona() -> None:
    cfg = get_persona_config(Persona.DEMO)
    timeline = create_speaking_timeline("Hello world", cfg)
    assert len(timeline.cues) >= 1
    for cue in timeline.cues:
        assert cue.amplitude == pytest.approx(1.0)


def test_idle_timeline_has_two_cues_for_work() -> None:
    cfg = get_persona_config(Persona.WORK)
    timeline = create_idle_timeline(cfg)
    assert len(timeline.cues) == 2


def test_silent_desk_idle_timeline_is_empty() -> None:
    cfg = get_persona_config(Persona.SILENT_DESK)
    timeline = create_idle_timeline(cfg)
    assert len(timeline.cues) == 0


def test_idle_timeline_amplitude_is_subdued() -> None:
    cfg = get_persona_config(Persona.DEMO)
    timeline = create_idle_timeline(cfg)
    assert len(timeline.cues) > 0
    for cue in timeline.cues:
        # Subdued: amplitude = persona.amplitude * 0.3
        assert cue.amplitude < cfg.gesture_profile.amplitude


import pytest  # noqa: E402 (keep at bottom so tests above are clear)
