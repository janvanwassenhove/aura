"""U16 live smoke — runs against the REAL robot over the network.

Skipped unless REACHY_LIVE=1 (needs the robot awake on the LAN and the
reachy-mini SDK installed: uv sync --package robot-runtime --extra reachy).

    REACHY_LIVE=1 REACHY_HOST=reachy-mini.local \
      uv run --package robot-runtime --extra dev --extra reachy \
      pytest services/robot-runtime/tests/test_reachy_live.py -v
"""

from __future__ import annotations

import os

import pytest

from shared_schemas.robot.models import MotionCommand, RobotMode

pytestmark = pytest.mark.skipif(
    os.environ.get("REACHY_LIVE") != "1",
    reason="live robot test: set REACHY_LIVE=1 with the robot on the network",
)


@pytest.fixture()
async def live_adapter():
    from robot_runtime.adapters.reachy import ReachyRobotAdapter

    adapter = ReachyRobotAdapter(
        host=os.environ.get("REACHY_HOST", "reachy-mini.local"),
        connection_mode="network",
        media_backend="no_media",  # motion-only smoke; media needs gstreamer
    )
    await adapter.connect()
    yield adapter
    await adapter.disconnect()


async def test_live_connect_and_status(live_adapter) -> None:
    state = await live_adapter.get_status()
    assert state.connected is True
    assert state.mode == RobotMode.ONLINE
    assert state.adapter_name == "reachy"


async def test_live_gentle_nod(live_adapter) -> None:
    # Small and slow on purpose: a visible but safe hardware wiggle.
    await live_adapter.execute_motion(
        MotionCommand(motion_id="nod", speed=0.8, amplitude=0.3, direction=None)
    )


async def test_live_antenna_wave(live_adapter) -> None:
    await live_adapter.execute_motion(
        MotionCommand(motion_id="wave", speed=1.0, amplitude=0.5, direction=None)
    )
