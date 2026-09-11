"""U326: he takes part in the conversation with his body, not only his voice.

Reported as "meeleven terwijl ik praat — als ik praat of als hij praat". Both
halves were genuinely missing:

* **While the other person talks** he was completely still. The nod at his name
  (U275) and the thinking pose (U147) both land *around* a turn, never inside
  one — and in a realtime or GPT-Live conversation there is no wake word and no
  thinking pause, so neither fired at all.
* **While he talks** the streamed paths command no motion whatsoever. The head
  sway during speech is the SDK reacting to audio levels (U157); nothing in it
  knows what he is saying. And on the one path that does gesture, the gesture
  was `await`ed *before* synthesis even started, so every reply was a move, a
  silence, and then a voice.

Two rules hold everything here together:

* **Only motions that keep follow-me.** The runtime pauses head tracking for
  anything outside its follow-gesture set, which in a conversation means he
  looks away from you in order to make a gesture about you.
* **Never in front of a word.** A gesture that arrives after the sentence is
  worse than no gesture (the same reason `embodiment.py` refuses a model call),
  so nothing here is ever awaited on the speech path.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

from aura_brain.embodiment import gesture_for

logger = logging.getLogger(__name__)

#: Motions the runtime runs WITHOUT pausing follow-me (its _FOLLOW_GESTURES).
KEEPS_TRACKING = frozenset({
    "nod", "tilt", "shake", "gesture", "wave",
    "mood_happy", "mood_excited", "mood_apologetic", "mood_curious",
    "mood_attentive", "listening", "thinking",
})

#: What "I am listening" looks like. Both are deliberately gentle: a big move
#: puts motor noise next to the microphone in the middle of the sentence it is
#: supposed to be hearing (U147 chose the lean for exactly this reason).
LISTEN_MOTIONS = ("listening", "nod")


def _f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _on(name: str, default: str = "true") -> bool:
    return os.environ.get(name, default).lower() == "true"


def _command(motion_id: str, amplitude: float, speed: float = 1.0):
    from shared_schemas.robot.models import MotionCommand

    return MotionCommand(motion_id=motion_id, speed=speed,
                         amplitude=max(0.05, min(1.0, amplitude)), direction=None)


def start_motion(robot: Any, motion_id: str, amplitude: float = 0.5,
                 speed: float = 1.0) -> asyncio.Task | None:
    """Start a motion and do NOT wait for it. Never raises.

    Returns the task (or None when the robot cannot move, or there is no event
    loop). Callers on the speech path use this so a gesture overlaps the
    synthesis instead of delaying it.
    """
    mover = getattr(robot, "execute_motion", None)
    if mover is None:
        return None

    async def _run() -> None:
        try:
            await mover(_command(motion_id, amplitude, speed))
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — a gesture is never worth a turn
            logger.debug("motion %s failed: %s", motion_id, exc)

    try:
        return asyncio.ensure_future(_run())
    except RuntimeError:        # called without a running loop
        return None


class ConversationBody:
    """The body's half of a conversation, shared by every speech engine."""

    def __init__(self, robot: Any, session_id: str = "default") -> None:
        self._robot = robot
        self._session_id = session_id
        self._last_listen = float("-inf")
        self._last_talk = float("-inf")
        self._ticker: asyncio.Task | None = None
        self._n = 0

    # -- while the other person is talking ------------------------------

    @property
    def listening(self) -> bool:
        return self._ticker is not None and not self._ticker.done()

    async def heard(self) -> bool:
        """A small "go on" while someone is talking to him.

        Rate-limited, because the callers are transcript deltas arriving many
        times a second: a cue per delta is a tic, not attention.
        """
        if not _on("BACKCHANNEL"):
            return False
        now = time.monotonic()
        if now - self._last_listen < _f("BACKCHANNEL_MIN_S", 4.0):
            return False
        self._last_listen = now
        motion = LISTEN_MOTIONS[self._n % len(LISTEN_MOTIONS)]
        self._n += 1
        return await self._move(motion, _f("BACKCHANNEL_AMPLITUDE", 0.3))

    def start_listening(self) -> None:
        """Keep acknowledging while they keep talking — for engines that
        report the start and end of a turn rather than a stream of deltas."""
        if self.listening:
            return
        try:
            self._ticker = asyncio.ensure_future(self._keep_listening())
        except RuntimeError:
            self._ticker = None

    def stop_listening(self) -> None:
        if self._ticker is not None:
            self._ticker.cancel()
            self._ticker = None

    async def _keep_listening(self) -> None:
        while True:
            await self.heard()
            await asyncio.sleep(max(0.05, _f("BACKCHANNEL_MIN_S", 4.0) / 2))

    # -- while he is talking --------------------------------------------

    async def replying(self, text: str = "", amplitude: float = 0.45) -> bool:
        """Move with what he is saying: the same keyword heuristic the typed
        path uses (U36), rate-limited to about one gesture per reply."""
        if not _on("TALK_GESTURES"):
            return False
        now = time.monotonic()
        if now - self._last_talk < _f("TALK_GESTURE_MIN_S", 6.0):
            return False
        motion = gesture_for(text or "")
        if motion not in KEEPS_TRACKING:
            motion = "nod"
        self._last_talk = now
        return await self._move(motion, amplitude)

    # -- the one place a motion is actually sent -------------------------

    async def _move(self, motion_id: str, amplitude: float) -> bool:
        mover = getattr(self._robot, "execute_motion", None)
        if mover is None:
            return False
        try:
            await mover(_command(motion_id, amplitude))
            return True
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — an unreachable robot costs the
            logger.debug("conversational motion %s failed: %s", motion_id, exc)
            return False          # gesture, never the conversation
