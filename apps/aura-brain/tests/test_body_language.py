"""U326: he is in the conversation with his body, not only with his voice.

Two halves of one complaint — "meeleven terwijl ik praat, als ik praat of als
hij praat":

* while the OTHER person talks he was completely still. The wake nod and the
  thinking pose (U275, U147) both land around a turn, never inside one, and in
  a realtime or GPT-Live conversation there is no wake word, so neither fires
  at all.
* while HE talks, the streamed paths command no motion whatsoever — the head
  sway is the SDK reacting to audio, nothing that knows what he is saying.

Everything here keeps follow-me alive (only motions from the runtime's
follow-gesture set) and can never delay a word: a gesture that arrives after
the sentence is worse than no gesture.
"""

from __future__ import annotations

import asyncio
import os

os.environ.setdefault("LLM_PROVIDER", "echo")

import pytest
from aura_brain.body_language import KEEPS_TRACKING, ConversationBody, start_motion


class _Robot:
    def __init__(self, fail: Exception | None = None, hang: bool = False) -> None:
        self.motions: list[tuple[str, float]] = []
        self._fail = fail
        self._hang = hang

    async def execute_motion(self, command) -> bool:
        if self._fail is not None:
            raise self._fail
        if self._hang:
            await asyncio.sleep(30)
        self.motions.append((command.motion_id, command.amplitude))
        return True


def _ids(robot: _Robot) -> list[str]:
    return [m for m, _ in robot.motions]


@pytest.fixture(autouse=True)
def _defaults(monkeypatch):
    for var in ("BACKCHANNEL", "BACKCHANNEL_MIN_S", "BACKCHANNEL_AMPLITUDE",
                "TALK_GESTURES", "TALK_GESTURE_MIN_S"):
        monkeypatch.delenv(var, raising=False)


# ── while the other person is talking ──────────────────────────────────────

async def test_he_acknowledges_that_he_is_listening() -> None:
    robot = _Robot()
    assert await ConversationBody(robot).heard() is True
    assert len(robot.motions) == 1


async def test_he_does_not_nod_at_every_syllable() -> None:
    """Transcript deltas arrive many times a second; a cue per delta is a tic."""
    body = ConversationBody(_Robot())
    assert await body.heard() is True
    assert await body.heard() is False
    assert await body.heard() is False


async def test_the_acknowledgement_is_small_and_keeps_him_looking_at_you() -> None:
    """A big move would both break eye contact and put motor noise next to the
    microphone in the middle of the sentence it is supposed to be hearing."""
    robot = _Robot()
    body = ConversationBody(robot)
    os.environ["BACKCHANNEL_MIN_S"] = "0"
    try:
        for _ in range(6):
            await body.heard()
    finally:
        del os.environ["BACKCHANNEL_MIN_S"]
    assert len(robot.motions) == 6
    assert len(set(_ids(robot))) > 1, "the same nod six times reads as a machine"
    for motion, amplitude in robot.motions:
        assert motion in KEEPS_TRACKING, motion
        assert amplitude <= 0.4, "a backchannel is a small thing"


async def test_he_keeps_acknowledging_while_you_keep_talking(monkeypatch) -> None:
    monkeypatch.setenv("BACKCHANNEL_MIN_S", "0.02")
    robot = _Robot()
    body = ConversationBody(robot)
    body.start_listening()
    await asyncio.sleep(0.12)
    body.stop_listening()
    during = len(robot.motions)
    await asyncio.sleep(0.08)
    assert during >= 2, "one nod for a long sentence is not listening"
    assert len(robot.motions) == during, "and he stops when you stop"
    assert body.listening is False


async def test_starting_twice_does_not_double_the_nodding(monkeypatch) -> None:
    monkeypatch.setenv("BACKCHANNEL_MIN_S", "0.02")
    body = ConversationBody(_Robot())
    body.start_listening()
    body.start_listening()
    await asyncio.sleep(0.05)
    body.stop_listening()
    assert body.listening is False


async def test_it_can_be_switched_off(monkeypatch) -> None:
    monkeypatch.setenv("BACKCHANNEL", "false")
    robot = _Robot()
    assert await ConversationBody(robot).heard() is False
    assert robot.motions == []


# ── while he is talking ────────────────────────────────────────────────────

