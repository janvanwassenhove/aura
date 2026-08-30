"""HeartbeatMonitor — background task that monitors backend services.

Pings each registered service endpoint every `interval_s` seconds.
Tracks per-service consecutive failure counts.

Mode state machine:
  ONLINE     → DEGRADED    (any service fails 3× in a row)
  DEGRADED   → RECOVERING  (all services healthy again)
  RECOVERING → ONLINE      (30-second stability window passes)
  DEGRADED   → MAINTENANCE (>= 24 hours in DEGRADED)

Emits events:
  BackendHeartbeatOk(service, latency_ms)
  BackendHeartbeatFailed(service, consecutive_failures)
  RobotModeChanged(from_mode, to_mode)
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict

import httpx
from shared_events.bus import AsyncEventBus
from shared_schemas.events.robot import RobotModeChanged
from shared_schemas.events.system import BackendHeartbeatFailed, BackendHeartbeatOk
from shared_schemas.robot.models import RobotMode

logger = logging.getLogger(__name__)

_FAILURE_THRESHOLD = 3          # consecutive failures before DEGRADED
_STABILITY_WINDOW_S = 30.0      # seconds of healthy heartbeats before ONLINE
_MAINTENANCE_THRESHOLD_S = 86_400.0  # 24 hours in DEGRADED → MAINTENANCE


class HeartbeatMonitor:
    """Asyncio background heartbeat monitor."""

    def __init__(
        self,
        bus: AsyncEventBus,
        services: dict[str, str],            # name → health URL
        interval_s: float = 30.0,
        failure_threshold: int = _FAILURE_THRESHOLD,
        stability_window_s: float = _STABILITY_WINDOW_S,
        essential: set[str] | None = None,
    ) -> None:
        self._bus = bus
        self._services = services             # e.g. {"llm": "http://llm:8000/health"}
        self._interval = interval_s
        self._threshold = failure_threshold
        self._stability_window = stability_window_s
        # U266: which signals may declare him unable to THINK.
        #
        # Every registered service is still pinged and still reports — the UI
        # wants to know the robot dropped off WiFi. But the signals do not all
        # mean the same thing, and the brain watched exactly one: the robot's
        # /health. A robot on WiFi blinks out for ninety seconds, the mode goes
        # DEGRADED and then straight to OFFLINE (with a single signal, "any
        # failing" and "all failing" are the same sentence), and from then on
        # every turn short-circuits past the LLM into the regex fallback —
        # "I'm operating in limited offline mode…" — while the key, the network
        # and the model were all fine. Reported from the middle of a talk.
        #
        # A body that is not plugged in is not a mind that cannot think.
        # An empty set means nothing can degrade him, which is the honest
        # default when no upstream health URL is configured: make the call and
        # report the real error, rather than refusing up front on a guess.
        self._essential = set(essential) if essential is not None else set(services)

        self._failures: dict[str, int] = defaultdict(int)
        self._mode: RobotMode = RobotMode.ONLINE
        self._task: asyncio.Task | None = None

        # timestamps for mode transitions
        self._degraded_since: float | None = None
        self._recovering_since: float | None = None

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        """Schedule the heartbeat loop as a background asyncio task."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop(), name="heartbeat-monitor")

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    # ------------------------------------------------------------------ #
    # Public mode accessor
    # ------------------------------------------------------------------ #

    @property
    def mode(self) -> RobotMode:
        return self._mode

    # ------------------------------------------------------------------ #
    # Core loop
    # ------------------------------------------------------------------ #

    async def _loop(self) -> None:
        while True:
            await self._run_once()
            await asyncio.sleep(self._interval)

    async def _run_once(self) -> None:
        """Run one heartbeat cycle across all services."""
        results: dict[str, bool] = {}
        async with httpx.AsyncClient(timeout=5.0) as client:
            for name, url in self._services.items():
                results[name] = await self._check(client, name, url)

        # U266: only the essential signals move the mode. The rest are pinged
        # and reported — the console still shows a robot that fell off WiFi —
        # but they no longer decide whether he is allowed to think.
        watched = self._essential
        all_healthy = all(results[n] for n in watched if n in results)
        any_degraded = any(self._failures[n] >= self._threshold for n in watched)
        # All monitored signals (e.g. brain↔robot link AND upstream internet) down.
        all_failing = bool(watched) and all(
            self._failures[n] >= self._threshold for n in watched
        )

        await self._transition(all_healthy, any_degraded, all_failing)

    @property
    def failing(self) -> list[str]:
        """Signals currently over the failure threshold — the reason, by name."""
        return sorted(n for n in self._services if self._failures[n] >= self._threshold)

    async def _check(self, client: httpx.AsyncClient, name: str, url: str) -> bool:
        """Ping one service; emit heartbeat event; return True if healthy."""
        t0 = time.monotonic()
        try:
            resp = await client.get(url)
            latency_ms = (time.monotonic() - t0) * 1000
            if resp.is_success:
                self._failures[name] = 0
                await self._bus.publish(
                    BackendHeartbeatOk(service=name, latency_ms=round(latency_ms, 1))
                )
                return True
            raise httpx.HTTPStatusError("non-2xx", request=resp.request, response=resp)
        except Exception as exc:
            self._failures[name] += 1
            logger.warning(
                "Heartbeat %s failed (attempt %d): %s",
                name, self._failures[name], exc,
            )
            await self._bus.publish(
                BackendHeartbeatFailed(
                    service=name,
                    consecutive_failures=self._failures[name],
                )
            )
            return False

    async def _transition(
        self, all_healthy: bool, any_degraded: bool, all_failing: bool = False
    ) -> None:
        """Apply mode state machine transitions.

        ONLINE → DEGRADED   (any monitored signal fails)
        DEGRADED → OFFLINE  (ALL signals down — fully cut off; e.g. robot link AND
                             internet both gone)
        DEGRADED/OFFLINE → RECOVERING → ONLINE  (recovery)
        DEGRADED → MAINTENANCE (>= 24h degraded)
        """
        now = time.monotonic()

        if self._mode == RobotMode.ONLINE:
            if any_degraded:
                self._degraded_since = now
                await self._set_mode(RobotMode.DEGRADED)

        elif self._mode == RobotMode.DEGRADED:
            # Check 24-hour maintenance threshold
            if self._degraded_since and (now - self._degraded_since) >= _MAINTENANCE_THRESHOLD_S:
                await self._set_mode(RobotMode.MAINTENANCE)
                return
            if all_failing:
                await self._set_mode(RobotMode.OFFLINE)
                return
            if all_healthy:
                self._recovering_since = now
                await self._set_mode(RobotMode.RECOVERING)

        elif self._mode == RobotMode.OFFLINE:
            if all_healthy:
                self._recovering_since = now
                await self._set_mode(RobotMode.RECOVERING)

        elif self._mode == RobotMode.RECOVERING:
            if not all_healthy:
                # Lost health again — drop back to DEGRADED
                self._degraded_since = now
                self._recovering_since = None
                await self._set_mode(RobotMode.DEGRADED)
            elif self._recovering_since and (now - self._recovering_since) >= self._stability_window:
                self._recovering_since = None
                self._degraded_since = None
                await self._set_mode(RobotMode.ONLINE)

    async def _set_mode(self, new_mode: RobotMode) -> None:
        old_mode = self._mode
        self._mode = new_mode
        logger.info("Robot mode: %s → %s", old_mode.value, new_mode.value)
        await self._bus.publish(
            RobotModeChanged(from_mode=old_mode, to_mode=new_mode)
        )
