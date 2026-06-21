"""Contract tests for FakeRobotAdapter (spec 002)."""

import pytest
from robot_runtime.adapters.fake import FakeRobotAdapter
from shared_schemas.robot.models import BehaviorState, MotionCommand, RobotMode


@pytest.fixture
async def adapter() -> FakeRobotAdapter:
    a = FakeRobotAdapter()
    await a.connect()
    return a


async def test_connect_sets_online(adapter: FakeRobotAdapter) -> None:
    status = await adapter.get_status()
    assert status.connected is True
    assert status.mode == RobotMode.ONLINE


async def test_speak_records_text(adapter: FakeRobotAdapter) -> None:
    await adapter.speak("Hello, world")
    assert "Hello, world" in adapter.spoken_texts


async def test_capture_audio_returns_bytes(adapter: FakeRobotAdapter) -> None:
    raw = await adapter.capture_audio(0.1)
    assert isinstance(raw, bytes)
    assert len(raw) > 0


async def test_execute_motion_records(adapter: FakeRobotAdapter) -> None:
    cmd = MotionCommand(motion_id="nod", speed=0.5, amplitude=0.4, direction=None)
    await adapter.execute_motion(cmd)
    assert any(m.motion_id == "nod" for m in adapter.executed_motions)


async def test_get_camera_frame_returns_bytes(adapter: FakeRobotAdapter) -> None:
    frame = await adapter.get_camera_frame()
    assert isinstance(frame, bytes)
    assert len(frame) > 0
    assert frame[:8] == b"\x89PNG\r\n\x1a\n"


async def test_disconnect_sets_offline(adapter: FakeRobotAdapter) -> None:
    await adapter.disconnect()
    status = await adapter.get_status()
    assert status.connected is False
    assert status.mode == RobotMode.OFFLINE


async def test_set_state(adapter: FakeRobotAdapter) -> None:
    await adapter.set_state(RobotMode.DEGRADED, BehaviorState.THINKING)
    status = await adapter.get_status()
    assert status.mode == RobotMode.DEGRADED
    assert status.behavior_state == BehaviorState.THINKING
