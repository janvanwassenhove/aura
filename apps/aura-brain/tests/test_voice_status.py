"""U275: hands-free voice must be observable.

Reported as "ik roep robot 'hey richie' met wakeword, maar krijg geen
reactie". Everything underneath worked — probing the robot's own microphone
transcribed "Richie" and produced a reply — so the fault was inside the loop's
gates, and nothing anywhere could say which one. The loop has no status, its
only log lines are INFO while the packaged app logs at WARNING, and a task
started with `create_task` that dies takes its exception with it.

Five different causes, one silence:
  * the loop never started, or died hours ago
  * the room is below VOICE_SPEECH_PEAK, so nothing is even transcribed
  * the name was heard and no command followed (the actual answer here)
  * the transcript was discarded as self-echo
  * hands-free is simply switched off
"""

from __future__ import annotations

import asyncio

import pytest
from aura_brain.voice_loop import VoiceLoop


class _Robot:
    async def listen(self, duration_s=0.0):
        return b"", 0.0

    async def execute_motion(self, cmd):
        self.moved = getattr(cmd, "motion_id", "?")
        return True


@pytest.fixture()
def loop(monkeypatch):
    monkeypatch.setenv("VOICE_MODE", "wake_word")
    return VoiceLoop(robot=_Robot(), pipeline=None, bus=None, default_wake_word="richie")


def test_status_says_it_is_not_running_before_start(loop) -> None:
    st = loop.status()
    assert st["running"] is False
    assert st["listening"] is False
    assert st["wake_word"] == "richie"


def test_status_reports_the_loudness_gate_that_eats_a_quiet_room(loop) -> None:
    """The gate discards a window BEFORE speech-to-text, saying nothing."""
    st = loop.status()
    assert "speech_peak_gate" in st
    assert st["last_peak"] == 0.0
    assert st["windows"] == 0


def test_a_dead_loop_is_reported_as_dead_not_as_quiet(loop) -> None:
    """`create_task` swallows the exception; "crashed" is how anyone finds out."""
    async def boom():
        raise RuntimeError("mic exploded")

    async def run():
        loop._task = asyncio.create_task(boom())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        return loop.status()

    st = asyncio.run(run())
    assert st["running"] is False
    assert "mic exploded" in st["crashed"]


def test_the_wake_word_gets_a_visible_acknowledgement(loop) -> None:
    """U275: he heard the name, opened a listening window, and gave no sign —
    so the owner waited for an answer while he waited for a command. A nod is
    not a conversational turn (U93 removed the generic spoken reply, rightly)
    but it does say "go on"."""
    robot = loop._robot
    asyncio.run(loop._acknowledge_wake())
    assert getattr(robot, "moved", "") == "nod"


def test_the_acknowledgement_can_be_switched_off(loop, monkeypatch) -> None:
    monkeypatch.setenv("WAKE_ACK", "off")
    robot = loop._robot
    asyncio.run(loop._acknowledge_wake())
    assert not hasattr(robot, "moved")


def test_an_unreachable_robot_costs_the_nod_not_the_turn(loop) -> None:
    class _Dead:
        async def execute_motion(self, cmd):
            raise OSError("no route to host")

    loop._robot = _Dead()
    asyncio.run(loop._acknowledge_wake())      # must not raise
