"""Tests for AsyncEventBus."""

import asyncio
import pytest
from shared_events.bus import AsyncEventBus, EventBusNotStartedError
from shared_schemas.events.robot import RobotConnected


async def test_publish_before_start_raises():
    bus = AsyncEventBus()
    with pytest.raises(EventBusNotStartedError):
        await bus.publish(RobotConnected(session_id="s1", adapter_name="fake"))


async def test_handler_called_on_publish():
    bus = AsyncEventBus()
    await bus.start()

    received = []

    async def handler(event: RobotConnected) -> None:
        received.append(event)

    bus.subscribe(RobotConnected, handler)
    await bus.publish(RobotConnected(session_id="s1", adapter_name="fake"))

    # Allow create_task to run
    await asyncio.sleep(0.05)
    assert len(received) == 1
    assert received[0].adapter_name == "fake"


async def test_unsubscribe_stops_handler():
    bus = AsyncEventBus()
    await bus.start()

    received = []

    async def handler(event: RobotConnected) -> None:
        received.append(event)

    bus.subscribe(RobotConnected, handler)
    bus.unsubscribe(RobotConnected, handler)
    await bus.publish(RobotConnected(session_id="s1", adapter_name="fake"))
    await asyncio.sleep(0.05)
    assert received == []


async def test_handler_exception_does_not_crash_bus():
    bus = AsyncEventBus()
    await bus.start()

    async def bad_handler(event: RobotConnected) -> None:
        raise RuntimeError("boom")

    bus.subscribe(RobotConnected, bad_handler)
    # Should not raise
    await bus.publish(RobotConnected(session_id="s1", adapter_name="fake"))
    await asyncio.sleep(0.05)


async def test_stop_prevents_publish():
    bus = AsyncEventBus()
    await bus.start()
    await bus.stop()
    with pytest.raises(EventBusNotStartedError):
        await bus.publish(RobotConnected(session_id="s1", adapter_name="fake"))
