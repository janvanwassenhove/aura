"""U205: the co-presenter beat/scenario model."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from shared_schemas.presentation import Beat, Scenario


def test_trigger_is_parsed_into_kind_and_value() -> None:
    assert Beat(id="a", trigger="manual", text="hi").trigger_kind == "manual"
    b = Beat(id="b", trigger="slide:3", text="hi")
    assert b.trigger_kind == "slide" and b.slide_number == 3
    k = Beat(id="c", trigger="keyword:privacy", mode="chime_in", topic="x")
    assert k.trigger_kind == "keyword" and k.trigger_value == "privacy"


def test_speak_needs_text_and_improvise_needs_topic() -> None:
    with pytest.raises(ValidationError):
        Beat(id="a", mode="speak")                      # no text
    with pytest.raises(ValidationError):
        Beat(id="b", mode="improvise")                  # no topic
    Beat(id="ok1", mode="speak", text="hello")
    Beat(id="ok2", mode="improvise", topic="the future")


def test_chime_in_must_be_keyword_triggered() -> None:
    with pytest.raises(ValidationError):
        Beat(id="a", trigger="manual", mode="chime_in", topic="x")
    Beat(id="ok", trigger="keyword:agents", mode="chime_in", topic="x")


def test_bad_triggers_and_engines_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Beat(id="a", trigger="slide:notanumber", text="hi")
    with pytest.raises(ValidationError):
        Beat(id="b", trigger="keyword:", mode="chime_in", topic="x")
    with pytest.raises(ValidationError):
        Beat(id="c", trigger="whoknows", text="hi")
    with pytest.raises(ValidationError):
        Beat(id="d", text="hi", engine="banana")


def test_scenario_rejects_duplicate_beat_ids() -> None:
    with pytest.raises(ValidationError):
        Scenario(beats=[Beat(id="dup", text="a"), Beat(id="dup", text="b")])
