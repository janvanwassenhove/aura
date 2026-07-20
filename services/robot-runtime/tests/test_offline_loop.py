"""U15: on-device offline behavior loop, verified against FakeRobot (no brain)."""

from __future__ import annotations

import pytest
from robot_runtime.adapters.fake import FakeRobotAdapter
from robot_runtime.engine.behavior import BehaviorEngine
from robot_runtime.offline_loop import OfflineBehaviorLoop
from shared_events.bus import AsyncEventBus
from shared_schemas.events.robot import RobotModeChanged


@pytest.fixture()
async def engine_setup():
    bus = AsyncEventBus()
    await bus.start()
    adapter = FakeRobotAdapter()
    await adapter.connect()
    engine = BehaviorEngine(adapter, bus, session_id="t")
    await engine.start()
    yield adapter, engine, bus
    await engine.stop()
    await bus.stop()


async def test_enters_offline_speaks_notice_and_idles(engine_setup) -> None:
    adapter, engine, bus = engine_setup
    modes: list[RobotModeChanged] = []

    async def cap(e: RobotModeChanged) -> None:
        modes.append(e)

    bus.subscribe(RobotModeChanged, cap)

    # timeout_s=0 → the very next check treats the brain as gone.
    loop = OfflineBehaviorLoop(engine, bus, timeout_s=0.0)

    await loop.check()
    assert loop.offline is True
    spoken = adapter.spoken_texts
    assert any("lost connection to my brain" in s for s in spoken)  # the notice
    assert adapter.executed_motions  # idle motion so it never freezes

    # Notice is spoken only once while offline.
    await loop.check()
    assert sum("lost connection" in s for s in adapter.spoken_texts) == 1


async def test_recovers_when_brain_returns(engine_setup) -> None:
    adapter, engine, bus = engine_setup
    loop = OfflineBehaviorLoop(engine, bus, timeout_s=0.0)
    await loop.check()
    assert loop.offline is True

    # A brain command arrives → liveness refreshed → next check recovers.
    loop._timeout_s = 999.0
    loop.touch()
    await loop.check()
    assert loop.offline is False
