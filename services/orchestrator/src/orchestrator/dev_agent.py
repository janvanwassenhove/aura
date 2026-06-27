"""DevAgentTool — outbound development-task execution (U20, ADR-007 §3.2).

Dispatches dev tasks via subprocess shell or, when granted, via the Claude Code
CLI.  Approval tiers (owner-confirmed):

    read / grep / run tests   → auto-approve
    write / edit files        → step-up via ApprovalManager
    git commit                → step-up via ApprovalManager
    git push / arbitrary exec → step-up via ApprovalManager
    cross-repo working dir    → always ask, regardless of operation type
    task needs Claude Code    → ask permission before escalating

Security invariants:
- Never uses shell=True (no command injection via user-controlled strings).
- working_dir is resolved and validated before use.
- Subprocess execution is capped at _EXEC_TIMEOUT_S seconds.
- Claude Code CLI invoked as a subprocess (no eval / exec).
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
from enum import StrEnum
from pathlib import Path

from orchestrator.approval_manager import ApprovalDeniedError, ApprovalManager, ApprovalTimeout
from shared_events.bus import AsyncEventBus

logger = logging.getLogger(__name__)

_EXEC_TIMEOUT_S = 120.0

# Keywords that indicate a write/mutating operation in a shell command.
_WRITE_PREFIXES = (
    "touch ", "mkdir ", "cp ", "mv ", "rm ",
    "git add", "git reset", "git checkout",
    "git merge", "git rebase", "git cherry",
    "sed ", "awk ", "tee ", "truncate ", "dd ",
    ">", ">>",
)
_COMMIT_PREFIXES = ("git commit",)
_PUSH_PREFIXES = ("git push", "git push --force")

# Commands considered safe reads — auto-approved.
_READ_PREFIXES = (
    "echo ",
    "cat ", "ls ", "find ", "grep ", "rg ", "fd ",
    "git log", "git status", "git diff", "git show", "git branch",
    "head ", "tail ", "wc ", "stat ", "file ",
    "pytest", "python -m pytest", "uv run pytest", "uv run --",
    "python -m ", "uv run python",
)


class OperationType(StrEnum):
    READ = "read"
    WRITE = "write"
    COMMIT = "commit"
    PUSH = "push"
    COMPLEX = "complex"  # multi-step; needs Claude Code


def classify_operation(task: str) -> OperationType:
    """Heuristic classification of a task string into an operation type."""
    t = task.strip().lower()

    for p in _PUSH_PREFIXES:
        if t.startswith(p):
            return OperationType.PUSH
    for p in _COMMIT_PREFIXES:
        if t.startswith(p):
            return OperationType.COMMIT
    for p in _WRITE_PREFIXES:
        if t.startswith(p) or (p in (">", ">>") and p in t):
            return OperationType.WRITE
    for p in _READ_PREFIXES:
        if t.startswith(p):
            return OperationType.READ

    # If it looks like natural language (no known command prefix and contains
    # spaces + sentence-like words) treat it as a complex task for Claude Code.
    words = t.split()
    if len(words) > 3 and not any(c in t for c in ("|", ";", "&&", "$")):
        return OperationType.COMPLEX

    # Default: treat as an arbitrary shell exec (requires approval).
    return OperationType.PUSH  # conservative: treat unknown as high-risk


class DevAgentTool:
    """Executes dev tasks with approval gating.

    Injected into :class:`orchestrator.pipeline.OrchestratorPipeline`; the
    pipeline calls ``run()`` when the LLM emits a ``run_dev_task`` tool call.
    """

    def __init__(
        self,
        approval_mgr: ApprovalManager,
        bus: AsyncEventBus,
    ) -> None:
        self._approval = approval_mgr
        self._bus = bus
        self._backend: str = os.environ.get("DEV_AGENT_BACKEND", "shell").lower()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(
        self,
        task: str,
        session_id: str,
        working_dir: str | None = None,
        operation_type: str | None = None,
    ) -> str:
        """Execute a dev task and return a text result for the LLM."""
        cwd = self._resolve_cwd(working_dir)
        cross_repo = self._is_cross_repo(cwd)

        op = (
            OperationType(operation_type)
            if operation_type and operation_type in OperationType.__members__.values()
            else classify_operation(task)
        )

        needs_approval = op in (OperationType.WRITE, OperationType.COMMIT, OperationType.PUSH)

        if cross_repo or needs_approval:
            label = "run_dev_task_cross_repo" if cross_repo else f"run_dev_task_{op.value}"
            try:
                await self._approval.request_approval(
                    label,
                    {
                        "task": task[:200],
                        "working_dir": str(cwd),
                        "operation_type": op.value,
                        "cross_repo": cross_repo,
                    },
                )
            except ApprovalTimeout:
                return f"[run_dev_task: approval timed out for {op.value} operation]"
            except ApprovalDeniedError:
                return f"[run_dev_task: denied by owner for {op.value} operation]"

        # Complex task in shell-only mode → ask for Claude Code escalation.
        backend = self._backend
        if op == OperationType.COMPLEX and backend == "shell":
            backend = await self._maybe_escalate_to_claude(task, session_id)
            if backend == "shell":
                return (
                    "[run_dev_task: task is too complex for a single shell command. "
                    "Set DEV_AGENT_BACKEND=claude or rephrase as a concrete shell command.]"
                )

        if backend == "claude":
            return await self._execute_claude(task, cwd)
        return await self._execute_shell(task, cwd)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _resolve_cwd(self, working_dir: str | None) -> Path:
        if not working_dir:
            return Path.cwd()
        p = Path(working_dir).expanduser()
        if not p.is_absolute():
            p = Path.cwd() / p
        return p.resolve()

    def _is_cross_repo(self, cwd: Path) -> bool:
        """Return True when cwd is outside the brain process working directory."""
        try:
            home = Path.cwd().resolve()
            cwd.relative_to(home)  # raises ValueError if outside
            return False
        except ValueError:
            return True

    async def _maybe_escalate_to_claude(self, task: str, session_id: str) -> str:
        """Ask for approval to escalate from shell to Claude Code.

        Returns ``'claude'`` if granted, ``'shell'`` if denied/timeout.
        """
        try:
            await self._approval.request_approval(
                "escalate_to_claude_code",
                {"task": task[:200], "reason": "task requires multi-step coding"},
            )
            return "claude"
        except (ApprovalTimeout, ApprovalDeniedError):
            return "shell"

    async def _execute_shell(self, task: str, cwd: Path) -> str:
        """Run task as a shell command via asyncio subprocess (no shell=True)."""
        try:
            argv = shlex.split(task)
        except ValueError as exc:
            return f"[run_dev_task: cannot parse command — {exc}]"

        if not argv:
            return "[run_dev_task: empty command]"

        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                cwd=str(cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=_EXEC_TIMEOUT_S)
            except TimeoutError:
                proc.kill()
                return f"[run_dev_task: shell command timed out after {_EXEC_TIMEOUT_S:.0f}s]"

            output = stdout.decode(errors="replace").strip()
            if proc.returncode != 0:
                return (
                    f"[run_dev_task: exit {proc.returncode}]\n"
                    + (output[:1000] if output else "(no output)")
                )
            return output[:2000] or "(command completed with no output)"

        except FileNotFoundError:
            return f"[run_dev_task: command not found — {argv[0]!r}]"
        except Exception as exc:
            logger.error("dev_agent shell exec failed: %s", exc)
            return f"[run_dev_task: error — {exc}]"

    async def _execute_claude(self, task: str, cwd: Path) -> str:
        """Invoke Claude Code CLI: ``claude --task <task> --cwd <cwd>``."""
        claude_bin = os.environ.get("CLAUDE_CODE_BIN", "claude")
        try:
            proc = await asyncio.create_subprocess_exec(
                claude_bin,
                "--task", task,
                "--cwd", str(cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=_EXEC_TIMEOUT_S)
            except TimeoutError:
                proc.kill()
                return f"[run_dev_task: Claude Code timed out after {_EXEC_TIMEOUT_S:.0f}s]"

            output = stdout.decode(errors="replace").strip()
            if proc.returncode != 0:
                return f"[run_dev_task: claude exit {proc.returncode}]\n" + output[:1000]
            return output[:2000] or "(claude completed with no output)"

        except FileNotFoundError:
            return (
                f"[run_dev_task: Claude Code CLI not found at {claude_bin!r}. "
                "Install it or set CLAUDE_CODE_BIN to its path.]"
            )
        except Exception as exc:
            logger.error("dev_agent claude exec failed: %s", exc)
            return f"[run_dev_task: error — {exc}]"
