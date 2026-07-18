"""U127: per-person recognition snapshots — what did Richie see when he
recognized you?

When perception recognizes a KNOWN person it can drop a small snapshot here,
keyed by person_id, so the owner can review "recent sightings of Jan" in the
brain profile.

Privacy (ADR-008): these are face images of KNOWN people, so they stay IN
MEMORY ONLY (a brain restart wipes them), are capped per person, throttled so
one visit isn't 500 frames, and are served only under the SENSITIVE unlock
tier (the API gates them). Nothing touches disk; nothing leaves the machine.
"""

from __future__ import annotations

import base64
import io
import time
from collections import deque
from dataclasses import dataclass, field
from uuid import uuid4


def _thumbnail(png_bytes: bytes, width: int = 240) -> bytes:
    from PIL import Image

    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    ratio = width / img.width
    img = img.resize((width, max(1, int(img.height * ratio))))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=68)
    return buf.getvalue()


@dataclass
class Snapshot:
    thumbnail: bytes                      # small JPEG
    confidence: float
    snapshot_id: str = field(default_factory=lambda: str(uuid4()))
    seen_at: float = field(default_factory=time.time)
    # U136: the face embedding behind this match. Kept so that flagging the
    # snapshot as WRONG can re-file it for correct tagging (which re-enrols it
    # against the right person and improves recognition).
    embedding: list[float] | None = None
    frame: bytes | None = None            # full frame, for re-filing


class RecognitionGallery:
    """In-memory ring of recent recognition snapshots per known person."""

    def __init__(self, per_person: int = 6, cooldown_s: float = 20.0) -> None:
        self._by_person: dict[str, deque[Snapshot]] = {}
        self._per_person = per_person
        self._cooldown = cooldown_s
        self._last_capture: dict[str, float] = {}

    def record(
        self,
        person_id: str,
        frame_png: bytes,
        confidence: float,
        embedding: list[float] | None = None,
    ) -> Snapshot | None:
        """Store a throttled snapshot for a recognized person. Best-effort."""
        if not person_id:
            return None
        now = time.time()
        if now - self._last_capture.get(person_id, 0.0) < self._cooldown:
            return None
        try:
            thumb = _thumbnail(frame_png)
        except Exception:  # noqa: BLE001 — a bad frame must never break perception
            return None
        self._last_capture[person_id] = now
        ring = self._by_person.setdefault(person_id, deque(maxlen=self._per_person))
        snap = Snapshot(thumbnail=thumb, confidence=round(confidence, 3),
                        embedding=embedding, frame=frame_png)
        ring.appendleft(snap)
        return snap

    def mark_wrong(self, person_id: str, snapshot_id: str) -> Snapshot | None:
        """U136: 'that isn't them' — drop the snapshot and hand it back so the
        caller can re-file it as an unknown sighting for correct tagging."""
        ring = self._by_person.get(person_id)
        if not ring:
            return None
        found = next((s for s in ring if s.snapshot_id == snapshot_id), None)
        if found is None:
            return None
        remaining = [s for s in ring if s.snapshot_id != snapshot_id]
        ring.clear()
        ring.extend(remaining)
        # Let a corrected face be re-captured straight away.
        self._last_capture.pop(person_id, None)
        return found

    def list(self, person_id: str) -> list[dict]:
        """Newest first — data URIs so the console renders them inline."""
        ring = self._by_person.get(person_id)
        if not ring:
            return []
        return [
            {
                "snapshot_id": s.snapshot_id,
                "seen_at": s.seen_at,
                "confidence": s.confidence,
                "image": "data:image/jpeg;base64," + base64.b64encode(s.thumbnail).decode(),
            }
            for s in ring
        ]

    def forget(self, person_id: str) -> int:
        """Drop all snapshots of a person (used by right-to-be-forgotten)."""
        removed = len(self._by_person.pop(person_id, []) or [])
        self._last_capture.pop(person_id, None)
        return removed
