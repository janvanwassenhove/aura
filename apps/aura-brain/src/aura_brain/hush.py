"""May he still be talking? — U366.

U256 gave the owner a Quiet switch. U332 made it real for the *start* of a
turn: while Quiet is on, every turn goes back through the wake word, so the
television cannot ask him questions. U334 did the same for Present mode, where
only the scenario may speak.

Both gates sit where a turn is *decided*, and that is why the owner reported,
twice, that Quiet "does nothing": an open Live or realtime session is not a
turn. It holds the microphone for up to ten minutes
(``LIVE_SESSION_MAX_S``) and answers whatever is loudest. Switching Quiet on in
the middle of that changed the header and nothing else.

So the question has one home now, and the sessions ask it on the same tick they
already use to notice the Stop button — about once a second. Stop, Quiet and
Present then all mean the same thing: *now*, not when this conversation happens
to end.

**It never raises, and an unreadable policy is never a reason to fall silent.**
That is the older rule (U332) and it points the other way on purpose: a robot
that goes mute because a JSON file could not be parsed is a fault nobody can
diagnose from the outside, while a robot that keeps talking is merely the state
everyone already understands.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

QUIET = "quiet switched on"
PRESENTING = "present mode — only the scenario speaks"


def _ask() -> tuple[bool, bool]:
    """``(quiet, presenting)`` straight from the policy. May raise.

    Imported by name rather than as an attribute so that a replaced module is
    honoured — which is how the policy is stood in for, and how a future
    packaging of this ever gets tested at all. A policy that knows only about
    Quiet is read for Quiet; missing is not the same as false, but it is the
    same as "nothing here forbids speaking".
    """
    import importlib  # noqa: PLC0415

    policy = importlib.import_module("orchestrator.mode_policy")
    quiet = getattr(policy, "quiet", None)
    presenting = getattr(policy, "presenting", None)
    return (bool(quiet()) if callable(quiet) else False,
            bool(presenting()) if callable(presenting) else False)


def silence_reason() -> str | None:
    """Why an open conversation must end right now, or None to carry on."""
    try:
        quiet, presenting = _ask()
    except Exception as exc:  # noqa: BLE001 — see the docstring: never mute him
        logger.debug("policy unreadable (%s); he keeps his voice", type(exc).__name__)
        return None
    if quiet:
        return QUIET
    if presenting:
        return PRESENTING
    return None


def hushed() -> bool:
    """The entry gate U332 wrote, now asking the same question as the sessions."""
    return silence_reason() is not None
