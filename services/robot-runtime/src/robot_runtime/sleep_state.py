"""Sleep is a state of the ROBOT, not a flag on the laptop — U237.

Before this, "asleep" lived only as `ROBOT_ASLEEP` in the brain's environment.
The brain suppressed greetings and replies, told the adapter to stop tracking,
and played the sleep motion. The robot then drooped, and roughly four seconds
later stood back up: the on-device loops that exist precisely so it never looks
frozen — the offline behaviour loop (every 4 s) and the idle fidget loop (every
30 s) — had no idea anything had been asked of them, and a reconnect ran
``wake_up()`` unconditionally.

So the robot now holds the state itself. Everything that moves the robot on its
own initiative asks here first. A module rather than a flag on one object,
because the three things that need it (the offline loop, the behaviour engine
and the Reachy adapter) have no other object in common.

Sleep means *take no action of your own*. It does not silence commands: a
motion the owner explicitly asks for still runs, which is what makes the wake
button work.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_asleep = False


def is_asleep() -> bool:
    return _asleep


def set_asleep(value: bool) -> bool:
    """Returns the new state. Logged, because a robot that stops moving on
    purpose looks exactly like a robot that has stopped working."""
    global _asleep
    changed = _asleep != bool(value)
    _asleep = bool(value)
    if changed:
        logger.info("robot is now %s", "asleep — self-initiated motion suspended" if _asleep else "awake")
    return _asleep
