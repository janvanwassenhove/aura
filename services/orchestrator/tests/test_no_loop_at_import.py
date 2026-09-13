"""U332: importing must not need an event loop, and neither must a dataclass.

A second machine could not start AURA at all:

    File "…/orchestrator/approval_manager.py", line 40, in _PendingApproval
        future: asyncio.Future[bool] = field(
            default_factory=asyncio.get_event_loop().create_future)
    RuntimeError: There is no current event loop in thread 'MainThread'.

`asyncio.get_event_loop()` ran while the CLASS BODY was being evaluated — at
import, in a thread with no loop. Until Python 3.13 that quietly created one
and only warned (our own test output has carried that DeprecationWarning for
months); **3.14 raises**, and `uv` picked 3.14 on the new laptop. The brain
then died before its first line of work, with a stack trace about a dataclass
field that has nothing to do with what the owner was trying to do.

So: no module in this repository may reach for the loop at import time, and the
ones that need a loop ask for the RUNNING one, which cannot be the wrong loop.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SOURCES = (REPO / "apps" / "aura-brain" / "src", REPO / "services", REPO / "packages")

#: `get_event_loop()` is deprecated everywhere and fatal at import on 3.14.
#: `get_running_loop()` is the one that cannot be wrong: inside a coroutine it
#: returns the loop actually running; outside one it refuses, loudly.
_FORBIDDEN = re.compile(r"asyncio\.get_event_loop\s*\(")


def _sources() -> list[Path]:
    out: list[Path] = []
    for root in SOURCES:
        for py in root.rglob("*.py"):
            parts = py.as_posix()
            if "/dist/" in parts or "/tests/" in parts or "/.venv/" in parts:
                continue
            out.append(py)
    return out


def test_no_module_reaches_for_the_loop() -> None:
    offenders = {
        py.relative_to(REPO).as_posix(): n
        for py in _sources()
        for n, line in enumerate(py.read_text(encoding="utf-8", errors="replace").splitlines(), 1)
        if _FORBIDDEN.search(line)
    }
    assert not offenders, (
        "asyncio.get_event_loop() is deprecated and raises at import on Python "
        f"3.14 — use get_running_loop() inside async code: {offenders}"
    )


def test_the_approval_module_imports_without_a_loop() -> None:
    """The exact failure, reproduced: a fresh interpreter, no loop anywhere."""
    proc = subprocess.run(
        [sys.executable, "-c",
         "import orchestrator.approval_manager as m; "
         "print(m.ApprovalManager.__name__)"],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "ApprovalManager" in proc.stdout


async def test_a_pending_approval_binds_to_the_loop_it_is_created_in() -> None:
    """The future has to belong to the loop that will await it — which is why
    it is made when the approval is requested, not when the class is defined."""
    import asyncio

    from orchestrator.approval_manager import _PendingApproval

    pending = _PendingApproval(approval_id="a", tool_name="t", arguments={},
                               session_id="s")
    assert pending.future.get_loop() is asyncio.get_running_loop()
    assert not pending.future.done()
