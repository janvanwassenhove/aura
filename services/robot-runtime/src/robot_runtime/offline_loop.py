"""OfflineBehaviorLoop — on-device behavior when the brain is unreachable (U15).

Runs ON the robot (the Reachy). The laptop brain drives the robot via REST
commands; every command refreshes a liveness timestamp (`touch()`). If no command
arrives within `timeout_s`, the robot assumes the brain↔robot link is down and
keeps itself alive locally:

  - speaks a one-time "I've lost connection to my brain" notice,
  - performs periodic idle motion so it never freezes,
  - emits RobotModeChanged(→ OFFLINE) for the console.

When a command arrives again, it recovers (RobotModeChanged(→ ONLINE)). Fully
on-device — no network, no LLM. Works identically against FakeRobot.
"""

from __future__ import annotations

import asyncio
import logging
import time

from shared_events.bus import AsyncEventBus
from shared_schemas.events.robot import RobotModeChanged
from shared_schemas.robot.models import RobotMode

logger = logging.getLogger(__name__)

_OFFLINE_NOTICE = "I've lost connection to my brain. I'll keep things steady until it's back."


class OfflineBehaviorLoop:
    def __init__(
        self,
        engine,  # BehaviorEngine — avoid import cycle
        bus: AsyncEventBus,
        session_id: str = "robot",
        *,
        timeout_s: float = 15.0,
        check_interval_s: float = 4.0,
        idle_motion: str = "idle_fidget",
    ) -> None:
        self._engine = engine
        self._bus = bus
        self._session_id = session_id
        self._timeout_s = timeout_s
        self._check_interval_s = check_interval_s
        self._idle_motion = idle_motion
        self._last_seen = time.monotonic()
        self._offline = False
        self._task: asyncio.Task | None = None
        # U26: when set and constrained, idle animations are skipped so the Pi
        # sheds non-essential load while hot/saturated.
        self.budget_guard = None

    def touch(self) -> None:
        """Record a sign of life from the brain (called on every command)."""
        self._last_seen = time.monotonic()

    @property
    def offline(self) -> bool:
        return self._offline

    def _elapsed(self) -> float:
        return time.monotonic() - self._last_seen

    async def check(self) -> None:
        """Evaluate the brain link once and act. Deterministic — used by tests."""
        if self._elapsed() >= self._timeout_s:
            if not self._offline:
                self._offline = True
                logger.warning("Brain link lost — entering on-device offline behavior")
                await self._bus.publish(RobotModeChanged(
                    session_id=self._session_id,
                    from_mode=RobotMode.ONLINE, to_mode=RobotMode.OFFLINE,
                ))
                await self._engine.speak(_OFFLINE_NOTICE)
            # Keep moving so the robot never looks frozen while cut off —
            # unless the budget guard says the Pi needs the headroom (U26).
            if self.budget_guard is None or not self.budget_guard.constrained:
                await self._engine.add_motion(self._idle_motion)
        elif self._offline:
            self._offline = False
            logger.info("Brain link restored — leaving offline behavior")
            await self._bus.publish(RobotModeChanged(
                session_id=self._session_id,
                from_mode=RobotMode.OFFLINE, to_mode=RobotMode.ONLINE,
            ))

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self._check_interval_s)
            try:
                await self.check()
            except Exception:
                logger.exception("Offline behavior check failed")

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop(), name="offline-behavior-loop")

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
