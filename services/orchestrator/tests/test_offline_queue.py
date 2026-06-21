"""Tests for OfflineQueue — persistent SQLite action queue."""

from __future__ import annotations

import asyncio
import uuid

import pytest

from orchestrator.offline_queue import MAX_QUEUE_SIZE, OfflineQueue
from shared_events.bus import AsyncEventBus
from shared_schemas.events.orchestrator import ApprovalRequested
from shared_schemas.events.system import OfflineQueueSyncCompleted, OfflineQueueSyncStarted


@pytest.fixture
async def bus():
    b = AsyncEventBus()
    await b.start()
    yield b
    await b.stop()


@pytest.fixture
async def queue(bus):
    q = OfflineQueue(bus, db_path=":memory:")
    await q.open()
    yield q
    await q.close()


# --------------------------------------------------------------------------- #
# Basic enqueue / pending
# --------------------------------------------------------------------------- #

async def test_enqueue_adds_item(queue):
    action = await queue.enqueue("list_todos", {})
    assert action is not None
    assert action.tool_name == "list_todos"
    assert await queue.depth() == 1


async def test_multiple_enqueue(queue):
    await queue.enqueue("list_todos", {})
    await queue.enqueue("list_reminders", {})
    assert await queue.depth() == 2
    items = await queue.pending()
    assert [i.tool_name for i in items] == ["list_todos", "list_reminders"]


async def test_cancel_removes_from_pending(queue):
    action = await queue.enqueue("list_todos", {})
    ok = await queue.cancel(action.id)
    assert ok is True
    assert await queue.depth() == 0


async def test_cancel_nonexistent_returns_false(queue):
    ok = await queue.cancel(str(uuid.uuid4()))
    assert ok is False


# --------------------------------------------------------------------------- #
# Queue cap
# --------------------------------------------------------------------------- #

async def test_queue_full_rejects_new_items(queue):
    for i in range(MAX_QUEUE_SIZE):
        result = await queue.enqueue("list_todos", {"i": i})
        assert result is not None

    overflow = await queue.enqueue("list_todos", {})
    assert overflow is None
    assert await queue.depth() == MAX_QUEUE_SIZE


# --------------------------------------------------------------------------- #
# sync_on_reconnect — sensitive actions require approval
# --------------------------------------------------------------------------- #

async def test_sync_emits_approval_for_sensitive_action(bus, queue):
    approval_events: list[ApprovalRequested] = []
    bus.subscribe(ApprovalRequested, lambda e: approval_events.append(e))

    await queue.enqueue("send_mail", {"to": "alice@example.com", "subject": "Hi"})

    connector_calls: list = []

    async def fake_connector(tool_name, arguments):
        connector_calls.append(tool_name)

    await queue.sync_on_reconnect("session-1", fake_connector)
    await asyncio.sleep(0)

    assert len(approval_events) == 1
    assert approval_events[0].tool_name == "send_mail"
    # Sensitive action should NOT be auto-executed
    assert connector_calls == []


# --------------------------------------------------------------------------- #
# sync_on_reconnect — read-only actions auto-execute
# --------------------------------------------------------------------------- #

async def test_sync_auto_executes_readonly_action(bus, queue):
    await queue.enqueue("list_todos", {})

    executed: list = []

    async def fake_connector(tool_name, arguments):
        executed.append(tool_name)

    await queue.sync_on_reconnect("session-1", fake_connector)
    await asyncio.sleep(0)

    assert "list_todos" in executed
    # Should be marked as executed (no longer pending)
    assert await queue.depth() == 0


# --------------------------------------------------------------------------- #
# sync_on_reconnect — emits start/complete events
# --------------------------------------------------------------------------- #

async def test_sync_emits_start_and_complete_events(bus, queue):
    starts: list = []
    completes: list = []
    bus.subscribe(OfflineQueueSyncStarted, lambda e: starts.append(e))
    bus.subscribe(OfflineQueueSyncCompleted, lambda e: completes.append(e))

    await queue.enqueue("list_todos", {})

    async def fake_connector(tool_name, arguments):
        pass

    await queue.sync_on_reconnect("session-1", fake_connector)
    await asyncio.sleep(0)

    assert len(starts) == 1
    assert len(completes) == 1
    assert completes[0].synced_count == 1


# --------------------------------------------------------------------------- #
# sync_on_reconnect — multiple sensitive items in queue order
# --------------------------------------------------------------------------- #

async def test_sync_multiple_sensitive_actions_ordered(bus, queue):
    approval_events: list = []
    bus.subscribe(ApprovalRequested, lambda e: approval_events.append(e))

    await queue.enqueue("send_mail", {"to": "a@example.com"})
    await queue.enqueue("post_teams_message", {"channel": "general", "text": "hi"})

    async def noop_connector(tool_name, arguments):
        pass

    await queue.sync_on_reconnect("session-1", noop_connector)
    await asyncio.sleep(0)

    assert len(approval_events) == 2
    assert approval_events[0].tool_name == "send_mail"
    assert approval_events[1].tool_name == "post_teams_message"
