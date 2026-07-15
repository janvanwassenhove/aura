"""U16: ReachyRobotAdapter — contract tests against a stubbed SDK.

No hardware needed: a fake ``reachy_mini`` module is injected into sys.modules.
The live smoke test lives in test_reachy_live.py (REACHY_LIVE=1).
"""

from __future__ import annotations

import sys
import types

import numpy as np
import pytest

from shared_schemas.robot.models import (
    BehaviorState,
    MotionCommand,
    MotionCue,
    MotionTimeline,
    RobotMode,
)


class FakeMini:
    """Records every SDK call the adapter makes."""

    def __init__(self, **kwargs) -> None:
        self.init_kwargs = kwargs
        self.calls: list[tuple[str, dict]] = []
        self.media_released = False
        self.client = types.SimpleNamespace(disconnect=lambda: self.calls.append(("disconnect", {})))

    def goto_target(self, head=None, antennas=None, duration=0.5) -> None:
        self.calls.append(("goto_target", {"head": head, "antennas": antennas, "duration": duration}))

    def look_at_world(self, x, y, z, duration=1.0):
        self.calls.append(("look_at_world", {"x": x, "y": y, "z": z}))
        return np.eye(4)

    def wake_up(self) -> None:
        self.calls.append(("wake_up", {}))

    def goto_sleep(self) -> None:
        self.calls.append(("goto_sleep", {}))

    def release_media(self) -> None:
        self.media_released = True


@pytest.fixture()
def adapter(monkeypatch):
    """A connected ReachyRobotAdapter backed by FakeMini."""
    created: list[FakeMini] = []

    fake_module = types.ModuleType("reachy_mini")

    def _ctor(**kwargs):
        mini = FakeMini(**kwargs)
        created.append(mini)
        return mini

    fake_module.ReachyMini = _ctor
    monkeypatch.setitem(sys.modules, "reachy_mini", fake_module)

    from robot_runtime.adapters.reachy import ReachyRobotAdapter

    a = ReachyRobotAdapter(host="stub-host", connection_mode="network", media_backend="no_media")
    a._created = created  # type: ignore[attr-defined]
    return a


def _moves(mini: FakeMini) -> list[str]:
    return [name for name, _ in mini.calls if name != "disconnect"]


async def test_connect_reports_online_status(adapter) -> None:
    await adapter.connect()
    state = await adapter.get_status()
    assert state.connected is True
    assert state.mode == RobotMode.ONLINE
    assert state.adapter_name == "reachy"
    mini = adapter._created[0]
    assert mini.init_kwargs["host"] == "stub-host"
    assert mini.init_kwargs["connection_mode"] == "network"


async def test_disconnect_reports_offline(adapter) -> None:
    await adapter.connect()
    await adapter.disconnect()
    state = await adapter.get_status()
    assert state.connected is False
    assert state.mode == RobotMode.OFFLINE


async def test_set_state_round_trips(adapter) -> None:
    await adapter.connect()
    await adapter.set_state(RobotMode.DEGRADED, BehaviorState.SPEAKING)
    state = await adapter.get_status()
    assert state.mode == RobotMode.DEGRADED
    assert state.behavior_state == BehaviorState.SPEAKING


async def test_nod_pitches_head_and_returns_to_neutral(adapter) -> None:
    await adapter.connect()
    await adapter.execute_motion(MotionCommand(motion_id="nod", amplitude=0.5, direction=None))
    mini = adapter._created[0]
    gotos = [kw for name, kw in mini.calls if name == "goto_target"]
    assert len(gotos) == 2
    # first leg pitches (rotation about x → element [1][2] non-zero)
    assert abs(gotos[0]["head"][1][2]) > 0
    # last leg returns to neutral
    assert np.allclose(gotos[-1]["head"], np.eye(4))


async def test_wave_wiggles_antennas_and_recenters(adapter) -> None:
    await adapter.connect()
    await adapter.execute_motion(MotionCommand(motion_id="wave", amplitude=1.0, direction=None))
    mini = adapter._created[0]
    antenna_moves = [kw["antennas"] for name, kw in mini.calls if name == "goto_target"]
    assert len(antenna_moves) == 3
    assert antenna_moves[-1] == [0.0, 0.0]


async def test_point_uses_look_at_world(adapter) -> None:
    await adapter.connect()
    await adapter.execute_motion(MotionCommand(motion_id="point", direction=None))
    assert "look_at_world" in _moves(adapter._created[0])


async def test_wake_up_and_sleep_map_to_sdk_emotes(adapter) -> None:
    await adapter.connect()
    await adapter.execute_motion(MotionCommand(motion_id="wake_up", direction=None))
    await adapter.execute_motion(MotionCommand(motion_id="sleep", direction=None))
    moves = _moves(adapter._created[0])
    # U101: wake_up still uses the SDK emote; sleep is now a custom "tucked"
    # pose (goto_target with head down + antennas back), not goto_sleep().
    assert "wake_up" in moves and "goto_target" in moves


async def test_unknown_motion_falls_back_to_gentle_nod(adapter) -> None:
    await adapter.connect()
    await adapter.execute_motion(MotionCommand(motion_id="does-not-exist", direction=None))
    mini = adapter._created[0]
    assert _moves(mini)  # did SOMETHING (graceful) rather than raising


async def test_timeline_executes_cues_in_order(adapter) -> None:
    await adapter.connect()
    timeline = MotionTimeline(cues=[
        MotionCue(offset_ms=0, motion_id="wake_up"),
        MotionCue(offset_ms=10, motion_id="sleep"),
    ])
    await adapter.execute_timeline(timeline)
    moves = _moves(adapter._created[0])
    # U101: sleep cue is a custom goto_target pose; it runs after wake_up.
    assert moves.index("wake_up") < moves.index("goto_target")


async def test_motion_before_connect_raises(adapter) -> None:
    with pytest.raises(RuntimeError):
        await adapter.execute_motion(MotionCommand(motion_id="nod", direction=None))


async def test_no_media_degrades_gracefully(adapter) -> None:
    await adapter.connect()
    # speak without audio payload: logs, no crash
    await adapter.speak("hello")
    # play_audio: skipped with a warning
    await adapter.play_audio(b"\x00\x00" * 100)
    # capture: silence of the right length (16kHz 16-bit mono)
    pcm = await adapter.capture_audio(duration_s=0.5)
    assert len(pcm) == int(0.5 * 16_000) * 2
    # camera: explicit error (recognition must know there is no frame)
    with pytest.raises(RuntimeError):
        await adapter.get_camera_frame()


async def test_speed_scales_motion_duration(adapter) -> None:
    await adapter.connect()
    await adapter.execute_motion(MotionCommand(motion_id="nod", speed=2.0, direction=None))
    await adapter.execute_motion(MotionCommand(motion_id="nod", speed=0.5, direction=None))
    mini = adapter._created[0]
    durations = [kw["duration"] for name, kw in mini.calls if name == "goto_target"]
    assert durations[0] < durations[2]  # fast nod's legs are shorter than slow nod's
