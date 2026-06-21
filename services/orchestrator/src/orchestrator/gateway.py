"""GatewayManager — API key auth, per-key rate limiting, command dispatch, audit log."""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from collections import defaultdict, deque
from datetime import UTC, datetime

from shared_schemas.gateway.models import (
    AuditEntry,
    CommandStatus,
    GatewayAction,
    GatewayCommand,
    SENSITIVE_ACTIONS,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class GatewayAuthError(PermissionError):
    """Invalid or revoked API key."""


class GatewayRateLimitError(Exception):
    """Rate limit exceeded for the given key.

    Attributes:
        retry_after: seconds until the window resets.
    """

    def __init__(self, retry_after: float = 1.0) -> None:
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded; retry after {retry_after:.1f}s")


class GatewayModeError(Exception):
    """AURA is in a mode that rejects external commands (OFFLINE/MAINTENANCE)."""

    def __init__(self, mode: str, retry_after: int = 30) -> None:
        self.mode = mode
        self.retry_after = retry_after
        super().__init__(f"AURA is in {mode} mode")


class GatewayActionError(ValueError):
    """Unknown or unsupported action type."""


# ---------------------------------------------------------------------------
# Rate limiter — sliding window, per key
# ---------------------------------------------------------------------------


class _SlidingWindow:
    """Sliding-window rate limiter — thread-safe for asyncio (single-threaded)."""

    def __init__(self, limit: int, window_s: float) -> None:
        self._limit = limit
        self._window_s = window_s
        self._timestamps: deque[float] = deque()

    def allow(self) -> tuple[bool, float]:
        """Return (allowed, retry_after_seconds)."""
        now = time.monotonic()
        cutoff = now - self._window_s
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()
        if len(self._timestamps) >= self._limit:
            oldest = self._timestamps[0]
            retry_after = self._window_s - (now - oldest)
            return False, max(0.0, retry_after)
        self._timestamps.append(now)
        return True, 0.0


# ---------------------------------------------------------------------------
# GatewayManager
# ---------------------------------------------------------------------------


class GatewayManager:
    """Validates API keys, enforces rate limits, dispatches commands, and audits.

    SECURITY:
    - API key comparison uses ``hmac.compare_digest`` (constant-time) to prevent
      timing attacks (FR-005).
    - Audit entries NEVER contain payload content for sensitive actions (FR-007).
    - API keys are stored as their SHA-256 hex digest; raw key values are never
      retained in memory beyond the initial comparison.

    Args:
        api_keys: mapping of ``key_id -> raw_key_value``.  The key_id is the
                  opaque label stored in the audit log; the value is what the
                  caller presents.
        rate_limit: max commands per key per second (default 10, FR-006).
        blocked_modes: AURA modes that cause 503 (FR-009).
    """

    def __init__(
        self,
        api_keys: dict[str, str] | None = None,
        rate_limit: int = 10,
        window_s: float = 1.0,
        blocked_modes: frozenset[str] = frozenset({"OFFLINE", "MAINTENANCE"}),
    ) -> None:
        # Store digest -> key_id mapping for O(1) lookup without storing raw key
        self._key_digests: dict[str, str] = {}
        for key_id, raw_key in (api_keys or {}).items():
            digest = self._digest(raw_key)
            self._key_digests[digest] = key_id

        self._rate_limiters: dict[str, _SlidingWindow] = defaultdict(
            lambda: _SlidingWindow(rate_limit, window_s)
        )
        self._rate_limit = rate_limit
        self._window_s = window_s
        self._blocked_modes = blocked_modes
        self._audit: list[AuditEntry] = []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _digest(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode()).hexdigest()

    def _authenticate(self, raw_key: str) -> str:
        """Return key_id for *raw_key* or raise GatewayAuthError.

        Uses constant-time comparison (OWASP A07).
        """
        incoming_digest = self._digest(raw_key)
        for stored_digest, key_id in self._key_digests.items():
            if hmac.compare_digest(incoming_digest, stored_digest):
                return key_id
        raise GatewayAuthError("Invalid API key")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_key(self, key_id: str, raw_key: str) -> None:
        """Add or replace an API key at runtime."""
        self._key_digests[self._digest(raw_key)] = key_id

    def revoke_key(self, key_id: str) -> None:
        """Revoke all digests associated with *key_id*."""
        to_remove = [d for d, kid in self._key_digests.items() if kid == key_id]
        for d in to_remove:
            del self._key_digests[d]

    def dispatch(
        self,
        raw_key: str,
        action_str: str,
        payload: dict,
        priority: str = "normal",
        current_mode: str = "ONLINE",
    ) -> tuple[GatewayCommand, AuditEntry]:
        """Validate, rate-limit, and record a gateway command.

        Returns (GatewayCommand, AuditEntry) if the command passes all checks.
        Raises GatewayAuthError, GatewayRateLimitError, GatewayModeError, or
        GatewayActionError as appropriate.

        SECURITY: payload is never written to the audit log for sensitive actions.
        """
        # 1. Authenticate
        key_id = self._authenticate(raw_key)

        # 2. Mode check (FR-009)
        if current_mode.upper() in self._blocked_modes:
            raise GatewayModeError(current_mode)

        # 3. Rate limit (FR-006)
        allowed, retry_after = self._rate_limiters[key_id].allow()
        if not allowed:
            raise GatewayRateLimitError(retry_after)

        # 4. Action validation
        try:
            action = GatewayAction(action_str)
        except ValueError:
            raise GatewayActionError(f"Unknown action: {action_str!r}")

        # 5. Build command
        cmd = GatewayCommand(
            action=action,
            payload=payload,
            priority=priority,  # type: ignore[arg-type]
            api_key_id=key_id,
        )

        is_sensitive = action in SENSITIVE_ACTIONS

        # 6. Record audit (FR-003, FR-007 — no payload for sensitive)
        entry = AuditEntry(
            action_type=action,
            key_id=key_id,
            status=CommandStatus.RECEIVED,
            mode_at_time=current_mode,
            is_sensitive=is_sensitive,
        )
        self._audit.append(entry)
        logger.info(
            "Gateway command received: action=%s key_id=%s sensitive=%s",
            action,
            key_id,
            is_sensitive,
        )

        return cmd, entry

    def update_audit_status(self, entry_id: str, status: CommandStatus) -> None:
        """Update the status of an existing audit entry in-place."""
        for entry in self._audit:
            if entry.entry_id == entry_id:
                entry.status = status
                return

    def get_audit_log(self, limit: int = 20) -> list[AuditEntry]:
        """Return the last *limit* audit entries (most recent last)."""
        return list(self._audit[-limit:])
