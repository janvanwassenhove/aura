"""U393: whether he should be wandering right now, and what he may say while he does.

Asked for as (translated): *"can we add a 'wandering' mode — the robot wanders
around, following people, moving the antennas, moving towards sound or
people"*, with an option for whether he may make sound. Agreed with three
conditions: a switch next to follow-me; "review that this cannot conflict with
other settings and modes"; and when someone speaks to him while he wanders, he
looks at them but only speaks if his wander sound allows it.

The robot decides HOW to wander (`robot_runtime.wander`) and refuses to while
asleep. This module decides WHETHER, in one place:

- the owner's switch, the `wander` capability (`WANDER_ENABLED`);
- paused while a presentation runs — on stage only the scenario moves and
  speaks (U334). U394 lets a scenario turn it on;
- re-asserted on every change that could matter: the switch, a scenario
  loading or ending, waking up, and the robot coming back — the robot does
  not remember it across its own restart.

His wander sound (`WANDER_SOUND`): `silent` — the default, and what anything
unrecognised means, because a typo must never be the reason he starts talking
— or `talk`. U395 adds `emotions`.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

SILENT, TALK = "silent", "talk"
SOUNDS = (SILENT, TALK)

_last: dict = {"robot": None, "note": "", "follow_me_overridden": False}


def wanted() -> bool:
    """The owner's switch."""
    return os.environ.get("WANDER_ENABLED", "false").strip().lower() == "true"


def _stage() -> dict | None:
    """U394: what the running talk asks of his body, or None when no talk runs.
    Each value is None where the scenario does not say."""
    try:
        from aura_brain import presentation_api  # noqa: PLC0415

        if presentation_api.is_active():
            return presentation_api.stage_robot()
    except Exception:  # noqa: BLE001 — a missing presentation module pauses nothing
        pass
    return None


def paused_reason() -> str | None:
    """Why it is not in force although the owner wants it, or None."""
    stage = _stage()
    if stage is not None and stage.get("wander") is not True:
        return "presentation"
    return None


def effective() -> bool:
    """Whether he should be wandering right now.

    During a talk the scenario decides — it is the owner's own script for
    that talk, so `wander: on` there makes him wander even with the switch
    off, and a scenario that says nothing pauses it (U334). Otherwise, the
    switch.
    """
    stage = _stage()
    if stage is not None:
        return stage.get("wander") is True
    return wanted()


def owner_follow_me() -> bool:
    return os.environ.get("HEAD_TRACKING", "true").strip().lower() == "true"


def sound() -> str:
    value = os.environ.get("WANDER_SOUND", SILENT).strip().lower()
    return value if value in SOUNDS else SILENT


def silences_speech() -> bool:
    """While wandering silently, replies are not spoken: someone who speaks to
    him gets looked at (the robot turns to the voice), and the answer shows in
    the console as text."""
    return effective() and sound() == SILENT


async def apply(robot: Any) -> dict:
    """Tell the robot what is in force. Never raises: a robot that is away or
    too old to wander is a state to report, not an error."""
    if robot is None:
        return status()
    want = effective()
    try:
        import httpx  # noqa: PLC0415

        try:
            _last["robot"] = await robot.set_wander(want)
            _last["note"] = ""
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code if exc.response is not None else 0
            _last["robot"] = None
            _last["note"] = ("the robot needs an update to wander"
                             if code in (404, 501) else f"the robot refused it (HTTP {code})")
        except (httpx.HTTPError, OSError) as exc:
            _last["robot"] = None
            _last["note"] = "could not reach the robot to tell it"
            logger.debug("wander apply failed: %s", exc)
    except Exception as exc:  # noqa: BLE001 — never break the caller
        _last["note"] = f"could not apply: {exc}"
    if _last["note"]:
        logger.info("wander: %s", _last["note"])
    await _apply_follow_me(robot)
    return status()


async def _apply_follow_me(robot: Any) -> None:
    """U394: a scenario may set follow-me for the talk; when the talk ends —
    or the scenario stops saying — the owner's own setting comes back."""
    stage = _stage()
    want = stage.get("follow_me") if stage is not None else None
    try:
        if want is not None:
            await robot.set_tracking(want)
            _last["follow_me_overridden"] = True
        elif _last["follow_me_overridden"]:
            await robot.set_tracking(owner_follow_me())
            _last["follow_me_overridden"] = False
    except Exception as exc:  # noqa: BLE001 — the same "never raises" as above
        logger.debug("follow-me apply failed: %s", exc)


def status() -> dict:
    return {
        "wanted": wanted(),
        "effective": effective(),
        "paused": paused_reason() if wanted() else None,
        "sound": sound(),
        "robot": _last["robot"],
        "note": _last["note"],
    }


def forget() -> None:
    """Tests: drop what the last apply learned."""
    _last["robot"], _last["note"] = None, ""
    _last["follow_me_overridden"] = False
