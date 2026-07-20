"""Tests for BehaviorEngine state transitions (spec 004 T013)."""

from __future__ import annotations

import asyncio

import pytest
from robot_runtime.adapters.fake import FakeRobotAdapter
from robot_runtime.engine.behavior import BehaviorEngine
from shared_events.bus import AsyncEventBus
from shared_personas import Persona
from shared_schemas.events.audio import AudioInputStarted, UserSpeechDetected
from shared_schemas.robot.models import BehaviorState, RobotMode


@pytest.fixture()
async def bus() -> AsyncEventBus:
    b = AsyncEventBus()
    await b.start()
    yield b
    await b.stop()


@pytest.fixture()
async def adapter() -> FakeRobotAdapter:
    a = FakeRobotAdapter()
    await a.connect()
    return a


@pytest.fixture()
async def engine(adapter: FakeRobotAdapter, bus: AsyncEventBus) -> BehaviorEngine:
    e = BehaviorEngine(adapter, bus, session_id="test", persona=Persona.WORK)
    await e.start()
    yield e
    await e.stop()


async def test_initial_state_is_idle(engine: BehaviorEngine) -> None:
    assert engine.current_state == BehaviorState.IDLE


async def test_idle_to_listening_on_audio_started(
    engine: BehaviorEngine, bus: AsyncEventBus
) -> None:
    await bus.publish(AudioInputStarted(session_id="test"))
    await asyncio.sleep(0.05)  # let create_task dispatch run
    assert engine.current_state == BehaviorState.LISTENING


async def test_listening_to_thinking_on_speech_detected(
    engine: BehaviorEngine, bus: AsyncEventBus
) -> None:
    await bus.publish(AudioInputStarted(session_id="test"))
    await asyncio.sleep(0.05)
    await bus.publish(UserSpeechDetected(session_id="test", transcript="hello"))
    await asyncio.sleep(0.05)
    assert engine.current_state == BehaviorState.THINKING


async def test_interrupt_returns_to_idle(
    engine: BehaviorEngine, bus: AsyncEventBus
) -> None:
    await bus.publish(AudioInputStarted(session_id="test"))
    await asyncio.sleep(0.05)
    await engine.interrupt()
    assert engine.current_state == BehaviorState.IDLE


async def test_maintenance_mode_triggers_interrupt(
    engine: BehaviorEngine, bus: AsyncEventBus
) -> None:
    """Setting mode to MAINTENANCE should interrupt and return to IDLE."""
    from shared_schemas.events.robot import RobotModeChanged

    await bus.publish(AudioInputStarted(session_id="test"))
    await asyncio.sleep(0.05)
    assert engine.current_state == BehaviorState.LISTENING

    await bus.publish(
        RobotModeChanged(session_id="test", from_mode=RobotMode.ONLINE, to_mode=RobotMode.MAINTENANCE)
    )
    await asyncio.sleep(0.05)
    assert engine.current_state == BehaviorState.IDLE


async def test_idle_task_cancelled_on_stop(adapter: FakeRobotAdapter, bus: AsyncEventBus) -> None:
    """Idle fidget task is cancelled when engine stops."""
    engine = BehaviorEngine(adapter, bus, session_id="test")
    await engine.start()
    assert engine._idle_task is not None
    assert not engine._idle_task.done()
    await engine.stop()
    assert engine._idle_task.done()
