"""U48: 'always allow' approval memory."""

from __future__ import annotations

import asyncio

import pytest

from orchestrator.approval_manager import ApprovalManager
from shared_events.bus import AsyncEventBus


@pytest.fixture()
async def bus():
    b = AsyncEventBus()
    await b.start()
    yield b
    await b.stop()


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("AUTO_APPROVE_TOOLS", raising=False)


async def test_remembered_tool_auto_approves(bus, monkeypatch) -> None:
    monkeypatch.setenv("AUTO_APPROVE_TOOLS", "launch_app")
    mgr = ApprovalManager(bus, session_id="s")
    # No pending future is created; it returns immediately.
    assert await mgr.request_approval("launch_app", {"name": "spotify"}) is True
    assert mgr.needs_approval("launch_app") is False


async def test_grant_with_remember_persists(bus, monkeypatch) -> None:
    writes = {}
    import aura_brain.setup_api as setup_api
    monkeypatch.setattr(setup_api, "_write_env", lambda d: writes.update(d) or True)

    mgr = ApprovalManager(bus, session_id="s")
    task = asyncio.create_task(mgr.request_approval("send_mail", {"to": "x"}))
    await asyncio.sleep(0.05)
    approval_id = next(iter(mgr._pending))
    await mgr.grant(approval_id, remember=True)
    assert await task is True
    assert "send_mail" in mgr.auto_approved()
    assert writes.get("AUTO_APPROVE_TOOLS") == "send_mail"
    # A second call now auto-approves without a pending entry.
    assert await mgr.request_approval("send_mail", {"to": "y"}) is True


async def test_set_auto_toggle(bus) -> None:
    mgr = ApprovalManager(bus, session_id="s")
    mgr.set_auto("launch_app", True)
    assert mgr.auto_approved() == ["launch_app"]
    mgr.set_auto("launch_app", False)
    assert mgr.auto_approved() == []


async def test_grant_without_remember_does_not_persist(bus) -> None:
    mgr = ApprovalManager(bus, session_id="s")
    task = asyncio.create_task(mgr.request_approval("send_mail", {"to": "x"}))
    await asyncio.sleep(0.05)
    approval_id = next(iter(mgr._pending))
    await mgr.grant(approval_id, remember=False)
    assert await task is True
    assert mgr.auto_approved() == []
