"""U325: he turns toward whoever is there — without losing follow-me.

Two failures the owner reported as one ("hij blijft soms statisch staan, zeker
wanneer iemand passeert"):

* the only pointing primitive the brain could reach was `aim()`, and aiming
  PAUSES follow-me on purpose (U161), so nothing above the runtime could ever
  look at anybody without switching the tracker off;
* when the daemon's tracker had no face, the only thing that moved the head was
  the idle sweep on a fixed 25 s clock — a passer-by is gone long before.

`gaze()` is the nudge that co-exists with the tracker (the idle sweep already
proved the daemon composes our `goto_target` with its own face aim), and the
sweep now comes quickly when somebody was just here.
"""

from __future__ import annotations

import asyncio
import sys
import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from robot_runtime import routes
from robot_runtime.adapters.fake import FakeRobotAdapter


class FakeMini:
    """Records SDK calls; `face_detected` drives what the daemon tracker sees."""

    face_detected = False

    def __init__(self, **kwargs) -> None:
        self.init_kwargs = kwargs
        self.calls: list[tuple[str, dict]] = []
        self.client = types.SimpleNamespace(disconnect=lambda: None)

    def goto_target(self, head=None, antennas=None, duration=0.5, body_yaw=0.0) -> None:
        self.calls.append(("goto_target", {"head": head, "duration": duration,
                                           "body_yaw": body_yaw}))

    def start_head_tracking(self, weight: float = 1.0) -> None:
        self.calls.append(("start_head_tracking", {"weight": weight}))

    def stop_head_tracking(self) -> None:
        self.calls.append(("stop_head_tracking", {}))

    def get_tracked_face(self, wait: bool = True, timeout: float = 5.0):
        return types.SimpleNamespace(detected=self.face_detected, ts=1.0)

    def set_automatic_body_yaw(self, enabled: bool) -> None:
        self.calls.append(("set_automatic_body_yaw", {"enabled": enabled}))

    def set_target_body_yaw(self, yaw: float) -> None:
        self.calls.append(("set_target_body_yaw", {"yaw": yaw}))

    def wake_up(self) -> None:
        self.calls.append(("wake_up", {}))

    def release_media(self) -> None:
        self.calls.append(("release_media", {}))

    def acquire_media(self) -> None:
        self.calls.append(("acquire_media", {}))


@pytest.fixture()
def adapter(monkeypatch):
    monkeypatch.setenv("HEAD_TRACKING", "false")   # we enable it explicitly
    monkeypatch.setenv("IDLE_SCAN_S", "0")         # no sweeps unless a test wants them
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


def _gotos(mini: FakeMini) -> list[dict]:
    return [kw for name, kw in mini.calls if name == "goto_target"]


# ── the nudge ───────────────────────────────────────────────────────────────

async def test_gaze_turns_the_head_without_taking_follow_me_away(adapter) -> None:
    """The whole point: aim() pauses the tracker, gaze() must not."""
    await adapter.connect()
    await adapter.set_tracking(True)
    mini = adapter._created[0]
    before = len(mini.calls)

    result = await adapter.gaze(dyaw=0.5)

    moves = [n for n, _ in mini.calls[before:]]
    assert result["moved"] is True
    assert "goto_target" in moves
    assert "stop_head_tracking" not in moves
    assert not any(kw.get("weight") == 0.0 for n, kw in mini.calls[before:]
                   if n == "start_head_tracking"), "weight 0 is a pause"
    assert adapter._tracking_on is True, "follow-me survives being pointed"


async def test_gaze_uses_the_operator_frame(adapter) -> None:
    """U164's convention, unchanged: +dyaw is toward the RIGHT of the picture,
    which is a NEGATIVE yaw in the SDK's right-handed head frame."""
    await adapter.connect()
    await adapter.set_tracking(True)
    await adapter.gaze(dyaw=0.5)
    head = _gotos(adapter._created[0])[-1]["head"]
    assert head[0][1] > 0, "a right-of-picture nudge is a negative SDK yaw"


async def test_gaze_is_relative_and_clamped(adapter) -> None:
    """A face offset is relative to where he is already looking, so nudges
    accumulate — but never past the safe range."""
    await adapter.connect()
    await adapter.set_tracking(True)
    await adapter.gaze(dyaw=0.4)
    first = adapter._gaze_yaw
    await adapter.gaze(dyaw=0.4)
    assert adapter._gaze_yaw > first, "the second nudge builds on the first"
    for _ in range(20):
        await adapter.gaze(dyaw=1.0)
    assert abs(adapter._gaze_yaw) <= adapter.AIM_YAW_MAX + 1e-9


async def test_gaze_leaves_the_torso_where_it_is(adapter) -> None:
    """U158: goto_target's body_yaw default of 0.0 silently recentred the torso
    away from the person — every gaze would have undone follow-me's body turn."""
    await adapter.connect()
    await adapter.set_tracking(True)
    await adapter.gaze(dyaw=0.3)
    assert _gotos(adapter._created[0])[-1]["body_yaw"] is None


