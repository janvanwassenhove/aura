"""U410: which of a talk's lines the robot already has — and sending him the rest.

Asked (translated): *"can we add preloading to decrease delay/latency of e.g.
wifi hotspot?"* Since U409 a talk's fixed lines are recorded once, here. Played
on the robot, each still travelled at its cue: a whole utterance of PCM, some
300 kB for five seconds — on a phone's hotspot, the delay. So once a line is
recorded it is sent to the robot in the background, one line at a time so the
link stays free for whatever the talk needs now, and the cue names it.

A line is named by its audio (`key_of`): the same recording is the same name
on every run and after any restart, and a new take — re-recorded with the same
words, voice and direction — is a new name, so the robot can never play the
take the presenter replaced.

A robot older than this does not know a take by name — and would answer a
speak without audio by playing nothing and saying ok (U269). So a name is only
ever sent to a robot that has shown it keeps takes (it answered `held`); any
other robot gets the audio at the cue, exactly as before, and the status says
why. A robot that has lost a take answers 409; the line goes with its audio in
that same cue, and is sent to him again for next time.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

HOLDS, OLDER, UNKNOWN = "holds", "older", "unknown"

#: A line to send: a label (the beat it belongs to), and how to get its audio —
#: which may wait for its recording.
Line = tuple[str, Callable[[], Awaitable[str | None]]]


def key_of(audio_b64: str) -> str:
    """The name of a line on the robot: the hash of what he will play."""
    return hashlib.sha256(base64.b64decode(audio_b64)).hexdigest()[:32]


def status_of(exc: BaseException) -> int | None:
    """The HTTP status an error carries, if it carries one."""
    return getattr(getattr(exc, "response", None), "status_code", None)


class RobotTakes:
    def __init__(self) -> None:
        self.supported: bool | None = None
        self.held: set[str] = set()
        #: The name each label's line last had — for the status.
        self.named: dict[str, str] = {}
        self._queue: list[str] = []
        self._task: asyncio.Task | None = None

    # ── what he has ─────────────────────────────────────────────────────────

    def holds(self, key: str) -> bool:
        return self.supported is True and bool(key) and key in self.held

    def holds_line(self, label: str) -> bool:
        return self.holds(self.named.get(label, ""))

    def state(self) -> str:
        return {True: HOLDS, False: OLDER}.get(self.supported, UNKNOWN)

    def _busy(self) -> bool:
        """A send under way. One on an event loop that has closed never ends
        (a test client's per-request loop) and is not under way."""
        task = self._task
        return task is not None and not task.done() and not task.get_loop().is_closed()

    def sending(self) -> int:
        return len(self._queue) if self._busy() else 0

    def lost(self, key: str) -> None:
        self.held.discard(key)

    # ── sending ahead ───────────────────────────────────────────────────────

    def send_ahead(self, robot: Any, lines: list[Line], *, replace: bool = True) -> None:
        """Send these lines to him in the background, one at a time, each once
        it is recorded and only if he does not have it. `replace` drops a send
        already under way (a new talk); otherwise this batch waits its turn."""
        if robot is None or not hasattr(robot, "store_take") or self.supported is False:
            return
        previous = None
        if self._busy():
            if replace:
                self._task.cancel()
                self._queue = []
            else:
                previous = self._task
        self._queue += [label for label, _ in lines]
        self._task = asyncio.ensure_future(self._send(robot, lines, previous))

    def resend(self, robot: Any, label: str, audio_b64: str) -> None:
        """Send one line again — he lost it."""
        async def audio() -> str | None:
            return audio_b64
        self.send_ahead(robot, [(label, audio)], replace=False)

    async def _send(self, robot: Any, lines: list[Line],
                    previous: asyncio.Task | None) -> None:
        if previous is not None:
            try:
                await previous
            except BaseException:  # noqa: BLE001 — the earlier batch's fate is its own
                pass
        try:
            for label, audio_of in lines:
                try:
                    if not await self._one(robot, label, audio_of):
                        return
                finally:
                    self._done(label)
        finally:
            for label, _ in lines:
                self._done(label)

    async def _one(self, robot: Any, label: str,
                   audio_of: Callable[[], Awaitable[str | None]]) -> bool:
        """Send one line if he needs it. False when sending ahead is over —
        he is too old for it."""
        audio = await audio_of()
        if not audio:
            return True                   # not recorded: the cue will say so
        key = key_of(audio)
        self.named[label] = key
        if key in self.held and self.supported:
            return True
        try:
            have = await robot.held_takes([key])
            self.supported = True
            if key in have:
                self.held.add(key)
                return True
            await robot.store_take(key, audio)
            self.held.add(key)
        except Exception as exc:  # noqa: BLE001 — sending ahead is a bonus, never a failure
            if status_of(exc) == 404:
                self._older()
                return False
            logger.warning("a line could not be sent to the robot ahead: %s", exc)
        return True

    def _older(self) -> None:
        if self.supported is not False:
            logger.warning("the robot is older than this app: a talk's lines travel "
                           "at their cue (no /robot/takes)")
        self.supported = False

    def _done(self, label: str) -> None:
        if label in self._queue:
            self._queue.remove(label)

    def cancel(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._queue = []


_store: RobotTakes | None = None


def store() -> RobotTakes:
    global _store
    if _store is None:
        _store = RobotTakes()
    return _store


def reset() -> None:
    """Forget everything about the robot's takes — what a brain restart forgets."""
    global _store
    if _store is not None:
        _store.cancel()
    _store = None
