"""U349: one spoken line, several personas — the inline `[persona:id]` marker.

The splitter is pure text→segments. Who those persona ids actually ARE is the
brain's business (characters live there); this layer only has to cut the line
up correctly and never let a marker reach the speaker.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from shared_schemas.presentation import (
    Beat,
    VoiceSegment,
    persona_marker_problem,
    split_persona_segments,
)


def _pairs(text: str, default: str = "") -> list[tuple[str, str]]:
    return [(s.text, s.persona) for s in split_persona_segments(text, default)]


def test_a_line_without_markers_is_one_segment_in_the_beat_persona() -> None:
    assert _pairs("Hallo zaal.") == [("Hallo zaal.", "")]
    assert _pairs("Hallo zaal.", "dry_tech_butler") == [
        ("Hallo zaal.", "dry_tech_butler")]


def test_a_marker_switches_persona_from_that_point_on() -> None:
    assert _pairs("Eerst ik. [persona:kids_companion]En nu ik!") == [
        ("Eerst ik.", ""), ("En nu ik!", "kids_companion")]


def test_a_closing_marker_returns_to_the_beat_persona() -> None:
    line = "Netjes. [persona:kids_companion]Joepie![persona] Netjes."
    assert _pairs(line, "dry_tech_butler") == [
        ("Netjes.", "dry_tech_butler"),
        ("Joepie!", "kids_companion"),
        ("Netjes.", "dry_tech_butler"),
    ]
    # `[/persona]` is the same thing — people reach for the closing-tag shape.
    assert _pairs("a[persona:x]b[/persona]c") == [
        ("a", ""), ("b", "x"), ("c", "")]


def test_the_marker_itself_is_never_spoken() -> None:
    for segment in split_persona_segments("a [persona:x] b [persona] c"):
        assert "persona" not in segment.text
        assert "[" not in segment.text and "]" not in segment.text


def test_a_line_may_open_on_another_persona() -> None:
    assert _pairs("[persona:kids_companion]Hoi hoi!", "butler") == [
        ("Hoi hoi!", "kids_companion")]


def test_neighbouring_segments_of_the_same_persona_merge() -> None:
    """Two markers in a row for one persona is one TTS call, not two — and one
    uninterrupted delivery rather than an audible seam in the middle."""
    assert _pairs("[persona:x]A.[persona:x]B.") == [("A. B.", "x")]
    assert _pairs("A.[persona]B.") == [("A. B.", "")]


def test_empty_and_whitespace_only_segments_disappear() -> None:
    assert split_persona_segments("") == []
    assert split_persona_segments("   ") == []
    assert _pairs("[persona:x]   [persona]Hallo") == [("Hallo", "")]


def test_spaces_inside_a_marker_are_tolerated() -> None:
    assert _pairs("a[ persona : kids_companion ]b") == [
        ("a", ""), ("b", "kids_companion")]


def test_case_does_not_matter_for_the_marker_keyword() -> None:
    assert _pairs("a[PERSONA:Kids]b") == [("a", ""), ("b", "Kids")]


# --------------------------------------------------------------------------- #
# Malformed markers are caught at authoring time, not read out on stage
# --------------------------------------------------------------------------- #

def test_a_well_formed_line_reports_no_problem() -> None:
    assert persona_marker_problem("plain text") == ""
    assert persona_marker_problem("a[persona:x]b[persona]c") == ""
    assert persona_marker_problem("a[/persona]b") == ""
    # Prose that merely contains the word is not a marker.
    assert persona_marker_problem("we praten over [de persona van de robot]") == ""


def test_a_marker_without_an_id_is_a_problem() -> None:
    assert persona_marker_problem("a[persona:]b")


def test_a_closing_marker_with_an_id_is_a_problem() -> None:
    assert persona_marker_problem("a[/persona:kids]b")


def test_an_id_with_a_space_in_it_is_a_problem() -> None:
    assert persona_marker_problem("a[persona:kids companion]b")


def test_the_problem_names_the_marker_it_tripped_on() -> None:
    problem = persona_marker_problem("a[persona:]b")
    assert "[persona:]" in problem


# --------------------------------------------------------------------------- #
# The beat carries a persona, and validates the markers in its own text
# --------------------------------------------------------------------------- #

def test_a_beat_carries_a_persona_and_defaults_to_none() -> None:
    assert Beat(id="a", text="hi").persona == ""
    assert Beat(id="b", text="hi", persona="dry_tech_butler").persona == "dry_tech_butler"


def test_a_beat_rejects_a_persona_id_that_is_not_an_id() -> None:
    with pytest.raises(ValidationError):
        Beat(id="a", text="hi", persona="dry tech butler")


def test_a_beat_rejects_a_malformed_marker_in_its_text() -> None:
    """A typo'd marker used to be prose, and prose gets read out loud. Finding
    out on stage that the robot says "bracket persona colon" is the failure
    this validation exists to prevent."""
    with pytest.raises(ValidationError) as exc:
        Beat(id="intro", text="Hallo [persona:] zaal")
    assert "intro" in str(exc.value)


def test_a_beat_splits_its_own_text_using_its_own_persona_as_the_base() -> None:
    beat = Beat(id="a", persona="dry_tech_butler",
                text="Netjes. [persona:kids_companion]Joepie!")
    assert beat.speech_segments() == [
        VoiceSegment(text="Netjes.", persona="dry_tech_butler"),
        VoiceSegment(text="Joepie!", persona="kids_companion"),
    ]


def test_an_improvised_line_is_split_with_the_beat_persona_too() -> None:
    """improvise/chime_in have no `text` — the line arrives from the LLM, and
    it still has to come out in the beat's persona."""
    beat = Beat(id="i", trigger="manual", mode="improvise", topic="x",
                persona="kids_companion")
    assert beat.speech_segments("Iets verzonnen.") == [
        VoiceSegment(text="Iets verzonnen.", persona="kids_companion")]
