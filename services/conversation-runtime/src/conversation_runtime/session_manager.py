"""SessionManager — tracks active conversation sessions."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


@dataclass
class Session:
    session_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_active: datetime = field(default_factory=lambda: datetime.now(UTC))
    turn_count: int = 0


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def create(self) -> Session:
        session_id = str(uuid.uuid4())
        session = Session(session_id=session_id)
        self._sessions[session_id] = session
        logger.info("Session created: %s", session_id)
        return session

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def get_or_create(self, session_id: str) -> Session:
        if session_id not in self._sessions:
            session = Session(session_id=session_id)
            self._sessions[session_id] = session
        return self._sessions[session_id]

    def touch(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if session:
            session.last_active = datetime.now(UTC)
            session.turn_count += 1

    def end(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        logger.info("Session ended: %s", session_id)

    def active_count(self) -> int:
        return len(self._sessions)
