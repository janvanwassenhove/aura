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

# Cosine similarity above which a face counts as a match. Tuned for insightface
# ArcFace normed embeddings, where genuine same-person pairs sit ~0.4-0.8 and
# different people <0.3. 0.6 was far too strict (real matches rejected → the
# owner kept reading as "unknown"). Override with RECOGNITION_THRESHOLD.
_DEFAULT_THRESHOLD = float(os.environ.get("RECOGNITION_THRESHOLD", "0.4"))
_MAX_SAMPLES_PER_PERSON = 8  # keep several shots (angles/light) → robust matching


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
        # person_id -> list of encrypted embeddings (several shots per person).
        self._enrolled: dict[str, list[bytes]] = {}
        # Optional disk persistence (ciphertext only — same rules as U29).
        self._path = Path(path) if path is not None else None
        if self._path is not None and self._path.exists():
            data = json.loads(self._path.read_text(encoding="utf-8"))
            for pid, val in data.get("embeddings", {}).items():
                blobs = val if isinstance(val, list) else [val]  # v1 = single blob
                self._enrolled[pid] = [base64.b64decode(b) for b in blobs]

    def _flush(self) -> None:
        if self._path is None:
            return
        data = {
            "version": 2,
            "embeddings": {
                pid: [base64.b64encode(b).decode() for b in blobs]
                for pid, blobs in self._enrolled.items()
            },
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, self._path)

    def enroll(self, person_id: str, embedding: list[float]) -> None:
        """Add an (encrypted) reference embedding. Keeps several shots per
        person so lighting/angle differences still match; oldest fall off."""
        blob = crypto.encrypt(
            self._omk, json.dumps(embedding).encode(), aad=person_id.encode()
        )
        samples = self._enrolled.setdefault(person_id, [])
        samples.append(blob)
        del samples[:-_MAX_SAMPLES_PER_PERSON]  # cap
        self._flush()

    def forget(self, person_id: str) -> None:
        self._enrolled.pop(person_id, None)
        self._flush()  # erasure must reach disk too

    def transfer(self, from_person_id: str, to_person_id: str) -> int:
        """U189: move every enrolled face from one person to another.

        Used when the owner assigns an auto-created guest to a real person:
        the face must keep working under the target's id. Samples cannot be
        copied as-is — each blob is AES-GCM bound to its person via AAD — so
        they are decrypted under the source id and re-encrypted under the
        target. The source is then forgotten (cryptographic erasure).

        Returns how many samples moved.
        """
        blobs = self._enrolled.get(from_person_id, [])
        moved = 0
        for blob in blobs:
            try:
                embedding = json.loads(
                    crypto.decrypt(self._omk, blob, aad=from_person_id.encode()))
            except Exception:  # noqa: BLE001 — skip an unreadable sample
                continue
            self.enroll(to_person_id, embedding)   # re-encrypts + flushes
            moved += 1
        self.forget(from_person_id)
        return moved

    def sample_count(self, person_id: str) -> int:
        return len(self._enrolled.get(person_id, []))

    def identify(self, embedding: list[float]) -> tuple[str | None, float]:
        """Return (person_id, confidence) for the best match over ALL of each
        person's samples, or (None, score) if nothing clears the threshold."""
        best_id: str | None = None
        best_score = 0.0
        for pid, blobs in self._enrolled.items():
            for blob in blobs:
                ref = json.loads(crypto.decrypt(self._omk, blob, aad=pid.encode()))
                score = _cosine(embedding, ref)
                if score > best_score:
                    best_id, best_score = pid, score
        if best_id is not None and best_score >= self._threshold:
            return best_id, best_score
        return None, best_score

    def enrolled_ids(self) -> list[str]:
        return list(self._enrolled)
