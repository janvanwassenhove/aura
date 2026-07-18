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
import os
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


_HAND_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/latest/hand_landmarker.task"
)


class HandGestureDetector:
    """Open-palm ('hi!') detection via mediapipe hand landmarks (U36e).

    No stored data, no identity — a transient reaction trigger only. Uses a
    landmark heuristic (four fingers extended, hand upright). The small
    hand-landmarker model (~8 MB) downloads once to ./data/models/.
    """

    name = "mediapipe-hands"

    def __init__(self) -> None:
        from pathlib import Path

        from mediapipe.tasks import python as mp_python  # lazy: [gestures] extra
        from mediapipe.tasks.python import vision

        model_path = Path(os.environ.get(
            "GESTURE_MODEL_PATH", "./data/models/hand_landmarker.task",
        ))
        if not model_path.exists():
            import urllib.request

            model_path.parent.mkdir(parents=True, exist_ok=True)
            logger.info("downloading hand-landmarker model (once) → %s", model_path)
            urllib.request.urlretrieve(_HAND_MODEL_URL, model_path)  # noqa: S310

        self._landmarker = vision.HandLandmarker.create_from_options(
            vision.HandLandmarkerOptions(
                base_options=mp_python.BaseOptions(model_asset_path=str(model_path)),
                num_hands=1,
                min_hand_detection_confidence=0.6,
            )
        )

    def detect(self, png_bytes: bytes) -> str | None:
        """Return a gesture name ('open_palm') or None."""
        import io

        import mediapipe as mp
        import numpy as np
        from PIL import Image

        img = np.asarray(Image.open(io.BytesIO(png_bytes)).convert("RGB"))
        result = self._landmarker.detect(
            mp.Image(image_format=mp.ImageFormat.SRGB, data=img)
        )
        if not result.hand_landmarks:
            return None
        lm = result.hand_landmarks[0]
        # Fingers extended: tip above (smaller y than) its middle joint.
        extended = sum(1 for tip, pip in ((8, 6), (12, 10), (16, 14), (20, 18))
                       if lm[tip].y < lm[pip].y)
        # Hand raised: wrist below the middle-finger base (hand pointing up).
        upright = lm[0].y > lm[9].y
        if extended >= 4 and upright:
            return "open_palm"
        # Thumbs up: thumb clearly extended upward, all four fingers folded.
        thumb_up = lm[4].y < lm[3].y < lm[2].y
        if thumb_up and extended == 0:
            return "thumbs_up"
        return None


def build_gesture_detector():
    """HandGestureDetector, or None when mediapipe is unavailable/broken."""
    try:
        return HandGestureDetector()
    except Exception as exc:  # noqa: BLE001 — gestures must never block startup
        logger.info("gesture detector unavailable (%s) — reactions inert "
                    "(uv sync --package aura-brain --extra gestures)", exc)
        return None


def build_embedder(kind: str) -> FaceEmbedder:
    if kind == "insightface":
        try:
            return InsightFaceEmbedder()
        except ImportError:
            logger.warning(
                "FACE_EMBEDDER=insightface but the model stack is not installed "
                "(uv sync --package aura-brain --extra recognition) — recognition inert."
            )
            return NullEmbedder()
    return NullEmbedder()


class PerceptionLoop:
    """Polls the robot camera and publishes debounced PersonRecognized events."""

    def __init__(
        self,
        bus: Any,
        matcher: Any,          # EmbeddingMatcher | None (recognition off)
        robot: Any,            # RobotClient (needs .camera_frame())
        embedder: FaceEmbedder,
        knowledge_store: Any = None,  # for display_name lookup
        interval_s: float = 2.0,
        session_id: str = "default",
        gesture_detector: Any = None,  # HandGestureDetector | None (U36e)
        gesture_cooldown_s: float = 8.0,
        sighting_log: Any = None,      # SightingLog | None (U36f)
        gallery: Any = None,           # RecognitionGallery | None (U127)
    ) -> None:
        self._bus = bus
        self._matcher = matcher
        self._robot = robot
        self._embedder = embedder
        self._store = knowledge_store
        self._interval = interval_s
        self._session_id = session_id
        self._gestures = gesture_detector
        self._gesture_cooldown = gesture_cooldown_s
        self._sightings = sighting_log
        self._gallery = gallery
        self._last_gesture_at = 0.0
        self._task: asyncio.Task | None = None
        self._last_seen: str | None = None  # person_id | _ABSENT | None(=never)

    def set_matcher(self, matcher: Any, embedder: FaceEmbedder) -> None:
        """Upgrade a running loop with recognition (in-app secure enable)."""
        self._matcher = matcher
        self._embedder = embedder

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
        """One frame → gestures + recognition → (maybe) events. Public for tests."""
        frame = await self._robot.camera_frame()

        # Gestures (U36e): transient reaction trigger, no identity required.
        if self._gestures is not None:
            await self._detect_gesture(frame)

        embedding = await asyncio.to_thread(self._embedder.embed, frame)

        if embedding is None:
            await self._transition(_ABSENT, None, 0.0)
            return

        if self._matcher is not None:
            person_id, confidence = self._matcher.identify(embedding)
        else:
            person_id, confidence = None, 0.0  # recognition not enabled (yet)

        # U36f: log unrecognized passers-by (in-memory only) for easy tagging.
        if person_id is None and self._sightings is not None:
            self._sightings.record(frame, embedding)
        # U127: snapshot KNOWN people so the owner can review recent sightings
        # per person (throttled + capped in the gallery).
        if person_id is not None and self._gallery is not None:
            self._gallery.record(person_id, frame, confidence)

        await self._transition(person_id or "", person_id, confidence)

    async def _detect_gesture(self, frame: bytes) -> None:
        import time

        if time.monotonic() - self._last_gesture_at < self._gesture_cooldown:
            return
        try:
            gesture = await asyncio.to_thread(self._gestures.detect, frame)
        except Exception as exc:  # noqa: BLE001 — detector hiccups are non-fatal
            logger.debug("gesture detect failed: %s", exc)
            return
        if gesture is None:
            return
        self._last_gesture_at = time.monotonic()
        from shared_schemas.events.perception import GestureDetected

        await self._bus.publish(GestureDetected(
            session_id=self._session_id, gesture=gesture, confidence=0.8,
        ))
        logger.info("GestureDetected: %s", gesture)

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
