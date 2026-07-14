"""Unknown-visitor log (U36f): who walked past that AURA didn't recognize?

Privacy by design (ADR-008): unknown faces belong to people who never
consented, so sightings live IN MEMORY ONLY — nothing touches disk, and a
brain restart wipes them. Sightings of the same person are merged (embedding
cosine similarity) instead of stacking up, the log is capped, and entries
expire. Tagging a sighting enrolls its embedding into the ENCRYPTED matcher —
that is the moment it becomes durable, tied to a known person.
"""

from __future__ import annotations

import io
import math
import time
from dataclasses import dataclass, field
from uuid import uuid4


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _thumbnail(png_bytes: bytes, width: int = 320) -> bytes:
    from PIL import Image

    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    ratio = width / img.width
    img = img.resize((width, max(1, int(img.height * ratio))))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return buf.getvalue()


@dataclass
class Sighting:
    embedding: list[float]
    thumbnail: bytes  # small JPEG
    sighting_id: str = field(default_factory=lambda: str(uuid4()))
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    count: int = 1


class SightingLog:
    def __init__(
        self,
        max_entries: int = 12,
        merge_threshold: float = 0.5,
        capture_cooldown_s: float = 15.0,
        expiry_s: float = 24 * 3600,
    ) -> None:
        self._entries: list[Sighting] = []
        self._max = max_entries
        self._merge_threshold = merge_threshold
        self._cooldown = capture_cooldown_s
        self._expiry = expiry_s
        self._last_capture = 0.0

    def record(self, frame_png: bytes, embedding: list[float]) -> Sighting | None:
        """Merge into an existing sighting of the same person, or append."""
        now = time.time()
        self._expire(now)
        if now - self._last_capture < self._cooldown:
            return None
        self._last_capture = now

        for entry in self._entries:
            if _cosine(embedding, entry.embedding) >= self._merge_threshold:
                entry.last_seen = now
                entry.count += 1
                entry.thumbnail = _thumbnail(frame_png)  # freshest look
                return entry

        sighting = Sighting(embedding=embedding, thumbnail=_thumbnail(frame_png))
        self._entries.insert(0, sighting)
        del self._entries[self._max:]  # cap: oldest fall off
        return sighting

    def list(self) -> list[dict]:
        self._expire(time.time())
        return [
            {
                "sighting_id": e.sighting_id,
                "first_seen": e.first_seen,
                "last_seen": e.last_seen,
                "count": e.count,
            }
            for e in self._entries
        ]

    def get(self, sighting_id: str) -> Sighting | None:
        return next((e for e in self._entries if e.sighting_id == sighting_id), None)

    def remove(self, sighting_id: str) -> bool:
        before = len(self._entries)
        self._entries = [e for e in self._entries if e.sighting_id != sighting_id]
        return len(self._entries) != before

    def purge_matching(self, matcher) -> int:
        """Drop sightings that the (just-updated) matcher now recognizes."""
        kept: list[Sighting] = []
        removed = 0
        for entry in self._entries:
            person_id, _ = matcher.identify(entry.embedding)
            if person_id is None:
                kept.append(entry)
            else:
                removed += 1
        self._entries = kept
        return removed

    def _expire(self, now: float) -> None:
        self._entries = [e for e in self._entries if now - e.last_seen < self._expiry]
