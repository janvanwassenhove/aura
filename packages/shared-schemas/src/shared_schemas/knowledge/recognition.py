"""Face-recognition matching over ENCRYPTED embeddings (U18 + ADR-008).

The camera + the model that turns a frame into an embedding live on the robot
(🔒 hardware). This module is the part that needs neither: it enrolls and matches
face *embeddings* (vectors) and decides who is present. Embeddings are biometric
data → stored encrypted at rest (AES-256-GCM under the OMK); plaintext vectors
exist only transiently during a match. `RecognitionLink` (knowledge store) maps
the opaque ref → person; this holds the actual (encrypted) vectors.
"""

from __future__ import annotations

import base64
import json
import math
import os
from pathlib import Path

from shared_schemas.knowledge import crypto

_DEFAULT_THRESHOLD = 0.6  # cosine similarity above which a face counts as a match


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class EmbeddingMatcher:
    def __init__(
        self,
        omk: bytes,
        threshold: float = _DEFAULT_THRESHOLD,
        path: str | Path | None = None,
    ) -> None:
        if len(omk) != 32:
            raise ValueError("OMK must be 32 bytes (AES-256).")
        self._omk = omk
        self._threshold = threshold
        self._enrolled: dict[str, bytes] = {}  # person_id -> encrypted embedding
        # Optional disk persistence (ciphertext only — same rules as U29).
        self._path = Path(path) if path is not None else None
        if self._path is not None and self._path.exists():
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._enrolled = {
                pid: base64.b64decode(blob) for pid, blob in data.get("embeddings", {}).items()
            }

    def _flush(self) -> None:
        if self._path is None:
            return
        data = {
            "version": 1,
            "embeddings": {
                pid: base64.b64encode(blob).decode() for pid, blob in self._enrolled.items()
            },
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, self._path)

    def enroll(self, person_id: str, embedding: list[float]) -> None:
        """Store (encrypted) a reference embedding for a known person."""
        blob = crypto.encrypt(
            self._omk, json.dumps(embedding).encode(), aad=person_id.encode()
        )
        self._enrolled[person_id] = blob
        self._flush()

    def forget(self, person_id: str) -> None:
        self._enrolled.pop(person_id, None)
        self._flush()  # erasure must reach disk too

    def identify(self, embedding: list[float]) -> tuple[str | None, float]:
        """Return (person_id, confidence) for the best match, or (None, score)
        if nothing clears the threshold (a stranger)."""
        best_id: str | None = None
        best_score = 0.0
        for pid, blob in self._enrolled.items():
            ref = json.loads(crypto.decrypt(self._omk, blob, aad=pid.encode()))
            score = _cosine(embedding, ref)
            if score > best_score:
                best_id, best_score = pid, score
        if best_id is not None and best_score >= self._threshold:
            return best_id, best_score
        return None, best_score

    def enrolled_ids(self) -> list[str]:
        return list(self._enrolled)
