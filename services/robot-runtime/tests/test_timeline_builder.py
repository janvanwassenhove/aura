"""Tests for timeline_builder helpers (spec 004 T014)."""

from __future__ import annotations

from robot_runtime.behavior.timeline_builder import (
    create_idle_timeline,
    create_speaking_timeline,
)
from shared_personas import Persona, get_persona_config


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


def test_idle_timeline_fidgets_or_looks_around(monkeypatch) -> None:
    import robot_runtime.behavior.timeline_builder as tb

    cfg = get_persona_config(Persona.WORK)
    # Deterministic branches: fidget (2 cues) vs look-around (1 cue, U36d).
    monkeypatch.setattr(tb.random, "random", lambda: 0.9)
    fidget = create_idle_timeline(cfg)
    assert len(fidget.cues) == 2
    monkeypatch.setattr(tb.random, "random", lambda: 0.1)
    curious = create_idle_timeline(cfg)
    assert [c.motion_id for c in curious.cues] == ["look_around"]


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


# ── U408: spread over the line he is actually saying ────────────────────────

def _at(timeline) -> list[int]:
    """When each cue starts, from the start of the line. A cue's offset is its
    wait from the cue before it — the MotionCue contract."""
    out, t = [], 0
    for cue in timeline.cues:
        t += cue.offset_ms
        out.append(t)
    return out


def test_the_gestures_are_spread_over_the_line_not_bunched_at_its_start() -> None:
    cfg = get_persona_config(Persona.WORK)
    at = _at(create_speaking_timeline(" ".join(["woord"] * 48), cfg, duration_ms=12_000))
    assert len(at) >= 4
    assert at[0] < 3_000, "the first comes early in the line"
    assert at[-1] > 6_000, "and the last in its second half"


def test_no_gesture_starts_too_late_to_finish_inside_the_line() -> None:
    cfg = get_persona_config(Persona.DEMO)
    for _ in range(20):
        at = _at(create_speaking_timeline(" ".join(["woord"] * 40), cfg, duration_ms=4_000))
        assert at and max(at) <= 4_000 - 600


def test_without_words_the_length_of_the_line_decides() -> None:
    """A line the laptop plays reaches the robot as audio only."""
    cfg = get_persona_config(Persona.WORK)
    assert len(create_speaking_timeline("", cfg, duration_ms=8_000).cues) >= 2
