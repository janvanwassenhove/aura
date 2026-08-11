"""U237: asleep means the robot stops moving on its own initiative.

The reported symptom: press Asleep, the robot lies down, and a few seconds
later it is back up. Sleep lived only as an env var on the BRAIN, so the
on-device loops — which exist precisely so the robot never looks frozen — kept
fidgeting, and a reconnect ran wake_up() unconditionally.

These tests assert the behaviour, not the flag: what the robot actually did.
"""

from __future__ import annotations

import pytest
from robot_runtime import sleep_state
from robot_runtime.adapters.fake import FakeRobotAdapter
from robot_runtime.engine.behavior import BehaviorEngine
from robot_runtime.offline_loop import OfflineBehaviorLoop
from shared_events.bus import AsyncEventBus


@pytest.fixture(autouse=True)
def _awake_by_default():
    """Never leak sleep into another test — it suppresses motion everywhere."""
    sleep_state.set_asleep(False)
    yield
    sleep_state.set_asleep(False)


@pytest.fixture()
async def stack():
    bus = AsyncEventBus()
    await bus.start()
    adapter = FakeRobotAdapter()
    await adapter.connect()
    engine = BehaviorEngine(adapter, bus, session_id="t")
    await engine.start()
    yield adapter, engine, bus
    await engine.stop()
    await bus.stop()


async def test_offline_loop_moves_a_waking_robot(stack) -> None:
    """The control: awake, cut off from the brain, it fidgets so it never
    looks frozen. This is the behaviour sleep has to suppress."""
    adapter, engine, bus = stack
    loop = OfflineBehaviorLoop(engine, bus, timeout_s=0.0)

    await loop.check()

    assert loop.offline is True
    assert adapter.executed_motions, "an awake robot keeps moving when cut off"


async def test_offline_loop_leaves_a_sleeping_robot_alone(stack) -> None:
    """The bug: this is what stood the robot back up every four seconds."""
    adapter, engine, bus = stack
    loop = OfflineBehaviorLoop(engine, bus, timeout_s=0.0)

    sleep_state.set_asleep(True)
    await loop.check()
    await loop.check()
    await loop.check()

    assert adapter.executed_motions == [], "a sleeping robot must not be moved"
    assert adapter.spoken_texts == [], "nor spoken to — sleep means take no action"
    assert loop.offline is False, "and it must not narrate a mode change either"


async def test_waking_restores_the_loop(stack) -> None:
    """Sleep suspends; it does not disable. Waking must give the behaviour back
    — otherwise the fix trades one silent failure for another."""
    adapter, engine, bus = stack
    loop = OfflineBehaviorLoop(engine, bus, timeout_s=0.0)

    sleep_state.set_asleep(True)
    await loop.check()
    assert adapter.executed_motions == []

    sleep_state.set_asleep(False)
    await loop.check()
    assert adapter.executed_motions, "an awake robot moves again"


async def test_commands_still_run_while_asleep(stack) -> None:
    """Sleep suspends what the robot decides for itself, not what it is told.
    The wake button is exactly such a command, so this has to keep working."""
    from shared_schemas.robot.models import MotionCommand

    adapter, engine, bus = stack
    sleep_state.set_asleep(True)

    await adapter.execute_motion(MotionCommand(motion_id="wake_up", speed=1.0,
                                               amplitude=0.7, direction=None))

    assert adapter.executed_motions, "an explicit command must still be obeyed"


def test_state_round_trips() -> None:
    assert sleep_state.is_asleep() is False
    assert sleep_state.set_asleep(True) is True
    assert sleep_state.is_asleep() is True
    assert sleep_state.set_asleep(False) is False
    assert sleep_state.is_asleep() is False
