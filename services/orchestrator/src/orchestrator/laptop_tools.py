"""U58: tool-ladder basistools — PowerShell, bestandsysteem, git-voorbereiding.

Deel van de automatiseringsladder (agentic-plan.md):
  API → CLI → file system → browser → desktop-GUI → screenshot+klik.

Beveiligingsmodel:
  - ``run_powershell`` en ``write_file`` zijn APPROVAL_REQUIRED (shared-policies).
  - Bestandstoegang is pad-begrensd tot AGENT_FS_ROOTS (``;``-gescheiden;
    default: de werkmap van de brain). Alles daarbuiten wordt geweigerd —
    óók via ``..``/symlinks (paths worden geresolved vóór de check).
  - ``git_prepare`` is read-only (status/diff/log); committen/pushen blijft
    bij run_dev_task met zijn eigen approval-tiers.
  - Output is gecapt zodat één tool-resultaat de context niet opblaast.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

_OUTPUT_CAP = 6000  # chars per tool result


def _fs_roots() -> list[Path]:
    raw = os.environ.get("AGENT_FS_ROOTS", "").strip()
    roots = [Path(p).resolve() for p in raw.split(";") if p.strip()] if raw else []
    return roots or [Path.cwd().resolve()]


def _resolve_bounded(path: str) -> Path | None:
    """Resolve ``path`` and require it inside an allowed root; None otherwise."""
    try:
        target = Path(path).expanduser().resolve()
    except OSError:
        return None
    for root in _fs_roots():
        if target == root or target.is_relative_to(root):
            return target
    return None


def _cap(text: str) -> str:
    if len(text) <= _OUTPUT_CAP:
        return text
    return text[:_OUTPUT_CAP] + f"\n[... truncated, {len(text)} chars total]"


async def _run_argv(argv: list[str], cwd: str | None, timeout: float = 60.0) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv, cwd=cwd,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except FileNotFoundError:
        return f"[{argv[0]}: not found on this machine]"
    except TimeoutError:
        proc.kill()
        return f"[{argv[0]}: timed out after {timeout:.0f}s]"
    except Exception as exc:  # noqa: BLE001
        return f"[{argv[0]}: error — {exc}]"
    text = out.decode("utf-8", errors="replace").strip()
    status = "" if proc.returncode == 0 else f"\n[exit code {proc.returncode}]"
    return _cap(text or "(no output)") + status


# ── tools ──────────────────────────────────────────────────────────────


async def run_powershell(command: str, working_dir: str | None = None) -> str:
    """CLI-laag. Approval-gated upstream (APPROVAL_REQUIRED)."""
    command = (command or "").strip()
    if not command:
        return "[run_powershell: command is required]"
    cwd = None
    if working_dir:
        bounded = _resolve_bounded(working_dir)
        if bounded is None:
            return f"[run_powershell: working_dir {working_dir!r} is outside the allowed roots]"
        cwd = str(bounded)
    return await _run_argv(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", command], cwd,
    )


async def read_file(path: str) -> str:
    """FS-laag, read-only en pad-begrensd — geen approval nodig."""
    target = _resolve_bounded(path or "")
    if target is None:
        roots = "; ".join(str(r) for r in _fs_roots())
        return f"[read_file: {path!r} is outside the allowed roots ({roots})]"
    if not target.is_file():
        return f"[read_file: {path!r} does not exist or is not a file]"
    try:
        return _cap(target.read_text(encoding="utf-8", errors="replace"))
    except OSError as exc:
        return f"[read_file: error — {exc}]"


async def write_file(path: str, content: str) -> str:
    """FS-laag, schrijvend — approval-gated upstream (APPROVAL_REQUIRED)."""
    target = _resolve_bounded(path or "")
    if target is None:
        roots = "; ".join(str(r) for r in _fs_roots())
        return f"[write_file: {path!r} is outside the allowed roots ({roots})]"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content or "", encoding="utf-8")
        return f"Wrote {len(content or '')} chars to {target}."
    except OSError as exc:
        return f"[write_file: error — {exc}]"


_GIT_ACTIONS = {
    "status": ["git", "status", "--short", "--branch"],
    "diff": ["git", "diff"],
    "diff_staged": ["git", "diff", "--staged"],
    "log": ["git", "log", "--oneline", "-15"],
}


async def git_prepare(action: str, working_dir: str | None = None) -> str:
    """Read-only git-voorbereiding (status/diff/log). Commit/push loopt via
    run_dev_task met zijn eigen approval-tiers."""
    argv = _GIT_ACTIONS.get((action or "").strip().lower())
    if argv is None:
        return f"[git_prepare: action must be one of {sorted(_GIT_ACTIONS)}]"
    cwd = None
    if working_dir:
        bounded = _resolve_bounded(working_dir)
        if bounded is None:
            return f"[git_prepare: working_dir {working_dir!r} is outside the allowed roots]"
        cwd = str(bounded)
    return await _run_argv(argv, cwd, timeout=30.0)
