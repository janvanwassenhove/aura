"""FallbackAgent — pattern-matching command handler for offline mode.

Used by the orchestrator pipeline when the LLM is unavailable (DEGRADED mode).
Handles a predefined set of commands via regex matching; returns text replies
and may create reminders via the memory service if reachable.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Patterns (order matters — first match wins)
# --------------------------------------------------------------------------- #

_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Current time
    (re.compile(r"\b(what('s| is) the time|what time is it|current time)\b", re.I), "time"),
    # Set reminder  e.g. "remind me to X at/in Y"
    (re.compile(r"\b(remind me|set a reminder|reminder)\b", re.I), "reminder"),
    # Set timer  e.g. "set a timer for 5 minutes"
    (re.compile(r"\b(set a timer|timer for|start a timer)\b", re.I), "timer"),
    # Status query
    (re.compile(r"\b(status|how are you|are you ok|system status)\b", re.I), "status"),
    # Calendar / meetings (explain offline limitation)
    (re.compile(r"\b(meeting|calendar|schedule|appointment)\b", re.I), "calendar_offline"),
    # Mail / Teams (explain offline limitation)
    (re.compile(r"\b(email|mail|teams|message)\b", re.I), "comms_offline"),
]

# Match a time spec from a reminder command
_TIME_RE = re.compile(
    r"(?:at\s+)?(\d{1,2}(?::\d{2})?\s*(?:am|pm)?|\d{1,2}(?::\d{2}))"
    r"|(?:in\s+(\d+)\s*(minutes?|hours?))",
    re.I,
)

_REMINDER_BODY_RE = re.compile(
    r"remind(?:er)?\s+(?:me\s+)?(?:to\s+)?(.+?)(?:\s+(?:at|in)\s+|\s*$)",
    re.I,
)


class FallbackAgent:
    """Offline pattern-matching agent."""

    def __init__(self) -> None:
        self._memory_url = os.environ.get(
            "MEMORY_SERVICE_URL", "http://memory-service:8005"
        )

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    async def handle(self, text: str, session_id: str) -> str:
        """Process *text* and return a text reply.  Never raises."""
        intent = self._classify(text)
        handler = {
            "time": self._handle_time,
            "reminder": self._handle_reminder,
            "timer": self._handle_timer,
            "status": self._handle_status,
            "calendar_offline": self._handle_calendar_offline,
            "comms_offline": self._handle_comms_offline,
        }.get(intent, self._handle_unknown)
        try:
            return await handler(text, session_id)
        except Exception as exc:
            logger.warning("FallbackAgent error for intent %r: %s", intent, exc)
            return (
                "I'm operating in limited offline mode and couldn't complete that request. "
                "Please try again when connectivity is restored."
            )

    # ------------------------------------------------------------------ #
    # Classification
    # ------------------------------------------------------------------ #

    def _classify(self, text: str) -> str:
        for pattern, intent in _PATTERNS:
            if pattern.search(text):
                return intent
        return "unknown"

    # ------------------------------------------------------------------ #
    # Handlers
    # ------------------------------------------------------------------ #

    async def _handle_time(self, text: str, session_id: str) -> str:
        now = datetime.now().strftime("%I:%M %p")
        return f"The current time is {now}."

    async def _handle_reminder(self, text: str, session_id: str) -> str:
        # Extract reminder body
        body_match = _REMINDER_BODY_RE.search(text)
        body = body_match.group(1).strip() if body_match else text.strip()

        # Try to persist via memory service
        saved = await self._create_reminder(body, session_id)
        if saved:
            return f"Reminder set: \"{body}\". I'll remind you when the time comes."
        return (
            f"I've noted your reminder: \"{body}\". "
            "Note: I'm offline and the reminder may not persist across restarts."
        )

    async def _handle_timer(self, text: str, session_id: str) -> str:
        time_match = _TIME_RE.search(text)
        if time_match and time_match.group(2):
            amount = time_match.group(2)
            unit = time_match.group(3) or "minutes"
            return (
                f"I'd normally set a {amount}-{unit} timer, but I'm in offline mode "
                "and cannot run timers right now. Please use another timer."
            )
        return (
            "I'm in offline mode and cannot set timers right now. "
            "Please use another device to set your timer."
        )

    async def _handle_status(self, text: str, session_id: str) -> str:
        return (
            "I'm currently operating in degraded offline mode. "
            "LLM and cloud services are unreachable. "
            "Basic commands (time, reminders) are available locally."
        )

    async def _handle_calendar_offline(self, text: str, session_id: str) -> str:
        return (
            "I cannot retrieve calendar information while offline. "
            "Please check your calendar app directly."
        )

    async def _handle_comms_offline(self, text: str, session_id: str) -> str:
        return (
            "I cannot send messages or access email while offline. "
            "Please restore connectivity and try again."
        )

    async def _handle_unknown(self, text: str, session_id: str) -> str:
        return (
            "I'm operating in limited offline mode. I can help with: "
            "current time, setting reminders, and system status. "
            "Other requests require connectivity."
        )

    # ------------------------------------------------------------------ #
    # Memory service integration (best-effort)
    # ------------------------------------------------------------------ #

    async def _create_reminder(self, message: str, session_id: str) -> bool:
        """Attempt to create a reminder in the memory service.  Returns True on success."""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.post(
                    f"{self._memory_url}/memory/reminders",
                    json={"session_id": session_id, "message": message},
                )
                return resp.is_success
        except Exception as exc:
            logger.debug("Memory service unreachable for reminder: %s", exc)
            return False
