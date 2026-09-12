"""U328: he reacts with his antennae, not only with his head.

Asked for after the movement report: "het is niet alleen knikken of nodge of
tracken, maar ook in combinatie met de antennes kan hij reactie tonen."

The antennae are the right instrument for a reaction that lands INSIDE someone
else's sentence, and not because they look nice:

* they do not move the head, so they cost no eye contact and cannot fight the
  face tracker (the same reason U157 used antennae for talking);
* the Stewart platform under the head is what puts motor noise next to the
  microphone mid-capture (U147) — an antenna does not.

So this is a small vocabulary of antenna-led cues, plus one that moves head and
antennae **together in the same command**, which is what reads as a reaction
rather than as a servo.
"""

from __future__ import annotations

import sys
import types

import numpy as np
import pytest
from shared_schemas.robot.models import MotionCommand


class FakeMini:
    def __init__(self, **kwargs) -> None:
        self.init_kwargs = kwargs
        self.calls: list[tuple[str, dict]] = []
        self.client = types.SimpleNamespace(disconnect=lambda: None)

    def goto_target(self, head=None, antennas=None, duration=0.5, body_yaw=0.0) -> None:
        self.calls.append(("goto_target", {"head": head, "antennas": antennas,
                                           "duration": duration, "body_yaw": body_yaw}))

    def start_head_tracking(self, weight: float = 1.0) -> None:
        self.calls.append(("start_head_tracking", {"weight": weight}))

    def stop_head_tracking(self) -> None:
        self.calls.append(("stop_head_tracking", {}))

    def get_tracked_face(self, wait: bool = True, timeout: float = 5.0):
        return types.SimpleNamespace(detected=False, ts=1.0)

    def set_automatic_body_yaw(self, enabled: bool) -> None: ...

    def set_target_body_yaw(self, yaw: float) -> None: ...

    def wake_up(self) -> None: ...

    def release_media(self) -> None: ...

    def acquire_media(self) -> None: ...


@pytest.fixture()
def adapter(monkeypatch):
    monkeypatch.setenv("HEAD_TRACKING", "false")
    monkeypatch.setenv("IDLE_SCAN_S", "0")
    monkeypatch.setenv("TRACKING_WATCHDOG_S", "0")
    created: list[FakeMini] = []
    module = types.ModuleType("reachy_mini")

    def _ctor(**kwargs):
        mini = FakeMini(**kwargs)
        created.append(mini)
        return mini

    module.ReachyMini = _ctor
    monkeypatch.setitem(sys.modules, "reachy_mini", module)
    from robot_runtime.adapters.reachy import ReachyRobotAdapter

    a = ReachyRobotAdapter(host="stub", connection_mode="network", media_backend="no_media")
    a._created = created  # type: ignore[attr-defined]
    return a


def _legs(mini: FakeMini) -> list[dict]:
    return [kw for name, kw in mini.calls if name == "goto_target"]


ANTENNA_ONLY = ("perk", "flick", "droop", "alert")


@pytest.mark.parametrize("motion", ANTENNA_ONLY)
async def test_the_antenna_cues_move_the_antennae_and_leave_the_head_alone(
    adapter, motion: str,
) -> None:
    """Antenna-only is the whole point: no eye contact lost, no motor noise on
    the head while it is listening to somebody."""
    await adapter.connect()
    mini = adapter._created[0]
    before = len(mini.calls)
    await adapter.execute_motion(MotionCommand(motion_id=motion, amplitude=0.6,
                                               direction=None))
    legs = [kw for name, kw in mini.calls[before:] if name == "goto_target"]
    assert legs, f"{motion} did nothing"
    assert all(leg["head"] is None for leg in legs), f"{motion} moved the head"
    assert any(leg["antennas"] and any(abs(v) > 0.01 for v in leg["antennas"])
               for leg in legs), f"{motion} did not move the antennae"


async def test_acknowledge_moves_head_and_antennae_in_the_same_command(adapter) -> None:
    """"In combination" is one command, not a nod followed by a wiggle — two
    commands would serialise on the motion lock and read as two events."""
    await adapter.connect()
    mini = adapter._created[0]
    before = len(mini.calls)
    await adapter.execute_motion(MotionCommand(motion_id="acknowledge", amplitude=0.6,
                                               direction=None))
    legs = [kw for name, kw in mini.calls[before:] if name == "goto_target"]
    together = [leg for leg in legs
                if leg["head"] is not None and leg["antennas"] is not None]
    assert together, "the head and the antennae never moved in one command"


async def test_a_reaction_is_smaller_than_a_deliberate_nod(adapter) -> None:
    """It lands inside someone else's sentence; a full nod there is an
    interruption."""
    await adapter.connect()
    mini = adapter._created[0]
    await adapter.execute_motion(MotionCommand(motion_id="nod", amplitude=1.0,
                                               direction=None))
    nod = max(abs(float(leg["head"][1][2])) for leg in _legs(mini)
              if leg["head"] is not None)
    mini.calls.clear()
    await adapter.execute_motion(MotionCommand(motion_id="acknowledge", amplitude=1.0,
                                               direction=None))
    ack = max(abs(float(leg["head"][1][2])) for leg in _legs(mini)
              if leg["head"] is not None)
    assert 0 < ack < nod


@pytest.mark.parametrize("motion", [*ANTENNA_ONLY, "acknowledge"])
async def test_none_of_them_costs_follow_me(adapter, motion: str) -> None:
    """A reaction that makes him look away from you is not a reaction."""
    await adapter.connect()
    await adapter.set_tracking(True)
    mini = adapter._created[0]
    before = len(mini.calls)
    await adapter.execute_motion(MotionCommand(motion_id=motion, amplitude=0.5,
                                               direction=None))
    moves = [n for n, _ in mini.calls[before:]]
    assert "stop_head_tracking" not in moves
    assert not any(kw.get("weight") == 0.0 for n, kw in mini.calls[before:]
                   if n == "start_head_tracking"), f"{motion} paused tracking"


async def test_the_torso_is_never_recentred_by_a_reaction(adapter) -> None:
    """U158: goto_target's body_yaw default of 0.0 turns him away from the
    person he is reacting to."""
    await adapter.connect()
    mini = adapter._created[0]
    await adapter.execute_motion(MotionCommand(motion_id="perk", amplitude=0.5,
                                               direction=None))
    assert all(leg["body_yaw"] is None for leg in _legs(mini))


async def test_an_unknown_motion_still_falls_back_to_a_nod(adapter) -> None:
    """The new ids must not shadow the default path for anything else."""
    await adapter.connect()
    mini = adapter._created[0]
    await adapter.execute_motion(MotionCommand(motion_id="wobbledy", amplitude=0.5,
                                               direction=None))
    assert any(leg["head"] is not None for leg in _legs(mini))
    assert isinstance(_legs(mini)[0]["head"], np.ndarray)