async def test_gaze_declines_when_the_tracker_already_has_the_face(adapter) -> None:
    """Two controllers on one head fight. The daemon wins when it has a lock."""
    await adapter.connect()
    await adapter.set_tracking(True)
    mini = adapter._created[0]
    mini.face_detected = True
    before = len(mini.calls)

    result = await adapter.gaze(dyaw=0.8)

    assert result["moved"] is False
    assert "tracker" in result["reason"]
    assert "goto_target" not in [n for n, _ in mini.calls[before:]]


async def test_gaze_declines_while_follow_me_is_off(adapter) -> None:
    """Manual mode means the operator owns the head (U162)."""
    await adapter.connect()
    result = await adapter.gaze(dyaw=0.8)
    assert result["moved"] is False and "follow-me" in result["reason"]


# ── looking again, quickly, after somebody was here ─────────────────────────

async def test_the_sweep_comes_quickly_after_a_face_was_lost(adapter, monkeypatch) -> None:
    """Someone walks past: the tracker drops them, and he used to stand still
    for up to IDLE_SCAN_S (25 s). Now he looks again within seconds."""
    monkeypatch.setenv("IDLE_SCAN_S", "30")        # the calm, empty-room cadence
    monkeypatch.setenv("IDLE_SCAN_LOST_S", "0.05")  # just-lost cadence
    monkeypatch.setenv("IDLE_SCAN_TICK_S", "0.01")
    monkeypatch.setenv("IDLE_SCAN_HOLD_S", "0.001")  # U158's 0.6 s hold, sped up
    await adapter.connect()
    await adapter.set_tracking(True)
    mini = adapter._created[0]
    mini.face_detected = True
    task = asyncio.ensure_future(adapter._idle_scan_loop())
    try:
        await asyncio.sleep(0.05)          # he sees a face: nothing to search for
        assert not _gotos(mini), "he does not sweep while looking at someone"
        mini.face_detected = False          # they walk out of frame
        await asyncio.sleep(0.25)
        assert _gotos(mini), "he looks for them again within the short interval"
    finally:
        task.cancel()


async def test_an_empty_room_goes_back_to_the_calm_cadence(adapter, monkeypatch) -> None:
    """A robot sweeping every few seconds all evening is its own problem."""
    monkeypatch.setenv("IDLE_SCAN_S", "30")
    monkeypatch.setenv("IDLE_SCAN_LOST_S", "0.05")
    monkeypatch.setenv("IDLE_SCAN_RECENT_S", "0.1")   # "recently" expires fast
    monkeypatch.setenv("IDLE_SCAN_TICK_S", "0.01")
    await adapter.connect()
    await adapter.set_tracking(True)
    mini = adapter._created[0]
    task = asyncio.ensure_future(adapter._idle_scan_loop())
    try:
        await asyncio.sleep(0.3)
        sweeps = len(_gotos(mini))
        assert sweeps <= 3, f"nobody has been here: {sweeps} sweeps is pacing"
    finally:
        task.cancel()


async def test_the_sweep_keeps_gaze_honest(adapter, monkeypatch) -> None:
    """The sweep ends centred, so the nudge integrator must agree — otherwise
    the next gaze starts from a pose the head is not in."""
    monkeypatch.setenv("IDLE_SCAN_S", "0.05")
    monkeypatch.setenv("IDLE_SCAN_LOST_S", "0.05")
    monkeypatch.setenv("IDLE_SCAN_TICK_S", "0.01")
    monkeypatch.setenv("IDLE_SCAN_HOLD_S", "0.001")
    await adapter.connect()
    await adapter.set_tracking(True)
    await adapter.gaze(dyaw=0.9)
    assert adapter._gaze_yaw != 0.0
    task = asyncio.ensure_future(adapter._idle_scan_loop())
    try:
        await asyncio.sleep(0.25)
    finally:
        task.cancel()
    assert adapter._gaze_yaw == 0.0


# ── the route ───────────────────────────────────────────────────────────────

def _client() -> TestClient:
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app)


async def test_gaze_route_nudges_the_fake_robot() -> None:
    """FakeRobot is the primary target (constitution II): CI must exercise it."""
    a = FakeRobotAdapter()
    await a.connect()
    await a.set_tracking(True)
    routes.adapter = a
    try:
        r = _client().post("/robot/gaze", json={"dyaw": 0.5, "dpitch": -0.2})
        assert r.status_code == 200
        assert r.json()["moved"] is True
        assert a._last_gaze is not None
    finally:
        routes.adapter = None


async def test_gaze_route_clamps_junk() -> None:
    a = FakeRobotAdapter()
    await a.connect()
    await a.set_tracking(True)
    routes.adapter = a
    try:
        _client().post("/robot/gaze", json={"dyaw": 40, "dpitch": "nonsense"})
        assert a._last_gaze[0] <= 1.0
    finally:
        routes.adapter = None


async def test_gaze_route_501_on_a_runtime_without_it() -> None:
    """Constitution X: the brain will meet older Pis, and must be told so."""
    class NoGaze(FakeRobotAdapter):
        gaze = None  # type: ignore[assignment]

    a = NoGaze()
    await a.connect()
    routes.adapter = a
    try:
        assert _client().post("/robot/gaze", json={"dyaw": 0.1}).status_code == 501
    finally:
        routes.adapter = None
