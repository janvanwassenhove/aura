"""Self-maintenance loop (U36g): the brain checks and heals itself.

Every MAINTENANCE_INTERVAL_S (default 300 s) it verifies the health of every
subsystem and takes recovery actions where it safely can:

  - robot link down → try to (re)connect robot-runtime's adapter,
  - LLM/TTS keys missing → flagged in the report,
  - knowledge store unencrypted → gentle nudge in the report,
  - expired sightings → purged (SightingLog does this on access).

Each pass publishes a ``MaintenanceReport`` event so the console's event log
shows the brain looking after itself. Reports never contain secrets.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from aura_brain import deploy_skew

logger = logging.getLogger(__name__)


class MaintenanceLoop:
    def __init__(
        self,
        bus: Any,
        robot: Any,                 # RobotClient
        knowledge_encrypted: Any,   # Callable[[], bool]
        session_id: str = "default",
        interval_s: float = 300.0,
        skill_proposer: Any = None,   # U250: SkillProposer | None
    ) -> None:
        self._bus = bus
        self._robot = robot
        self._knowledge_encrypted = knowledge_encrypted
        self._session_id = session_id
        self._interval = interval_s
        self._proposer = skill_proposer
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())
            logger.info("MaintenanceLoop started (every %.0fs)", self._interval)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # the maintainer must not need maintenance
                logger.warning("maintenance tick failed: %s", exc)

    async def tick(self) -> dict:
        """One self-check pass. Public for tests; returns the report dict."""
        checks: dict[str, str] = {}
        actions: list[str] = []

        # Robot link — and self-heal by reconnecting the adapter if it's down.
        try:
            status = await self._robot.status()
            if status.get("connected"):
                checks["robot"] = "ok"
            else:
                checks["robot"] = "disconnected"
                try:
                    await self._robot.connect()
                    actions.append("reconnected robot adapter")
                    checks["robot"] = "recovered"
                except Exception:  # noqa: BLE001
                    actions.append("robot reconnect failed")
        except Exception:  # noqa: BLE001 — runtime unreachable
            checks["robot"] = "unreachable"

        # U240: is the robot running the code this brain expects? Reported, never
        # enforced — the Pi sat 74 commits behind for a month and the first sign
        # was a 404 that made a button do nothing (U238). A tick is the right
        # place: it already asks the robot how it is.
        try:
            skew = deploy_skew.compare(await self._robot.build())
            checks["robot_build"] = skew["state"]
            if skew["state"] == "behind":
                actions.append(f"robot needs a deploy — {skew['detail']}")
                logger.warning("deployment skew: %s", skew["detail"])
        except Exception:  # noqa: BLE001 — never let a version check break a tick
            checks["robot_build"] = "unknown"

        checks["llm_key"] = "ok" if os.environ.get("OPENAI_API_KEY") else "missing"
        checks["tts"] = checks["llm_key"]  # same credential today
        checks["knowledge"] = (
            "encrypted" if self._knowledge_encrypted() else "unencrypted (dev)"
        )

        # U240: `healthy` is about whether the system WORKS. A robot running
        # older code usually works fine, so deployment skew must not flip this
        # flag — it would leave the console permanently unhealthy over something
        # informational, and a warning light that is always on is not a warning
        # light. The drift is surfaced through `actions` instead, where it reads
        # as "here is something to do" rather than "something is broken".
        # U250: is any skill worth bringing up? Deliberately AFTER the health
        # checks and outside `healthy` — a procedure that could be better is
        # not a fault, and a warning light that is always on is not a warning
        # light (the same reasoning as robot_build in U240). It lands in
        # `actions`: "here is something to decide", not "something is broken".
        if self._proposer is not None:
            try:
                raised = await self._proposer.review()
                if raised:
                    actions.append(
                        f"skill proposal: {raised['kind']} '{raised['skill']}' — "
                        f"{raised['reason']}")
            except Exception as exc:  # noqa: BLE001 — never break a tick
                logger.debug("skill proposal review failed: %s", exc)

        _FUNCTIONAL = ("ok", "encrypted", "recovered")
        healthy = all(
            v in _FUNCTIONAL
            for name, v in checks.items()
            if name != "robot_build"
        )
        from shared_schemas.events.system import MaintenanceReport

        report = MaintenanceReport(
            session_id=self._session_id,
            healthy=healthy,
            checks=checks,
            actions=actions,
        )
        await self._bus.publish(report)
        logger.info("maintenance: healthy=%s checks=%s actions=%s",
                    healthy, checks, actions)
        return {"healthy": healthy, "checks": checks, "actions": actions}
