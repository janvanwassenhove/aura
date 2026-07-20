"""OfflineQueue — persistent SQLite queue for actions queued while offline.

Stores pending tool calls so they survive service restarts (FR-003).
On reconnect, processes each item:
  - Sensitive actions (APPROVAL_REQUIRED) → emit ApprovalRequested (FR-005)
  - Read-only actions → execute automatically via connector service (FR-006)

Queue is capped at MAX_QUEUE_SIZE items (FR edge case).
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import aiosqlite
from shared_events.bus import AsyncEventBus
from shared_policies import APPROVAL_REQUIRED
from shared_schemas.events.orchestrator import ApprovalRequested
from shared_schemas.events.system import OfflineQueueSyncCompleted, OfflineQueueSyncStarted

logger = logging.getLogger(__name__)

MAX_QUEUE_SIZE = 50
_DEFAULT_DB = os.environ.get("OFFLINE_QUEUE_DB", ":memory:")


@dataclass
class QueuedAction:
    id: str
    tool_name: str
    arguments: dict
    queued_at: str
    status: str = "pending"   # pending | cancelled | executed


class OfflineQueue:
    """Persistent queue of offline actions backed by SQLite."""

    def __init__(self, bus: AsyncEventBus, db_path: str = _DEFAULT_DB) -> None:
        self._bus = bus
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    async def open(self) -> None:
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS offline_queue (
                id          TEXT PRIMARY KEY,
                tool_name   TEXT NOT NULL,
                arguments   TEXT NOT NULL DEFAULT '{}',
                queued_at   TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'pending'
            )
            """
        )
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    # ------------------------------------------------------------------ #
    # Enqueue / cancel
    # ------------------------------------------------------------------ #

    async def enqueue(self, tool_name: str, arguments: dict) -> QueuedAction | None:
        """Add an action to the queue.  Returns None if the queue is full."""
        depth = await self.depth()
        if depth >= MAX_QUEUE_SIZE:
            logger.warning("Offline queue full (%d/%d); rejecting %r", depth, MAX_QUEUE_SIZE, tool_name)
            return None

        action = QueuedAction(
            id=str(uuid.uuid4()),
            tool_name=tool_name,
            arguments=arguments,
            queued_at=datetime.now(tz=UTC).isoformat(),
        )
        await self._db.execute(
            "INSERT INTO offline_queue (id, tool_name, arguments, queued_at, status) VALUES (?,?,?,?,?)",
            (action.id, action.tool_name, json.dumps(action.arguments), action.queued_at, action.status),
        )
        await self._db.commit()
        return action

    async def cancel(self, item_id: str) -> bool:
        """Mark an item as cancelled.  Returns True if the item was found."""
        cur = await self._db.execute(
            "UPDATE offline_queue SET status='cancelled' WHERE id=? AND status='pending'",
            (item_id,),
        )
        await self._db.commit()
        return cur.rowcount > 0

    # ------------------------------------------------------------------ #
    # Query helpers
    # ------------------------------------------------------------------ #

    async def depth(self) -> int:
        cur = await self._db.execute("SELECT COUNT(*) FROM offline_queue WHERE status='pending'")
        row = await cur.fetchone()
        return row[0]

    async def pending(self) -> list[QueuedAction]:
        cur = await self._db.execute(
            "SELECT id, tool_name, arguments, queued_at, status "
            "FROM offline_queue WHERE status='pending' ORDER BY queued_at ASC"
        )
        rows = await cur.fetchall()
        return [
            QueuedAction(
                id=r["id"],
                tool_name=r["tool_name"],
                arguments=json.loads(r["arguments"]),
                queued_at=r["queued_at"],
                status=r["status"],
            )
            for r in rows
        ]

    # ------------------------------------------------------------------ #
    # Reconnect / sync
    # ------------------------------------------------------------------ #

    async def sync_on_reconnect(
        self,
        session_id: str,
        connector_fn,   # async callable(tool_name, arguments) -> str
    ) -> int:
        """Process all pending items.

        Sensitive actions emit ApprovalRequested and are left as 'pending'
        (the approval flow will complete them externally).
        Read-only actions are executed immediately via *connector_fn*.

        Returns the number of items processed.
        """
        items = await self.pending()
        await self._bus.publish(OfflineQueueSyncStarted())
        synced = 0

        for item in items:
            if item.tool_name in APPROVAL_REQUIRED:
                # Require fresh approval — emit event, leave in queue
                await self._bus.publish(
                    ApprovalRequested(
                        session_id=session_id,
                        approval_id=uuid.UUID(item.id),
                        tool_name=item.tool_name,
                        arguments_summary=json.dumps(item.arguments)[:200],
                    )
                )
            else:
                # Read-only: execute automatically
                try:
                    await connector_fn(item.tool_name, item.arguments)
                    await self._mark_executed(item.id)
                except Exception as exc:
                    logger.warning("Offline queue auto-exec failed for %r: %s", item.tool_name, exc)
            synced += 1

        await self._bus.publish(OfflineQueueSyncCompleted(synced_count=synced))
        return synced

    async def _mark_executed(self, item_id: str) -> None:
        await self._db.execute(
            "UPDATE offline_queue SET status='executed' WHERE id=?", (item_id,)
        )
        await self._db.commit()
