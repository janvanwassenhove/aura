"""U263: following the slideshow that is actually running.

Three faults the owner hit in one sitting, plus Keynote, which was absent:

  1. the watcher looked ONCE at start, so setting up the scenario before the
     slideshow cost every slide cue for the whole talk, silently;
  2. nothing checked WHICH deck was on screen;
  3. nothing knew how many slides it had, so a shifted deck fired the wrong
     beats without a word.
"""

from __future__ import annotations

import asyncio

import pytest
from aura_brain import deck_check, slides_watcher
from aura_brain.slides_watcher import SlideState, SlidesWatcher


# ---------------------------------------------------------------------------
# It keeps looking
# ---------------------------------------------------------------------------


async def test_it_waits_for_a_slideshow_that_is_not_up_yet(monkeypatch) -> None:
    """THE reported trap: the scenario is what you set up first, so the show is
    usually not running yet. Looking once meant no cues, all talk, in silence.
    """
    states: list[SlideState | None] = [None, None,
                                       SlideState("powerpoint", "talk.pptx", 1, 12)]
    seen: list[int] = []
    monkeypatch.setattr(slides_watcher, "_POLL_S", 0.01)
    monkeypatch.setattr(slides_watcher, "read_state",
                        lambda: states.pop(0) if states else
                        SlideState("powerpoint", "talk.pptx", 1, 12))

    w = SlidesWatcher(on_slide=lambda n: _record(seen, n))
    assert w.watching is False           # nothing on screen yet
    w.start()
    await asyncio.sleep(0.1)
    await w.stop()

    assert w.watching is True, "it should have picked the show up when it began"
    assert seen == [1]


async def test_a_show_that_ends_is_not_the_end_of_the_talk(monkeypatch) -> None:
    """Restarting the deck must re-fire its first beat rather than be swallowed
    as "no change" — a presenter who restarts a show is usually starting over.
    """
    seq = [SlideState("keynote", "talk.key", 3, 20), None,
           SlideState("keynote", "talk.key", 3, 20)]
    seen: list[int] = []
    monkeypatch.setattr(slides_watcher, "_POLL_S", 0.01)
    monkeypatch.setattr(slides_watcher, "read_state",
                        lambda: seq.pop(0) if seq else None)

    w = SlidesWatcher(on_slide=lambda n: _record(seen, n))
    w.start()
    await asyncio.sleep(0.1)
    await w.stop()
    assert seen == [3, 3]


async def test_only_a_changed_slide_fires(monkeypatch) -> None:
    monkeypatch.setattr(slides_watcher, "_POLL_S", 0.01)
    monkeypatch.setattr(slides_watcher, "read_state",
                        lambda: SlideState("powerpoint", "t.pptx", 7, 12))
    seen: list[int] = []
    w = SlidesWatcher(on_slide=lambda n: _record(seen, n))
    w.start()
    await asyncio.sleep(0.06)
    await w.stop()
    assert seen == [7]


async def _record(sink: list[int], n: int) -> None:
    sink.append(n)


# ---------------------------------------------------------------------------
# Keynote
# ---------------------------------------------------------------------------


def test_keynote_is_read_from_one_round_trip(monkeypatch) -> None:
    """Asking three times would let the answers come from three moments, and a
    slide number belonging to a different deck than the name beside it is worse
    than no answer at all."""
    import subprocess

    class _Out:
        stdout = "Mijn talk\t4\t22\n"

    monkeypatch.setattr(slides_watcher.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(slides_watcher.shutil, "which", lambda _n: "/usr/bin/osascript")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Out())

    state = slides_watcher._read_keynote()
    assert state == SlideState("keynote", "Mijn talk", 4, 22)


def test_keynote_not_playing_is_a_state_not_an_error(monkeypatch) -> None:
    import subprocess

    class _Out:
        stdout = "\n"

    monkeypatch.setattr(slides_watcher.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(slides_watcher.shutil, "which", lambda _n: "/usr/bin/osascript")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Out())
    assert slides_watcher._read_keynote() is None


def test_keynote_is_skipped_off_macos(monkeypatch) -> None:
    monkeypatch.setattr(slides_watcher.platform, "system", lambda: "Windows")
    assert slides_watcher._read_keynote() is None


def test_nothing_running_anywhere_is_not_an_error(monkeypatch) -> None:
    monkeypatch.setattr(slides_watcher, "_read_powerpoint", lambda: None)
    monkeypatch.setattr(slides_watcher, "_read_keynote", lambda: None)
    assert slides_watcher.read_state() is None
    assert slides_watcher.available() is False


# ---------------------------------------------------------------------------
# Which deck, and how big
# ---------------------------------------------------------------------------


def test_the_wrong_deck_is_called_out() -> None:
    warnings = deck_check.check("robot-junior-dev.pptx", "vakantiefotos.pptx", 30, [1, 4])
    assert [w.kind for w in warnings] == ["wrong_deck"]
    assert "robot-junior-dev.pptx" in warnings[0].message
    assert "vakantiefotos.pptx" in warnings[0].message


def test_the_same_deck_saved_again_is_not_a_different_deck() -> None:
    """A warning that cries wolf gets ignored exactly when it is right, so the
    copies a normal week produces must not trip it."""
    for actual in ("robot-junior-dev.pptx", "Robot-Junior-Dev.pptx",
                   "robot-junior-dev (2).pptx", "robot-junior-dev v3.pptx",
                   "C:/decks/robot-junior-dev.pptx", "robot-junior-dev-final.pptx"):
        assert deck_check.check("robot-junior-dev.pptx", actual, 30, [1]) == [], actual


def test_a_keynote_deck_matches_its_scenario() -> None:
    assert deck_check.check("mijn-talk.key", "mijn-talk", 20, [1]) == []


def test_cues_past_the_end_are_called_out() -> None:
    """The shifted-deck case: insert a slide and the tail of your scenario
    quietly points past the end."""
    warnings = deck_check.check("t.pptx", "t.pptx", 10, [2, 11, 14])
    assert [w.kind for w in warnings] == ["beats_past_end"]
    assert "10 slides" in warnings[0].message
    assert "11, 14" in warnings[0].message


def test_nothing_to_compare_means_no_warning() -> None:
    """An unnamed scenario, or an app that will not say how many slides it has,
    must not produce a scary message about nothing."""
    assert deck_check.check("", "whatever.pptx", 10, [1]) == []
    assert deck_check.check("t.pptx", "t.pptx", 0, [99]) == []


def test_slide_triggers_are_read_off_the_scenario() -> None:
    from shared_schemas.presentation.models import Beat, Scenario

    scenario = Scenario(title="t", pptx="t.pptx", beats=[
        Beat(id="a", trigger="slide:1", mode="speak", text="hi"),
        Beat(id="b", trigger="keyword:java", mode="speak", text="x"),
        Beat(id="c", trigger="slide:12", mode="speak", text="y"),
        Beat(id="d", trigger="manual", mode="speak", text="z"),
    ])
    assert deck_check.slide_triggers(scenario) == [1, 12]
