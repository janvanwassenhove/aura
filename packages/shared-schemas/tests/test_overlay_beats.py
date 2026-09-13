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
