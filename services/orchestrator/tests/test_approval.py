"""Tests for ApprovalManager."""

from __future__ import annotations

import asyncio

import pytest

from orchestrator.approval_manager import ApprovalDeniedError, ApprovalManager, ApprovalTimeout
from shared_events.bus import AsyncEventBus
from shared_schemas.events.orchestrator import ApprovalRequested


@pytest.fixture()
async def bus() -> AsyncEventBus:
    b = AsyncEventBus()
    await b.start()
    yield b
    await b.stop()


@pytest.fixture()
def manager(bus: AsyncEventBus) -> ApprovalManager:
    return ApprovalManager(bus, session_id="test-session")


async def test_needs_approval_for_send_mail(manager: ApprovalManager) -> None:
    assert manager.needs_approval("send_mail") is True


async def test_no_approval_for_read_tool(manager: ApprovalManager) -> None:
    assert manager.needs_approval("list_calendar_events_today") is False


async def test_grant_resolves_request(manager: ApprovalManager) -> None:
    # Fire-and-forget the grant so we resolve it just after request starts
    async def _grant_later() -> None:
        await asyncio.sleep(0.05)
        # Find the pending approval_id from the events emitted
        pending_ids = list(manager._pending.keys())
        if pending_ids:
            await manager.grant(pending_ids[0])

    task = asyncio.create_task(_grant_later())
    result = await manager.request_approval("send_mail", {"to": "alice@example.com"})
    await task
    assert result is True


async def test_deny_raises_error(manager: ApprovalManager) -> None:
    async def _deny_later() -> None:
        await asyncio.sleep(0.05)
        pending_ids = list(manager._pending.keys())
        if pending_ids:
            await manager.deny(pending_ids[0])

    task = asyncio.create_task(_deny_later())
    with pytest.raises(ApprovalDeniedError):
        await manager.request_approval("post_teams_message", {})
    await task


async def test_timeout_raises_error(bus: AsyncEventBus) -> None:
    # Use a very short timeout by monkey-patching the constant
    import orchestrator.approval_manager as am_mod
    original = am_mod._APPROVAL_TIMEOUT_S
    am_mod._APPROVAL_TIMEOUT_S = 0.1
    try:
        mgr = ApprovalManager(bus, session_id="timeout-test")
        with pytest.raises(ApprovalTimeout):
            await mgr.request_approval("send_mail", {})
    finally:
        am_mod._APPROVAL_TIMEOUT_S = original


async def test_approval_emits_requested_event(bus: AsyncEventBus, manager: ApprovalManager) -> None:
    events: list[ApprovalRequested] = []

    async def _capture(event: ApprovalRequested) -> None:
        events.append(event)

    bus.subscribe(ApprovalRequested, _capture)

    # Start request (will time out quickly)
    import orchestrator.approval_manager as am_mod
    original = am_mod._APPROVAL_TIMEOUT_S
    am_mod._APPROVAL_TIMEOUT_S = 0.05
    try:
        with pytest.raises(ApprovalTimeout):
            await manager.request_approval("send_mail", {})
    finally:
        am_mod._APPROVAL_TIMEOUT_S = original

    assert len(events) == 1
    assert events[0].tool_name == "send_mail"
