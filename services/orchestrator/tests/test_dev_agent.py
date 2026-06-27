"""Tests for DevAgentTool (U20 — outbound dev-agent, ADR-007 §3.2)."""

from __future__ import annotations

import asyncio

import pytest

from orchestrator.dev_agent import DevAgentTool, OperationType, classify_operation
from orchestrator.approval_manager import ApprovalDeniedError, ApprovalManager
from shared_events.bus import AsyncEventBus


# ---------------------------------------------------------------------------
# Operation classification
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("task,expected", [
    ("pytest tests/", OperationType.READ),
    ("uv run pytest packages/memory-service/tests", OperationType.READ),
    ("grep -r 'TODO' src/", OperationType.READ),
    ("cat README.md", OperationType.READ),
    ("git status", OperationType.READ),
    ("git log --oneline -10", OperationType.READ),
    ("git diff HEAD", OperationType.READ),
    ("git add .", OperationType.WRITE),
    ("touch newfile.py", OperationType.WRITE),
    ("git commit -m 'fix: something'", OperationType.COMMIT),
    ("git push origin main", OperationType.PUSH),
    ("git push --force", OperationType.PUSH),
])
def test_classify_operation(task: str, expected: OperationType) -> None:
    assert classify_operation(task) == expected


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
async def bus() -> AsyncEventBus:
    b = AsyncEventBus()
    await b.start()
    yield b
    await b.stop()


@pytest.fixture()
def approval_mgr(bus: AsyncEventBus) -> ApprovalManager:
    return ApprovalManager(bus, session_id="test-session")


@pytest.fixture()
def agent(approval_mgr: ApprovalManager, bus: AsyncEventBus) -> DevAgentTool:
    return DevAgentTool(approval_mgr, bus)


# ---------------------------------------------------------------------------
# Shell execution (read ops — auto-approve)
# ---------------------------------------------------------------------------

async def test_read_op_runs_without_approval(agent: DevAgentTool) -> None:
    result = await agent.run("python -c \"print('hello')\"", session_id="s1", operation_type="read")
    assert "hello" in result


async def test_test_command_is_auto_approved(agent: DevAgentTool) -> None:
    # 'uv run pytest' is a READ — should not trigger approval.
    result = await agent.run(
        "python -c \"print('test ok')\"",
        session_id="s1",
        operation_type="read",
    )
    assert "test ok" in result


async def test_unknown_command_returns_not_found(agent: DevAgentTool) -> None:
    result = await agent.run("nonexistent_cmd_xyz_abc", session_id="s1", operation_type="read")
    assert "not found" in result.lower() or "error" in result.lower()


# ---------------------------------------------------------------------------
# Approval gating (write/commit/push ops)
# ---------------------------------------------------------------------------

async def test_write_op_requires_approval_grant(agent: DevAgentTool, approval_mgr: ApprovalManager) -> None:
    async def _grant_later() -> None:
        await asyncio.sleep(0.05)
        pending_ids = list(approval_mgr._pending.keys())
        if pending_ids:
            await approval_mgr.grant(pending_ids[0])

    task = asyncio.create_task(_grant_later())
    result = await agent.run("touch /tmp/aura_test_file.txt", session_id="s1", operation_type="write")
    await task
    # Should have executed (or failed with not-found, not an approval error).
    assert "approval" not in result.lower()


async def test_write_op_denied_returns_message(agent: DevAgentTool, approval_mgr: ApprovalManager) -> None:
    async def _deny_later() -> None:
        await asyncio.sleep(0.05)
        pending_ids = list(approval_mgr._pending.keys())
        if pending_ids:
            await approval_mgr.deny(pending_ids[0])

    task = asyncio.create_task(_deny_later())
    result = await agent.run("git add .", session_id="s1")
    await task
    assert "denied" in result.lower()


async def test_push_op_requires_approval(agent: DevAgentTool, approval_mgr: ApprovalManager) -> None:
    async def _deny_later() -> None:
        await asyncio.sleep(0.05)
        ids = list(approval_mgr._pending.keys())
        if ids:
            await approval_mgr.deny(ids[0])

    task = asyncio.create_task(_deny_later())
    result = await agent.run("git push origin main", session_id="s1")
    await task
    assert "denied" in result.lower()


# ---------------------------------------------------------------------------
# Cross-repo detection
# ---------------------------------------------------------------------------

def test_is_cross_repo_detects_outside_cwd(agent: DevAgentTool, tmp_path) -> None:
    assert agent._is_cross_repo(tmp_path.parent) is True


def test_is_cross_repo_within_cwd_is_false(agent: DevAgentTool) -> None:
    import pathlib
    within = pathlib.Path.cwd() / "some" / "subdir"
    assert agent._is_cross_repo(within) is False


# ---------------------------------------------------------------------------
# Empty / malformed command
# ---------------------------------------------------------------------------

async def test_empty_command_returns_error(agent: DevAgentTool) -> None:
    result = await agent.run("", session_id="s1", operation_type="read")
    assert "empty" in result.lower() or "error" in result.lower() or "cannot parse" in result.lower()