async def test_what_he_says_shapes_how_he_moves() -> None:
    greeting, question = _Robot(), _Robot()
    assert await ConversationBody(greeting).replying("Hallo Jan, goedemorgen!") is True
    assert await ConversationBody(question).replying("Wat bedoel je daarmee?") is True
    assert _ids(greeting) == ["wave"]
    assert _ids(question) == ["tilt"]


async def test_he_gestures_once_per_reply_not_once_per_word() -> None:
    body = ConversationBody(_Robot())
    assert await body.replying("Ja, dat klopt.") is True
    assert await body.replying("Ja, dat klopt helemaal.") is False


async def test_talk_gestures_can_be_switched_off(monkeypatch) -> None:
    monkeypatch.setenv("TALK_GESTURES", "false")
    robot = _Robot()
    assert await ConversationBody(robot).replying("Hallo!") is False
    assert robot.motions == []


async def test_every_talk_gesture_keeps_him_facing_you() -> None:
    os.environ["TALK_GESTURE_MIN_S"] = "0"
    robot = _Robot()
    body = ConversationBody(robot)
    try:
        for text in ("Hallo!", "Geweldig gedaan!", "Sorry, dat lukt niet.",
                     "Klopt dat?", "Ik kijk het na."):
            await body.replying(text)
    finally:
        del os.environ["TALK_GESTURE_MIN_S"]
    assert len(robot.motions) == 5
    for motion, _ in robot.motions:
        assert motion in KEEPS_TRACKING, motion


# ── never at the cost of a word ────────────────────────────────────────────

async def test_a_gesture_never_delays_the_reply() -> None:
    """The whole reason this is a task and not an await: the old path waited
    for the gesture to finish before it even started synthesising speech, so
    every reply began with a move, then a silence, then a voice."""
    task = start_motion(_Robot(hang=True), "nod", 0.5)
    assert task is not None and not task.done()
    task.cancel()


async def test_a_robot_that_cannot_move_costs_nothing() -> None:
    """An unreachable robot must cost the gesture, not the conversation."""
    body = ConversationBody(_Robot(fail=RuntimeError("no robot")))
    assert await body.heard() is False
    assert await body.replying("Hallo!") is False


async def test_a_robot_without_motion_at_all_is_fine() -> None:
    class Mute:
        pass

    assert await ConversationBody(Mute()).heard() is False


# ── U328: the antennae carry the reaction too ──────────────────────────────

async def test_he_listens_with_his_antennae_not_only_his_head() -> None:
    """Antenna cues cost no eye contact and put no motor noise on the head
    while it is hearing a sentence — so they lead the rotation."""
    from aura_brain.body_language import ANTENNA_CUES

    robot = _Robot()
    body = ConversationBody(robot)
    os.environ["BACKCHANNEL_MIN_S"] = "0"
    try:
        for _ in range(4):
            await body.heard()
    finally:
        del os.environ["BACKCHANNEL_MIN_S"]
    used = _ids(robot)
    assert len(used) == 4
    assert any(m in ANTENNA_CUES for m in used), used
    assert all(m in KEEPS_TRACKING for m in used), used


async def test_the_tone_of_the_reply_reaches_the_antennae() -> None:
    """Regret droops, a greeting waves, everything else is the head-and-antenna
    acknowledgement — one classification, shared with the typed path."""
    cases = {
        "Sorry, dat lukt niet vandaag.": "droop",
        "Hallo Jan, goedemorgen!": "wave",
        "Ik kijk het even na.": "acknowledge",
    }
    os.environ["TALK_GESTURE_MIN_S"] = "0"
    try:
        for text, expected in cases.items():
            robot = _Robot()
            await ConversationBody(robot).replying(text)
            assert _ids(robot) == [expected], (text, _ids(robot))
    finally:
        del os.environ["TALK_GESTURE_MIN_S"]


def test_one_classification_for_both_paths() -> None:
    """`gesture_for` keeps its answers (the typed path is unchanged); the
    antenna mapping reads the same tone, so the two can never drift."""
    from aura_brain.embodiment import gesture_for, tone_for

    assert tone_for("Hallo!") == "greeting"
    assert tone_for("Geweldig gedaan!") == "excited"
    assert tone_for("Sorry, dat lukt niet.") == "sad"
    assert tone_for("Klopt dat?") == "question"
    assert tone_for("Ik kijk het na.") == "plain"
    # unchanged behaviour for everything that already used it
    assert gesture_for("Hallo!") == "wave"
    assert gesture_for("Klopt dat?") == "tilt"
    assert gesture_for("Ik kijk het na.") == "nod"
