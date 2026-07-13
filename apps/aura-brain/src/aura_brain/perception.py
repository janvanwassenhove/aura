"""U18 — live perception loop: camera frame → face embedding → PersonRecognized.

The loop polls the robot's camera over the one brain↔robot network hop, turns
frames into face embeddings via a pluggable ``FaceEmbedder``, matches them
against the encrypted ``EmbeddingMatcher``, and publishes ``PersonRecognized``
on the shared bus. The pipeline (U19e) and the console (U28) already consume
that event — this closes the loop.

Recognition IDENTIFIES, it never AUTHENTICATES (ADR-008): a match personalizes
greetings and context; it unlocks nothing.

Embedders:
  - ``NullEmbedder``       — always "no face"; keeps the loop inert without a model.
  - ``InsightFaceEmbedder``— real face recognition via the optional
    ``insightface`` + ``onnxruntime`` stack (install the brain's
    ``[recognition]`` extra). Lazy-imported.

Events are debounced: a ``PersonRecognized`` fires when the detected person
CHANGES (including → unknown/absent), not on every frame.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol

from shared_schemas.events.perception import PersonRecognized

logger = logging.getLogger(__name__)

_ABSENT = "__absent__"  # sentinel for "no face in frame" in the debouncer


class FaceEmbedder(Protocol):
    """Turns an image (PNG bytes) into a face embedding, or None if no face."""

    name: str

    def embed(self, png_bytes: bytes) -> list[float] | None: ...


class NullEmbedder:
    """No model installed: never sees a face. The loop stays inert."""

    name = "null"

    def embed(self, png_bytes: bytes) -> list[float] | None:
        return None


class InsightFaceEmbedder:
    """Real face embeddings (512-d ArcFace) via insightface. Optional extra.

    CPU-only by default; the model downloads once to ~/.insightface on first use.
    """

    name = "insightface"

    def __init__(self, model_name: str = "buffalo_l") -> None:
        import numpy as np  # noqa: F401 — required by insightface
        from insightface.app import FaceAnalysis  # lazy: optional dependency

        self._app = FaceAnalysis(name=model_name, providers=["CPUExecutionProvider"])
        self._app.prepare(ctx_id=-1)

    def embed(self, png_bytes: bytes) -> list[float] | None:
        import io

        import numpy as np
        from PIL import Image

        img = np.asarray(Image.open(io.BytesIO(png_bytes)).convert("RGB"))[:, :, ::-1]
        faces = self._app.get(img)
        if not faces:
            return None
        # Largest face in frame wins (the person actually in front of the robot).
        face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
        return [float(x) for x in face.normed_embedding]


def build_embedder(kind: str) -> FaceEmbedder:
    if kind == "insightface":
        return InsightFaceEmbedder()
    return NullEmbedder()


class PerceptionLoop:
    """Polls the robot camera and publishes debounced PersonRecognized events."""

    def __init__(
        self,
        bus: Any,
        matcher: Any,          # EmbeddingMatcher
        robot: Any,            # RobotClient (needs .camera_frame())
        embedder: FaceEmbedder,
        knowledge_store: Any = None,  # for display_name lookup
        interval_s: float = 2.0,
        session_id: str = "default",
    ) -> None:
        self._bus = bus
        self._matcher = matcher
        self._robot = robot
        self._embedder = embedder
        self._store = knowledge_store
        self._interval = interval_s
        self._session_id = session_id
        self._task: asyncio.Task | None = None
        self._last_seen: str | None = None  # person_id | _ABSENT | None(=never)

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())
            logger.info("PerceptionLoop started (embedder=%s, every %.1fs)",
                        self._embedder.name, self._interval)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # camera hiccups must not kill the loop
                logger.debug("perception tick failed: %s", exc)
            await asyncio.sleep(self._interval)

    async def tick(self) -> None:
        """One frame → embedding → match → (maybe) event. Public for tests."""
        frame = await self._robot.camera_frame()
        embedding = await asyncio.to_thread(self._embedder.embed, frame)

        if embedding is None:
            await self._transition(_ABSENT, None, 0.0)
            return

        person_id, confidence = self._matcher.identify(embedding)
        await self._transition(person_id or "", person_id, confidence)

    async def _transition(self, seen_key: str, person_id: str | None, confidence: float) -> None:
        if seen_key == self._last_seen:
            return  # debounce: same situation as the previous frame
        self._last_seen = seen_key
        if seen_key == _ABSENT:
            # Nobody in frame: clear the active person (pipeline stops injecting
            # personal context) but don't spam an event.
            return
        display_name = None
        if person_id and self._store is not None:
            person = await self._store.get_person(person_id)
            display_name = person.display_name if person else None
        await self._bus.publish(PersonRecognized(
            session_id=self._session_id,
            person_id=person_id,
            display_name=display_name,
            confidence=round(confidence, 3),
            known=person_id is not None,
        ))
        logger.info("PersonRecognized: %s (%.2f)", display_name or "unknown", confidence)
