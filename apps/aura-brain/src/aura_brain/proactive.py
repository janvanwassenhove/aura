"""U110: proactive Richie — speak from his own initiative.

Until now Richie only spoke in reply to a wake-word turn. Reminders fired on the
bus (ReminderTriggered) but nothing voiced them. This engine gives Richie
initiative: it voices due reminders and an optional daily briefing by publishing
a ResponseDrafted event — reusing the whole embodiment/TTS pipeline (which
already respects sleep mode), so proactive speech looks exactly like a reply.

Gating (so he's helpful, not annoying):
  - PROACTIVE_ENABLED (default true) — master switch, read live.
  - ROBOT_ASLEEP — never speak while asleep.
  - quiet hours PROACTIVE_QUIET_START/END ("HH:MM") — silent overnight.
The daily briefing time is PROACTIVE_BRIEFING_TIME ("HH:MM", empty = off).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Awaitable, Callable

from shared_schemas.events.conversation import ResponseDrafted

logger = logging.getLogger(__name__)

NowFn = Callable[[], datetime]


def _parse_hhmm(value: str) -> tuple[int, int] | None:
    try:
        h, m = value.strip().split(":")
        h, m = int(h), int(m)
        if 0 <= h < 24 and 0 <= m < 60:
            return h, m
    except (ValueError, AttributeError):
        pass
    return None


def _in_quiet_hours(now: datetime, start: str, end: str) -> bool:
    s, e = _parse_hhmm(start), _parse_hhmm(end)
    if s is None or e is None:
        return False
    cur = now.hour * 60 + now.minute
    a, b = s[0] * 60 + s[1], e[0] * 60 + e[1]
    if a == b:
        return False
    return a <= cur < b if a < b else (cur >= a or cur < b)  # wraps past midnight


class ProactiveEngine:
    def __init__(self, bus, session_id: str, now_fn: NowFn | None = None) -> None:
        self._bus = bus
        self._session_id = session_id
        self._now = now_fn or datetime.now
        self._last_briefing_day: str | None = None

    # -- gating ----------------------------------------------------------

    def enabled(self) -> bool:
        return os.environ.get("PROACTIVE_ENABLED", "true").lower() == "true"

    def should_speak(self, now: datetime | None = None) -> bool:
        if not self.enabled():
            return False
        if os.environ.get("ROBOT_ASLEEP", "false").lower() == "true":
            return False
        now = now or self._now()
        return not _in_quiet_hours(
            now,
            os.environ.get("PROACTIVE_QUIET_START", ""),
            os.environ.get("PROACTIVE_QUIET_END", ""),
        )

    # -- speaking --------------------------------------------------------

    async def announce(self, text: str) -> bool:
        """Voice a proactive line (unless gated). Returns whether it spoke."""
        text = (text or "").strip()
        if not text or not self.should_speak():
            return False
        await self._bus.publish(ResponseDrafted(
            session_id=self._session_id, response_text=text,
        ))
        logger.info("proactive: %s", text[:80])
        return True

    async def on_reminder(self, event) -> None:
        """Speak a fired reminder (ReminderTriggered handler)."""
        msg = getattr(event, "message", None) or getattr(event, "text", "")
        if msg:
            await self.announce(f"Even een herinnering: {msg}")

    # -- daily briefing --------------------------------------------------

    def briefing_due(self, now: datetime | None = None) -> bool:
        """True at most once per day, when the clock reaches the briefing time."""
        target = _parse_hhmm(os.environ.get("PROACTIVE_BRIEFING_TIME", ""))
        if target is None:
            return False
        now = now or self._now()
        day = now.date().isoformat()
        if self._last_briefing_day == day:
            return False
        # Fire once the target minute has arrived (and within the same hour, so a
        # slow poll doesn't miss it or repeat it across hours).
        if now.hour == target[0] and now.minute >= target[1]:
            self._last_briefing_day = day
            return True
        return False

    async def maybe_briefing(self, build_brief: Callable[[], Awaitable[str]]) -> bool:
        if not self.briefing_due():
            return False
        try:
            text = await build_brief()
        except Exception as exc:  # noqa: BLE001 — briefing must never crash the loop
            logger.debug("briefing build failed: %s", exc)
            return False
        return await self.announce(text)
