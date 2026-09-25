"""U365: the video was moving and the header said he was offline.

Reported as (translated): *"why is it taking so long for Richie to come
online? also at some point we see video moving (together with Richie moving)
but AURA still says robot offline — in the title bar, the video, …"*.

Both halves are the same defect, and the evidence was on the screen the whole
time: a moving picture is proof the robot is answering. Asked directly while
the console said offline, the brain answered `{"connected": true, "mode":
"online", "adapter_name": "reachy"}`. So the console was not reporting the
brain's truth; it was reporting something else that had gone stale.

Two faults, each enough on its own:

1. **The bridge could not follow him.** `RobotEventBridge` derived its
   WebSocket URL once, in `__init__`, from whatever `ROBOT_RUNTIME_URL` said at
   startup. U336 taught the brain to follow the robot to a new address — it
   rewrites the environment and `RobotClient._base_url`, which every HTTP call
   reads per request. The bridge reads neither. So after any move (the phone
   hotspot this was found on), the camera proxy, the status poll and speech all
   went to the new address while the event stream hammered the old one forever.

2. **A retry announced a fresh disconnect every five seconds.** That flood
   overwrites anything the console learns from polling, so even a correct
   answer was undone a moment later. A disconnect is a transition, not a
   heartbeat.

There were no tests on this bridge at all, which is how it survived.
"""

from __future__ import annotations

import asyncio
import json
import os

os.environ.setdefault("LLM_PROVIDER", "echo")

from aura_brain.robot_events import RobotEventBridge


class FakeBroadcaster:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def broadcast_raw(self, frame: str) -> None:
        self.sent.append(json.loads(frame))

    def types(self) -> list[str]:
        return [f["event_type"] for f in self.sent]


class FakeRobot:
    async def status(self) -> dict:
        return {"mode": "online", "behavior_state": "idle"}


def _connector(*, fails_until: int = 0, frames: list[str] | None = None):
    """A stand-in for websockets.connect that records every URL it is given."""
    seen: list[str] = []
    attempts = {"n": 0}

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def __aiter__(self):
            async def _gen():
                for f in frames or []:
                    yield f
                # The robot's stream ending is a disconnect like any other.
                raise ConnectionError("stream closed")
            return _gen()

    def connect(url: str, **kwargs):
        seen.append(url)
        attempts["n"] += 1
        if attempts["n"] <= fails_until:
            raise OSError("no route to host")
        return _Session()

    connect.seen = seen  # type: ignore[attr-defined]
    return connect


async def _run_briefly(bridge: RobotEventBridge, seconds: float = 0.25) -> None:
    bridge.start()
    await asyncio.sleep(seconds)
    await bridge.stop()


async def test_it_follows_him_to_a_new_address() -> None:
    """U336 rewrites the address the moment the old one stops answering. The
    bridge has to read it again, or it talks to a house he has left."""
    address = {"url": "http://192.168.0.178:8001"}
    connect = _connector(fails_until=99)      # nothing answers; we want the URLs

    bridge = RobotEventBridge(FakeBroadcaster(), lambda: address["url"],
                              robot_client=FakeRobot(), reconnect_s=0.02,
                              connect=connect)
    bridge.start()
    await asyncio.sleep(0.08)
    address["url"] = "http://172.20.10.8:8001"     # he moved to the hotspot
    await asyncio.sleep(0.12)
    await bridge.stop()

    assert connect.seen, "it never tried to connect"
    assert connect.seen[0].startswith("ws://192.168.0.178:8001")
    assert any(u.startswith("ws://172.20.10.8:8001") for u in connect.seen), \
        f"it kept calling the old address: {connect.seen[-3:]}"


async def test_a_plain_string_address_still_works() -> None:
    """docker-compose and every existing caller pass a string."""
    connect = _connector(fails_until=99)
    bridge = RobotEventBridge(FakeBroadcaster(), "http://robot-runtime:8001",
                              reconnect_s=0.02, connect=connect)
    await _run_briefly(bridge, 0.06)

    assert connect.seen[0] == "ws://robot-runtime:8001/ws/events"


async def test_a_retry_is_not_a_new_disconnect_every_five_seconds() -> None:
    """The flood is what made the console unfixable: a poll would learn the
    truth and the next retry tick would overwrite it."""
    bus = FakeBroadcaster()
    connect = _connector(fails_until=99)
    bridge = RobotEventBridge(bus, "http://robot:8001", reconnect_s=0.02,
                              connect=connect)
    await _run_briefly(bridge, 0.2)

    assert len(connect.seen) > 3, "the test did not actually retry"
    assert bus.types().count("RobotDisconnected") == 1, bus.types()


async def test_he_is_announced_again_when_he_comes_back() -> None:
    bus = FakeBroadcaster()
    connect = _connector(fails_until=1)
    bridge = RobotEventBridge(bus, "http://robot:8001", robot_client=FakeRobot(),
                              reconnect_s=0.02, connect=connect)
    await _run_briefly(bridge, 0.15)

    types = bus.types()
    assert "RobotDisconnected" in types
    assert "RobotConnected" in types
    assert types.index("RobotDisconnected") < types.index("RobotConnected")


async def test_the_robot_s_own_events_still_reach_the_console_verbatim() -> None:
    """The bridge's actual job, locked in — it had no test at all."""
    bus = FakeBroadcaster()
    frame = json.dumps({"event_id": "1", "event_type": "MotionStarted",
                        "timestamp": "2026-09-25T00:00:00Z", "name": "wave"})
    connect = _connector(frames=[frame])
    bridge = RobotEventBridge(bus, "http://robot:8001", robot_client=FakeRobot(),
                              reconnect_s=0.02, connect=connect)
    await _run_briefly(bridge, 0.1)

    assert any(f.get("name") == "wave" for f in bus.sent), bus.types()
