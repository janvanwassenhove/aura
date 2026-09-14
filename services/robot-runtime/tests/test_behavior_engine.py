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


# --------------------------------------------------------------------------- #
# U359: one failed line must not make him mute for the rest of the talk
# --------------------------------------------------------------------------- #

async def test_a_failed_line_still_leaves_him_able_to_speak_again(
    engine: BehaviorEngine, adapter: FakeRobotAdapter
) -> None:
    """Found mid-rehearsal, one slide into a conference talk: the first line
    played, and every line after it came back `500 Internal Server Error`.

    `speak()` transitions to SPEAKING, plays, then transitions to IDLE — with
    nothing in between guarded. A playback that raises skips the last step and
    leaves the engine in SPEAKING, and SPEAKING → SPEAKING is not a legal
    transition. So one transient audio failure turns into a robot that cannot
    speak again for the rest of the session.
    """
    async def boom(text, audio_bytes=None):
        raise RuntimeError("audio device went away")

    adapter.speak = boom                       # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        await engine.speak("this one fails")

    assert engine.current_state == BehaviorState.IDLE, \
        "he is stuck in SPEAKING and can never speak again"


async def test_he_actually_speaks_again_after_one_failure(
    engine: BehaviorEngine, adapter: FakeRobotAdapter
) -> None:
    """The state is the mechanism; this is the thing the room notices."""
    original = adapter.speak

    async def boom(text, audio_bytes=None):
        raise RuntimeError("audio device went away")

    adapter.speak = boom                       # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        await engine.speak("the setup line")

    adapter.speak = original                   # type: ignore[method-assign]
    await engine.speak("the fanfare")          # must not raise
    assert engine.current_state == BehaviorState.IDLE


async def test_the_room_is_never_left_thinking_he_is_still_talking(
    engine: BehaviorEngine, adapter: FakeRobotAdapter, bus: AsyncEventBus
) -> None:
    """The console derives "he is speaking" from the playback events. A start
    with no matching completion is a subtitle that never clears and an avatar
    that mouths for ever."""
    from shared_schemas.events.behavior import SpeechPlaybackCompleted

    seen: list = []
    bus.subscribe(SpeechPlaybackCompleted, lambda e: seen.append(e))

    async def boom(text, audio_bytes=None):
        raise RuntimeError("audio device went away")

    adapter.speak = boom                       # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        await engine.speak("this one fails")
    await asyncio.sleep(0.05)

    assert seen, "playback started and never finished, as far as anyone watching knows"
