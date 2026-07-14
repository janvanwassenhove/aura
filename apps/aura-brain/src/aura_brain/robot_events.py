"""Robot→brain event bridge (U36d).

robot-runtime publishes its events (SpeechPlaybackStarted, MotionStarted,
BehaviorStateChanged, RobotModeChanged, …) on ITS OWN bus on the Pi, exposed at
``ws://robot:8001/ws/events``. The console only listens to the BRAIN's stream —
so those events never reached the UI (Speaking stayed "Silent", Mode "UNKNOWN").

This bridge keeps one WebSocket client open to the robot and relays every frame
verbatim to the brain's console clients. On (re)connect it also fetches
``/robot/status`` once and synthesizes RobotConnected/RobotStateChanged so the
UI snaps to the correct state immediately.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


class RobotEventBridge:
    def __init__(
        self,
        broadcaster: Any,          # WebSocketBroadcaster (needs .broadcast_raw)
        robot_base_url: str,       # http://host:8001
        robot_client: Any = None,  # RobotClient for the initial status snapshot
        reconnect_s: float = 5.0,
    ) -> None:
        self._broadcaster = broadcaster
        self._ws_url = robot_base_url.rstrip("/").replace("http", "ws", 1) + "/ws/events"
        self._robot = robot_client
        self._reconnect_s = reconnect_s
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())
            logger.info("RobotEventBridge started (%s)", self._ws_url)

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
        import websockets

        while True:
            try:
                async with websockets.connect(self._ws_url, open_timeout=10) as ws:
                    logger.info("robot event stream connected")
                    await self._announce_status()
                    async for frame in ws:
                        if isinstance(frame, str):
                            await self._broadcaster.broadcast_raw(frame)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # robot restarting / unreachable — retry
                logger.debug("robot event stream down (%s); retrying", type(exc).__name__)
                await self._broadcaster.broadcast_raw(self._envelope("RobotDisconnected"))
            await asyncio.sleep(self._reconnect_s)
