"""U409: a scenario directs HOW a line is spoken.

Reported (translated): *"In the presentation scenario I want to define not only
the persona and the voice, but also the direction: powerful, short, emotional,
…"*. A beat had `persona`, `voice`, `speed` and `pause`, and nothing about
delivery.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from shared_schemas.presentation import Beat, Scenario
from shared_schemas.presentation.models import DIRECTION_MAX


def test_a_beat_and_a_talk_can_say_how_lines_are_delivered() -> None:
    beat = Beat(id="gag", text="Oh, I know this one.", direction="powerful, short")
    talk = Scenario(direction="warm, unhurried", beats=[beat])
    assert beat.direction == "powerful, short"
    assert talk.direction == "warm, unhurried"


def test_not_saying_is_no_direction() -> None:
    assert Beat(id="a", text="hi").direction == ""
    assert Scenario().direction == ""


def test_a_direction_is_a_short_note_not_an_essay() -> None:
    assert DIRECTION_MAX == 300
    Beat(id="ok", text="hi", direction="x" * DIRECTION_MAX)
    with pytest.raises(ValidationError, match="direction"):
        Beat(id="long", text="hi", direction="x" * (DIRECTION_MAX + 1))
    with pytest.raises(ValidationError, match="direction"):
        Scenario(direction="x" * (DIRECTION_MAX + 1))


def test_a_field_that_does_not_exist_is_still_refused() -> None:
    """U360: `delivery:` is what someone will write when they mean this."""
    with pytest.raises(ValidationError):
        Beat(id="a", text="hi", delivery="powerful")
    with pytest.raises(ValidationError):
        Scenario(delivery="powerful")
