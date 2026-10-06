"""U410: a talk's lines, kept on the robot ahead of their cue.

Asked (translated): *"can we add preloading to decrease delay/latency of e.g.
wifi hotspot?"* Since U409 each fixed line of a talk is recorded once, in the
brain. Played on the robot, it still had to travel at the cue: a whole
utterance of PCM, some 300 kB for five seconds, which on a phone's hotspot is
the delay. The brain now sends each line ahead; this keeps it, and the cue
names it.

A take is the brain's: its key is the brain's hash of everything that shapes
the line, so the same words in the same voice and direction are the same take
here too. Kept on disk (`ROBOT_TAKES_DIR`, default `~/.cache/aura/takes`) so a
restart of the runtime between rehearsal and talk keeps them; the `KEEP` most
recently used stay. A key is checked to be a key before it touches the disk —
it arrives over the network and becomes a file name.
"""

from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_KEY = re.compile(r"^[0-9a-f]{16,64}$")


def is_key(value: str) -> bool:
    return bool(_KEY.match(value or ""))


class TakeStore:
    #: How many takes are kept; the least recently used go first. A talk has
    #: dozens of lines; a few talks' worth is plenty.
    KEEP = 300

    def __init__(self, directory: str | None = None) -> None:
        self._dir = Path(directory or os.environ.get("ROBOT_TAKES_DIR", "")
                         or Path.home() / ".cache" / "aura" / "takes")
        self._last = 0.0

    def _stamp(self, path: Path) -> None:
        """Mark as just used — strictly later than the last one, so two takes
        stored within one clock tick still have an order to keep them by."""
        self._last = max(time.time(), self._last + 0.001)
        os.utime(path, (self._last, self._last))

    def _path(self, key: str) -> Path:
        if not is_key(key):
            raise ValueError(f"not a take: {key[:40]!r}")
        return self._dir / f"{key}.pcm"

    def has(self, key: str) -> bool:
        try:
            return self._path(key).exists()
        except ValueError:
            return False

    def get(self, key: str) -> bytes | None:
        try:
            path = self._path(key)
            if not path.exists():
                return None
            data = path.read_bytes()
            self._stamp(path)                # recently used: kept longest
            return data
        except (ValueError, OSError):
            return None

    def put(self, key: str, pcm: bytes) -> None:
        path = self._path(key)               # ValueError for anything not a key
        self._dir.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pcm)
        self._stamp(path)
        kept = sorted(self._dir.glob("*.pcm"), key=lambda p: p.stat().st_mtime)
        for old in kept[:max(0, len(kept) - self.KEEP)]:
            try:
                old.unlink()
            except OSError as exc:
                logger.debug("take %s not removed: %s", old.name, exc)

    def held(self, keys: list[str]) -> list[str]:
        return [k for k in keys if self.has(k)]
