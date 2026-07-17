"""U111: emotion & mimicry — reply tone → mood → robot motion id."""

from __future__ import annotations

from aura_brain.mood import detect_mood, mood_motion


def test_apologetic_beats_everything() -> None:
    assert detect_mood("Sorry, dat is helaas mislukt.") == "apologetic"
    assert detect_mood("I'm afraid that failed.") == "apologetic"


def test_excited_and_happy() -> None:
    assert detect_mood("Wauw, geweldig!") == "excited"
    assert detect_mood("Klaar, het is gelukt!") == "happy"
    assert detect_mood("Done!!") == "excited"          # double bang → excited
    assert detect_mood("Perfect.") == "happy"


def test_curious_on_question() -> None:
    assert detect_mood("Zal ik Spotify openen?") == "curious"
    assert detect_mood("Ik ben benieuwd naar je project") == "curious"


def test_attentive_while_working() -> None:
    assert detect_mood("Even kijken, momentje…") == "attentive"
    assert detect_mood("Let me check that for you") == "attentive"


def test_neutral_default() -> None:
    assert detect_mood("Het is drie uur.") == "neutral"
    assert detect_mood("") == "neutral"


def test_mood_motion_mapping() -> None:
    assert mood_motion("happy") == "mood_happy"
    assert mood_motion("apologetic") == "mood_apologetic"
    assert mood_motion("neutral") is None
    assert mood_motion("bogus") is None
