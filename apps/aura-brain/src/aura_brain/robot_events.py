"""Robot→brain event bridge (U36d).

robot-runtime publishes its events (SpeechPlaybackStarted, MotionStarted,
BehaviorStateChanged, RobotModeChanged, …) on ITS OWN bus on the Pi, exposed at
``ws://robot:8001/ws/events``. The console only listens to the BRAIN's stream —
so those events never reached the UI (Speaking stayed "Silent", Mode "UNKNOWN").

This bridge keeps one WebSocket client open to the robot and relays every frame
verbatim to the brain's console clients. On (re)connect it also fetches
``/robot/status`` once and synthesizes RobotConnected/RobotStateChanged so the
UI snaps to the correct state immediately.

U365 fixed two things that made the console claim "offline" about a robot whose
video was moving on the same screen:

* **The address is read on every attempt, not once.** U336 follows the robot to
  a new address by rewriting ``ROBOT_RUNTIME_URL`` and ``RobotClient._base_url``
  — which every HTTP call reads per request. This derived its WebSocket URL in
  ``__init__``, so after a move the camera, the status poll and speech all went
  to the new address while the event stream hammered the old one forever. Pass a
  callable and it follows him. (No watcher is needed while connected: the
  address only changes *because* the old one stopped answering, so the socket is
  already down when it does.)
* **A disconnect is a transition, not a heartbeat.** Announcing it on every
  retry flooded the console every ``reconnect_s`` seconds and overwrote anything
  a poll had just learned, which is what made the wrong state unrecoverable
  rather than merely late.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


class RobotEventBridge:
    def __init__(
        self,
        broadcaster: Any,          # WebSocketBroadcaster (needs .broadcast_raw)
        robot_base_url: str | Callable[[], str],   # http://host:8001, or a getter
        robot_client: Any = None,  # RobotClient for the initial status snapshot
        reconnect_s: float = 5.0,
        connect: Any = None,       # seam: websockets.connect
    ) -> None:
        self._broadcaster = broadcaster
        # A string keeps every existing caller working (docker-compose, tests);
        # a callable is how the brain hands over an address that can move.
        self._address: Callable[[], str] = (
            robot_base_url if callable(robot_base_url) else (lambda: str(robot_base_url))
        )
        self._robot = robot_client
        self._reconnect_s = reconnect_s
        self._connect = connect
        self._task: asyncio.Task | None = None
        #: None = nothing announced yet, so the first failure still says so.
        self._connected: bool | None = None

    def _ws_url(self) -> str:
        return self._address().rstrip("/").replace("http", "ws", 1) + "/ws/events"

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())
            logger.info("RobotEventBridge started (%s)", self._ws_url())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def _envelope(self, event_type: str, **fields: Any) -> str:
        return json.dumps({
            "event_id": str(uuid4()),
            "event_type": event_type,
            "timestamp": datetime.now(UTC).isoformat(),
            "session_id": "robot",
            **fields,
        })

    async def _announce_status(self) -> None:
        if self._robot is None:
            return
        try:
            status = await self._robot.status()
        except Exception:  # noqa: BLE001 — snapshot is best-effort
            return
        await self._broadcaster.broadcast_raw(
            self._envelope("RobotConnected", mode=status.get("mode", "online"))
        )
        await self._broadcaster.broadcast_raw(self._envelope(
            "RobotStateChanged",
            mode=status.get("mode"),
            behavior_state=status.get("behavior_state"),
        ))

    async def _run(self) -> None:
        connect = self._connect
        if connect is None:
            import websockets

            connect = websockets.connect

        while True:
            # Asked again every attempt: he may be at a different address than
            # he was when this brain started (U336/U365).
            url = self._ws_url()
            try:
                async with connect(url, open_timeout=10) as ws:
                    logger.info("robot event stream connected (%s)", url)
                    self._connected = True
                    await self._announce_status()
                    async for frame in ws:
                        if isinstance(frame, str):
                            await self._broadcaster.broadcast_raw(frame)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # robot restarting / unreachable — retry
                logger.debug("robot event stream down (%s); retrying", type(exc).__name__)
                # Only on the way down. Repeating it every reconnect_s seconds
                # overwrites whatever the console learned by asking, which is
                # what made a wrong "offline" permanent instead of brief.
                if self._connected is not False:
                    self._connected = False
                    await self._broadcaster.broadcast_raw(
                        self._envelope("RobotDisconnected"))
            await asyncio.sleep(self._reconnect_s)
