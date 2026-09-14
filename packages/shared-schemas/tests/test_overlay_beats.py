"""U352: a scenario says when the overlay is on the projector and when it is not.

Asked as: in presentation mode, within the scenario, an option to define when
the overlay is shown — "if not mentioned (and activated) it will be shown
continuously".

That last clause is the whole compatibility contract: every scenario written
before this unit says nothing about the overlay, and every one of them must go
on showing it for the whole talk.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from shared_schemas.presentation import Beat, Scenario

# --------------------------------------------------------------------------- #
# the default: say nothing, and nothing changes
# --------------------------------------------------------------------------- #

def test_a_scenario_that_never_mentions_the_overlay_starts_visible() -> None:
    assert Scenario(beats=[Beat(id="a", text="hi")]).overlay_starts_visible is True


def test_a_beat_that_never_mentions_the_overlay_changes_nothing() -> None:
    assert Beat(id="a", text="hi").overlay_change is None


# --------------------------------------------------------------------------- #
# a whole talk can start hidden, so the overlay appears only where it is asked for
# --------------------------------------------------------------------------- #

def test_a_scenario_can_start_hidden() -> None:
    assert Scenario(overlay="hidden", beats=[]).overlay_starts_visible is False
    assert Scenario(overlay="shown", beats=[]).overlay_starts_visible is True


def test_the_scenario_accepts_either_spelling() -> None:
    """`hidden` describes a state and `hide` an action; people reach for both,
    and refusing one of them teaches nothing."""
    for word in ("hidden", "hide", "HIDDEN", " hide "):
        assert Scenario(overlay=word, beats=[]).overlay_starts_visible is False
    for word in ("shown", "show", "Shown"):
        assert Scenario(overlay=word, beats=[]).overlay_starts_visible is True


def test_a_scenario_rejects_an_overlay_word_it_does_not_know() -> None:
    with pytest.raises(ValidationError) as exc:
        Scenario(overlay="maybe", beats=[])
    assert "shown" in str(exc.value) and "hidden" in str(exc.value)


# --------------------------------------------------------------------------- #
# a beat turns it on or off from that moment
# --------------------------------------------------------------------------- #

def test_a_beat_can_show_or_hide_the_overlay() -> None:
    assert Beat(id="a", text="hi", overlay="show").overlay_change is True
    assert Beat(id="b", text="hi", overlay="hide").overlay_change is False


def test_a_beat_accepts_either_spelling_too() -> None:
    assert Beat(id="a", text="hi", overlay="hidden").overlay_change is False
    assert Beat(id="b", text="hi", overlay="SHOWN").overlay_change is True


def test_a_beat_rejects_an_overlay_word_it_does_not_know() -> None:
    with pytest.raises(ValidationError) as exc:
        Beat(id="demo", text="hi", overlay="off-ish")
    assert "demo" in str(exc.value), "the error must name the beat to look at"


def test_a_silent_beat_may_still_move_the_overlay() -> None:
    """The most useful hide of all: a beat that exists only to get him off the
    screen while something else happens."""
    beat = Beat(id="demo", trigger="slide:5", mode="silent", overlay="hide")
    assert beat.overlay_change is False


# --------------------------------------------------------------------------- #
# U360: a beat may name a raw voice, a speed and a pause — and a typo is refused
# --------------------------------------------------------------------------- #

def test_a_beat_can_name_a_voice_and_a_speed() -> None:
    """A generated scenario wrote `voice: onyx` / `speed: 0.85` for a gag that
    turns on a second voice. Both were silently dropped, so the joke was
    delivered in the ordinary voice and nothing said why."""
    beat = Beat(id="the-fanfare", trigger="slide:9", mode="speak",
                text="Ta. Ta. Ta.", voice="onyx", speed=0.85)
    assert beat.voice == "onyx"
    assert beat.speed == 0.85


def test_a_beat_can_wait_before_it_speaks() -> None:
    beat = Beat(id="the-setup", trigger="slide:9", mode="speak", text="x", pause=7.0)
    assert beat.pause == 7.0


def test_those_three_default_to_nothing_at_all() -> None:
    beat = Beat(id="a", text="hi")
    assert beat.voice == "" and beat.speed == 0.0 and beat.pause == 0.0


def test_an_unknown_voice_is_refused_by_name() -> None:
    with pytest.raises(ValidationError) as exc:
        Beat(id="the-fanfare", text="x", voice="onix")
    assert "the-fanfare" in str(exc.value) and "onix" in str(exc.value)


def test_a_speed_the_provider_will_not_take_is_refused() -> None:
    for bad in (0.1, 5.0, -1.0):
        with pytest.raises(ValidationError):
            Beat(id="b", text="x", speed=bad)
    Beat(id="ok", text="x", speed=0.25)
    Beat(id="ok2", text="x", speed=4.0)


def test_a_negative_pause_is_refused() -> None:
    with pytest.raises(ValidationError):
        Beat(id="b", text="x", pause=-1.0)


def test_a_field_that_does_not_exist_is_refused_loudly() -> None:
    """The whole reason this unit exists. `voice:` sat in a shipped scenario
    doing nothing, through a rehearsal, because pydantic ignores extra keys by
    default. A misspelt field must stop the load, not evaporate."""
    with pytest.raises(ValidationError) as exc:
        Beat(id="the-fanfare", text="x", voise="onyx")
    assert "voise" in str(exc.value)


def test_a_scenario_refuses_unknown_keys_too() -> None:
    with pytest.raises(ValidationError):
        Scenario(beats=[], titel="typo")
