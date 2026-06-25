"""U27: 'present with me' — slides drive synchronized robot speech + gesture, and
co-pilot advance/previous navigation."""

from __future__ import annotations

import pytest

from orchestrator.presentation import PresentationManager, SlideOutOfRangeError
from shared_events.bus import AsyncEventBus
from shared_schemas.robot.models import MotionCommand

_YAML = """
title: "Demo"
slides:
  - slide_index: 0
    speech_cue: "Good morning."
  - slide_index: 1
    speech_cue: "Our roadmap."
    motion_cue: "point"
"""


class _FakeRobot:
    def __init__(self) -> None:
        self.spoken: list[str] = []
        self.motions: list[str] = []

    async def speak(self, text: str) -> None:
        self.spoken.append(text)

    async def execute_motion(self, command: MotionCommand) -> None:
        self.motions.append(command.motion_id)


@pytest.fixture()
async def bus():
    b = AsyncEventBus()
    await b.start()
    yield b
    await b.stop()


async def test_advance_drives_synced_speech_and_gesture(bus) -> None:
    robot = _FakeRobot()
    mgr = PresentationManager(bus, robot=robot)
    mgr.load_from_yaml(_YAML)

    s0 = await mgr.advance()
    assert s0.slide_index == 0
    assert robot.spoken == ["Good morning."]
    assert robot.motions == []  # slide 0 has no gesture

    s1 = await mgr.advance()
    assert s1.slide_index == 1
    assert robot.spoken[-1] == "Our roadmap."
    assert robot.motions == ["point"]  # gesture driven in sync with the cue

    # Past the end → out of range.
    with pytest.raises(SlideOutOfRangeError):
        await mgr.advance()


async def test_previous_navigates_back(bus) -> None:
    mgr = PresentationManager(bus, robot=_FakeRobot())
    mgr.load_from_yaml(_YAML)
    await mgr.advance()      # slide 0
    await mgr.advance()      # slide 1
    back = await mgr.previous()
    assert back.slide_index == 0


async def test_works_without_robot_attached(bus) -> None:
    # No robot → still tracks slides + emits cue events (console-only mode).
    mgr = PresentationManager(bus)
    mgr.load_from_yaml(_YAML)
    slide = await mgr.advance()
    assert slide.slide_index == 0
