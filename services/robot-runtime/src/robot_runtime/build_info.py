"""What code is this robot actually running? — U240.

The Pi drifted 74 commits behind the laptop and nobody noticed for a month,
because nothing in the system could answer that question. The laptop updates
itself several times a day; the robot is deployed by hand, and a hand forgets.

So the runtime says what it is running, the brain compares, and the drift shows
up in the maintenance report instead of in a bug months later. Reported, not
enforced: an old robot is often perfectly fine, and a version check that
*refuses to work* would be a worse failure than the drift it prevents.
"""

from __future__ import annotations

import functools
import subprocess
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(                      # noqa: S603 — fixed argv, no shell
            ["git", *args],                        # noqa: S607
            cwd=_REPO_ROOT, capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


@functools.lru_cache(maxsize=1)
def build_info() -> dict:
    """Identity of this deployment. Cached: it cannot change while we run.

    `commit` is the useful one — the brain compares it against its own. It is
    absent when the runtime was installed from a wheel rather than a checkout,
    which is a legitimate way to run and simply means the comparison is skipped
    rather than guessed at.
    """
    try:
        pkg = version("robot-runtime")
    except PackageNotFoundError:
        pkg = "unknown"
    commit = _git("rev-parse", "HEAD")
    return {
        "package": pkg,
        "commit": commit,
        "commit_short": commit[:7] if commit else None,
        "committed_at": _git("log", "-1", "--format=%cI"),
        "dirty": bool(_git("status", "--porcelain")) if commit else None,
    }
