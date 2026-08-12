"""Is the robot running the code we think it is? — U240.

The Pi sat 74 commits behind the laptop for a month. Nothing was broken enough
to notice, right up until a new endpoint returned 404 and the sleep button
silently did nothing (U238).

This is deliberately a *report*, never a refusal. An older robot usually works
fine, and a brain that declined to talk to one would turn a mild drift into an
outage — the opposite of the trade this project makes everywhere else.

The comparison is by commit, not by counting: the two hosts share no reliable
clock and the Pi's history was rewritten once already, so "is it the same
commit" is the only question with a trustworthy answer. Anything else is
`unknown`, which is honest rather than reassuring.
"""

from __future__ import annotations

import functools
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]


@functools.lru_cache(maxsize=1)
def own_commit() -> str | None:
    try:
        out = subprocess.run(                      # noqa: S603 — fixed argv, no shell
            ["git", "rev-parse", "HEAD"],          # noqa: S607
            cwd=_REPO_ROOT, capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


def compare(robot_build: dict | None, brain_commit: str | None = None) -> dict:
    """Compare what the robot reports with what we are.

    Returns {state, detail} where state is one of:
      in_step   — same commit
      behind    — different commit; the robot needs a deploy
      unknown   — one side cannot say (installed from a wheel, no git, old
                  runtime that has no /health build field at all)
    """
    brain = brain_commit if brain_commit is not None else own_commit()
    robot = (robot_build or {}).get("commit")
    # This runs inside a maintenance tick: a version check that can throw would
    # take out the loop that watches everything else. Anything that is not a
    # string is treated as "did not say".
    if not isinstance(robot, str):
        robot = None
    if not isinstance(brain, str):
        brain = None

    if not robot:
        return {
            "state": "unknown",
            "detail": "the robot does not report which code it runs — a runtime "
                      "older than U240, or installed from a wheel",
        }
    if not brain:
        return {"state": "unknown", "detail": "this brain cannot read its own commit"}
    if robot == brain:
        return {"state": "in_step", "detail": f"robot and brain both on {robot[:7]}"}
    return {
        "state": "behind",
        "detail": f"robot is on {robot[:7]}, brain on {brain[:7]} — "
                  f"deploy with scripts/deploy_robot.py",
        "robot_commit": robot,
        "brain_commit": brain,
    }
