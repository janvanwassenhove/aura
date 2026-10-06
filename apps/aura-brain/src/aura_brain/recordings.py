"""U409: one recording per line — the same take every time, ready on the cue.

Reported (translated): the same line on the same slide *"sounds different on
every run, and starts with a delay"*. Both had one cause. Every firing
synthesized the line afresh, and `gpt-4o-mini-tts` is a generative model: each
call is a new performance. The call was also a network round-trip made at the
cue, which on a conference connection is the delay by itself.

So a talk's fixed lines are recorded once — in the background, a few at a
time, when the talk is loaded — and the cue plays the recording. A take is
known by everything that shapes how it sounds: the words, the voice, the speed,
the direction and the model. Change any of them and it is a different take;
change none and it is the same one, on every run. Improvised lines cannot be
recorded before they are written and are not kept at all.

Takes live in memory for the brain's lifetime and on disk under
`RECORDINGS_DIR` (default `<SCENARIOS_DIR>/recordings`), so a restart between
the rehearsal and the talk keeps the rehearsed take. The disk keeps the
`KEEP` most recently used; a presenter who wants another take asks for one
(`POST /presentation/rerecord`).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
from collections import OrderedDict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

#: How many lines are recorded at once. A few, not all: a talk of forty lines
#: must not open forty connections on a conference's Wi-Fi.
AT_ONCE = 3
#: How many takes are kept, in memory and on disk; the least recently used go.
KEEP = 400

READY, RENDERING, FAILED, WAITING = "ready", "rendering", "failed", "waiting"


def _alive(task: asyncio.Task | None) -> bool:
    """A take still on its way. One whose event loop has closed never finishes
    (a test client's per-request loop) and counts as not started."""
    return task is not None and not task.done() and not task.get_loop().is_closed()


@dataclass(frozen=True)
class Take:
    """One stretch of a line, as it is to be performed."""

    text: str
    voice: str
    speed: float
    direction: str
    model: str

    @property
    def key(self) -> str:
        raw = json.dumps([self.text, self.voice.lower(), round(float(self.speed), 3),
                          self.direction, self.model], ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def folder() -> Path:
    explicit = os.environ.get("RECORDINGS_DIR", "").strip()
    if explicit:
        return Path(explicit)
    return Path(os.environ.get("SCENARIOS_DIR", "./scenarios")) / "recordings"


async def perform(take: Take) -> str | None:
    """Synthesize this take now, keeping nothing — for a line that is new
    every time (improvised). The direction is sent only when there is one."""
    from aura_brain import voice  # noqa: PLC0415 — optional at import time

    if take.direction:
        return await voice.synthesize_b64(take.text, take.voice, take.speed,
                                          instructions=take.direction)
    return await voice.synthesize_b64(take.text, take.voice, take.speed)


class Recordings:
    def __init__(self) -> None:
        self._audio: OrderedDict[str, str] = OrderedDict()
        self._pending: dict[str, asyncio.Task] = {}
        self._failed: set[str] = set()

    # ── what is there ───────────────────────────────────────────────────────

    def state(self, take: Take) -> str:
        key = take.key
        if key in self._audio:
            return READY
        if _alive(self._pending.get(key)):
            return RENDERING
        if key in self._failed:
            return FAILED
        if self._path(key).exists():
            return READY
        return WAITING

    # ── playing ─────────────────────────────────────────────────────────────

    async def take(self, take: Take) -> str | None:
        """The recording: kept, on its way (awaited, never asked twice), on
        disk, or — on a miss — made now and kept. None if it cannot be made;
        the caller says so (U269)."""
        key = take.key
        if key in self._audio:
            self._audio.move_to_end(key)
            return self._audio[key]
        task = self._pending.get(key)
        if _alive(task) and task.get_loop() is asyncio.get_running_loop():
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                me = asyncio.current_task()
                if me is not None and me.cancelling():
                    raise
                # the take was dropped for a new one while this line waited:
                # it is made below rather than lost
        audio = self._load(key)
        if audio is not None:
            return audio
        return await self._render(take)

    # ── recording ahead ─────────────────────────────────────────────────────

    def prepare(self, takes: Iterable[Take]) -> int:
        """Record in the background whatever is not recorded or on its way.
        Returns how many were started."""
        todo: list[Take] = []
        seen: set[str] = set()
        for take in takes:
            key = take.key
            if key in seen:
                continue
            seen.add(key)
            if key in self._audio or self._load(key) is not None:
                continue
            if _alive(self._pending.get(key)):
                continue
            todo.append(take)
        if not todo:
            return 0
        gate = asyncio.Semaphore(AT_ONCE)
        for take in todo:
            self._failed.discard(take.key)
            self._pending[take.key] = asyncio.ensure_future(self._render_in_turn(take, gate))
        return len(todo)

    def forget(self, takes: Iterable[Take]) -> None:
        """Drop these takes everywhere, so the next one is new."""
        for take in takes:
            key = take.key
            self._audio.pop(key, None)
            self._failed.discard(key)
            task = self._pending.pop(key, None)
            if task is not None and not task.done():
                task.cancel()
            try:
                self._path(key).unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("recording %s could not be removed: %s", key, exc)

    def clear_memory(self) -> None:
        """Forget what is held in memory — what a restart forgets. The disk stays."""
        for task in self._pending.values():
            if not task.done():
                task.cancel()
        self._pending.clear()
        self._audio.clear()
        self._failed.clear()

    # ── inside ──────────────────────────────────────────────────────────────

    async def _render_in_turn(self, take: Take, gate: asyncio.Semaphore) -> str | None:
        try:
            async with gate:
                return await self._render(take)
        finally:
            if self._pending.get(take.key) is asyncio.current_task():
                self._pending.pop(take.key, None)

    async def _render(self, take: Take) -> str | None:
        key = take.key
        try:
            audio = await perform(take)
        except Exception as exc:  # noqa: BLE001 — a failed take is a state, not a crash
            logger.warning("recording a line failed: %s", exc)
            audio = None
        if not audio:
            self._failed.add(key)
            return None
        self._failed.discard(key)
        self._keep(key, audio)
        self._save(key, audio)
        return audio

    def _keep(self, key: str, audio: str) -> None:
        self._audio[key] = audio
        self._audio.move_to_end(key)
        while len(self._audio) > KEEP:
            self._audio.popitem(last=False)

    def _path(self, key: str) -> Path:
        return folder() / f"{key}.pcm"

    def _load(self, key: str) -> str | None:
        path = self._path(key)
        try:
            if not path.exists():
                return None
            audio = base64.b64encode(path.read_bytes()).decode()
            os.utime(path)                  # recently used: kept longest
        except OSError as exc:
            logger.warning("recording %s unreadable: %s", key, exc)
            return None
        self._keep(key, audio)
        return audio

    def _save(self, key: str, audio: str) -> None:
        try:
            where = folder()
            where.mkdir(parents=True, exist_ok=True)
            self._path(key).write_bytes(base64.b64decode(audio))
            kept = sorted(where.glob("*.pcm"), key=lambda p: p.stat().st_mtime)
            for old in kept[:max(0, len(kept) - KEEP)]:
                old.unlink(missing_ok=True)
        except OSError as exc:            # memory still has it; only a restart loses it
            logger.warning("recording %s not kept on disk: %s", key, exc)


_store: Recordings | None = None


def store() -> Recordings:
    global _store
    if _store is None:
        _store = Recordings()
    return _store


def reset() -> None:
    """A fresh store (the disk is left alone)."""
    global _store
    if _store is not None:
        _store.clear_memory()
    _store = None
