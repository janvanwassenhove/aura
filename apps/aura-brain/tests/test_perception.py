"""U18: perception loop + enrollment API — tested with fakes, no camera."""

from __future__ import annotations

import pytest
from aura_brain.perception import NullEmbedder, PerceptionLoop, build_embedder
from shared_schemas.events.perception import PersonRecognized
from shared_schemas.knowledge import crypto
from shared_schemas.knowledge.recognition import EmbeddingMatcher

OMK = crypto.derive_omk("test-passphrase", b"0123456789abcdef")

# Orthogonal embeddings: cosine(jan, stranger) == 0.
JAN_FACE = [1.0, 0.0, 0.0]
STRANGER_FACE = [0.0, 1.0, 0.0]


class FakeBus:
    def __init__(self) -> None:
        self.published: list = []

    async def publish(self, event) -> None:
        self.published.append(event)


class FakeRobot:
    def __init__(self) -> None:
        self.frames_served = 0

    async def camera_frame(self) -> bytes:
        self.frames_served += 1
        return b"PNG-BYTES"


class ScriptedEmbedder:
    """Returns a scripted sequence of embeddings (None = no face). After the
    sequence is exhausted it repeats the last value (enroll captures several
    frames per call, U38)."""

    name = "scripted"

    def __init__(self, sequence: list) -> None:
        self._seq = list(sequence)
        self._i = 0

    def embed(self, png_bytes: bytes):
        if self._i < len(self._seq):
            val = self._seq[self._i]
            self._i += 1
        else:
            val = self._seq[-1] if self._seq else None
        return val


class FakeStore:
    def __init__(self, people: dict[str, str]) -> None:
        self._people = people

    async def get_person(self, person_id: str):
        if person_id not in self._people:
            return None
        from types import SimpleNamespace

        return SimpleNamespace(display_name=self._people[person_id])


def _loop(embedder, matcher=None, store=None) -> tuple[PerceptionLoop, FakeBus]:
    bus = FakeBus()
    matcher = matcher or EmbeddingMatcher(OMK)
    loop = PerceptionLoop(bus, matcher, FakeRobot(), embedder, knowledge_store=store)
    return loop, bus


async def test_known_person_publishes_recognized_event() -> None:
    matcher = EmbeddingMatcher(OMK)
    matcher.enroll("jan", JAN_FACE)
    loop, bus = _loop(
        ScriptedEmbedder([JAN_FACE]), matcher, store=FakeStore({"jan": "Jan"})
    )
    await loop.tick()
    (event,) = bus.published
    assert isinstance(event, PersonRecognized)
    assert event.person_id == "jan"
    assert event.display_name == "Jan"
    assert event.known is True
    assert event.confidence > 0.99


async def test_stranger_publishes_unknown_event() -> None:
    matcher = EmbeddingMatcher(OMK)
    matcher.enroll("jan", JAN_FACE)
    loop, bus = _loop(ScriptedEmbedder([STRANGER_FACE]), matcher)
    await loop.tick()
    (event,) = bus.published
    assert event.person_id is None
    assert event.known is False


async def test_same_person_is_debounced_across_frames() -> None:
    matcher = EmbeddingMatcher(OMK)
    matcher.enroll("jan", JAN_FACE)
    loop, bus = _loop(ScriptedEmbedder([JAN_FACE, JAN_FACE, JAN_FACE]), matcher)
    for _ in range(3):
        await loop.tick()
    assert len(bus.published) == 1  # one event, not three


async def test_person_change_fires_new_event() -> None:
    matcher = EmbeddingMatcher(OMK)
    matcher.enroll("jan", JAN_FACE)
    loop, bus = _loop(ScriptedEmbedder([JAN_FACE, STRANGER_FACE]), matcher)
    await loop.tick()
    await loop.tick()
    assert len(bus.published) == 2
    assert bus.published[0].known is True
    assert bus.published[1].known is False


async def test_empty_frame_publishes_nothing() -> None:
    loop, bus = _loop(ScriptedEmbedder([None, None]))
    await loop.tick()
    await loop.tick()
    assert bus.published == []


async def test_reappearance_after_absence_fires_again() -> None:
    matcher = EmbeddingMatcher(OMK)
    matcher.enroll("jan", JAN_FACE)
    loop, bus = _loop(ScriptedEmbedder([JAN_FACE, None, JAN_FACE]), matcher)
    for _ in range(3):
        await loop.tick()
    assert len(bus.published) == 2  # greet, (absent: silent), greet again


async def test_gesture_publishes_event_with_cooldown() -> None:
    class PalmDetector:
        name = 'fake'
        def detect(self, frame):
            return 'open_palm'

    bus = FakeBus()
    loop = PerceptionLoop(
        bus, None, FakeRobot(), NullEmbedder(),
        gesture_detector=PalmDetector(), gesture_cooldown_s=60.0,
    )
    await loop.tick()
    await loop.tick()  # within cooldown → no second event
    gestures = [e for e in bus.published if getattr(e, 'gesture', None)]
    assert len(gestures) == 1
    assert gestures[0].gesture == 'open_palm'


async def test_no_matcher_treats_every_face_as_unknown() -> None:
    bus = FakeBus()
    loop = PerceptionLoop(bus, None, FakeRobot(), ScriptedEmbedder([JAN_FACE]))
    await loop.tick()
    (event,) = bus.published  # U36f: unknown-face overlay works pre-secure
    assert event.known is False and event.person_id is None


async def test_unknown_face_lands_in_sighting_log() -> None:
    from aura_brain.sightings import SightingLog

    log = SightingLog(capture_cooldown_s=0.0)
    bus = FakeBus()

    class PngRobot(FakeRobot):
        async def camera_frame(self) -> bytes:
            import io

            from PIL import Image

            buf = io.BytesIO()
            Image.new('RGB', (64, 36)).save(buf, format='PNG')
            return buf.getvalue()

    loop = PerceptionLoop(bus, None, PngRobot(), ScriptedEmbedder([JAN_FACE]),
                          sighting_log=log)
    await loop.tick()
    assert len(log.list()) == 1


async def test_known_person_lands_in_recognition_gallery() -> None:
    """U127: recognizing a KNOWN person drops a snapshot in their gallery."""
    from aura_brain.recognition_gallery import RecognitionGallery

    class PngRobot(FakeRobot):
        async def camera_frame(self) -> bytes:
            import io

            from PIL import Image

            buf = io.BytesIO()
            Image.new("RGB", (64, 48), (30, 60, 90)).save(buf, format="PNG")
            return buf.getvalue()

    matcher = EmbeddingMatcher(OMK)
    matcher.enroll("jan", JAN_FACE)
    gallery = RecognitionGallery(cooldown_s=0.0)
    bus = FakeBus()
    loop = PerceptionLoop(bus, matcher, PngRobot(), ScriptedEmbedder([JAN_FACE]),
                          knowledge_store=FakeStore({"jan": "Jan"}), gallery=gallery)
    await loop.tick()
    snaps = gallery.list("jan")
    assert len(snaps) == 1 and snaps[0]["image"].startswith("data:image/jpeg")


async def test_set_matcher_upgrades_running_loop() -> None:
    bus = FakeBus()
    loop = PerceptionLoop(bus, None, FakeRobot(), NullEmbedder())
    matcher = EmbeddingMatcher(OMK)
    matcher.enroll('jan', JAN_FACE)
    loop.set_matcher(matcher, ScriptedEmbedder([JAN_FACE]))
    await loop.tick()
    assert bus.published[0].person_id == 'jan'


async def test_null_embedder_is_default() -> None:
    assert isinstance(build_embedder("null"), NullEmbedder)
    assert isinstance(build_embedder("anything-else"), NullEmbedder)


async def test_matcher_persists_enrollment_to_disk(tmp_path) -> None:
    path = tmp_path / "recognition.enc.json"
    m1 = EmbeddingMatcher(OMK, path=path)
    m1.enroll("jan", JAN_FACE)
    # Ciphertext only on disk.
    raw = path.read_text(encoding="utf-8")
    assert "1.0" not in raw
    # A fresh matcher (brain restart) still recognizes Jan.
    m2 = EmbeddingMatcher(OMK, path=path)
    pid, conf = m2.identify(JAN_FACE)
    assert pid == "jan" and conf > 0.99
    # Forgetting erases from disk.
    m2.forget("jan")
    m3 = EmbeddingMatcher(OMK, path=path)
    assert m3.enrolled_ids() == []


# ---------------------------------------------------------------------------
# Enrollment API
# ---------------------------------------------------------------------------


@pytest.fixture()
def api_client():
    from aura_brain import recognition_api
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    matcher = EmbeddingMatcher(OMK)
    embedder = ScriptedEmbedder([JAN_FACE, JAN_FACE, JAN_FACE])
    recognition_api.init(matcher, embedder, FakeRobot(), FakeStore({"jan": "Jan"}))
    app = FastAPI()
    app.include_router(recognition_api.router)
    yield TestClient(app), matcher
    recognition_api.init(None, None, None, None)  # reset module state


def test_enroll_known_person_succeeds(api_client) -> None:
    client, matcher = api_client
    resp = client.post("/recognition/enroll", json={"person_id": "jan"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["enrolled"] == "jan" and body["ok"] is True
    assert "jan" in matcher.enrolled_ids()


def test_enroll_unknown_person_404s(api_client) -> None:
    client, _ = api_client
    resp = client.post("/recognition/enroll", json={"person_id": "ghost"})
    assert resp.status_code == 404


def test_enroll_without_face_422s() -> None:
    from aura_brain import recognition_api
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    recognition_api.init(
        EmbeddingMatcher(OMK), ScriptedEmbedder([None, None, None, None]), FakeRobot(),
        FakeStore({"jan": "Jan"}),
    )
    app = FastAPI()
    app.include_router(recognition_api.router)
    resp = TestClient(app).post("/recognition/enroll", json={"person_id": "jan"})
    assert resp.status_code == 422
    recognition_api.init(None, None, None, None)


def test_forget_removes_enrollment(api_client) -> None:
    client, matcher = api_client
    client.post("/recognition/enroll", json={"person_id": "jan"})
    resp = client.delete("/recognition/people/jan")
    assert resp.status_code == 200
    assert matcher.enrolled_ids() == []


def test_status_reports_enrollment(api_client) -> None:
    client, _ = api_client
    client.post("/recognition/enroll", json={"person_id": "jan"})
    body = client.get("/recognition/status").json()
    assert body["enabled"] is True
    assert body["enrolled"] == ["jan"]


# ---------------------------------------------------------------------------
# U181: a new face becomes a guest profile
# ---------------------------------------------------------------------------

class RecordingStore(FakeStore):
    """FakeStore that also accepts new people, like the real knowledge store."""

    def __init__(self, people: dict[str, str] | None = None) -> None:
        super().__init__(people or {})
        self.created: list = []

    async def list_people(self):
        from types import SimpleNamespace

        return [SimpleNamespace(person_id=pid) for pid in self._people]

    async def upsert_person(self, person):
        self.created.append(person)
        self._people[person.person_id] = person.display_name
        return person


def _guest_loop(store, embedder, matcher):
    from aura_brain.sightings import SightingLog

    bus = FakeBus()
    loop = PerceptionLoop(
        bus, matcher, FakeRobot(), embedder,
        knowledge_store=store, sighting_log=SightingLog(),
    )
    return loop, bus


async def test_new_face_becomes_a_guest(monkeypatch) -> None:
    monkeypatch.setenv("AUTO_GUEST", "true")
    monkeypatch.setattr("aura_brain.sightings._thumbnail", lambda b, width=320: b"JPG")
    store = RecordingStore()
    matcher = EmbeddingMatcher(OMK)
    loop, bus = _guest_loop(store, ScriptedEmbedder([STRANGER_FACE]), matcher)

    await loop.tick()

    assert len(store.created) == 1
    guest = store.created[0]
    assert guest.person_id == "guest-1"
    assert guest.display_name == "Guest 1"
    assert guest.role.value == "guest"          # minimal role by design
    # Enrolled, so the SAME face is recognised from now on instead of "unknown".
    assert matcher.identify(STRANGER_FACE)[0] == "guest-1"
    (event,) = bus.published
    assert event.known is True and event.person_id == "guest-1"


async def test_same_face_does_not_spawn_a_second_guest(monkeypatch) -> None:
    """The sighting log merges repeats; enrolment makes later frames 'known'."""
    monkeypatch.setenv("AUTO_GUEST", "true")
    monkeypatch.setattr("aura_brain.sightings._thumbnail", lambda b, width=320: b"JPG")
    store = RecordingStore()
    matcher = EmbeddingMatcher(OMK)
    loop, _ = _guest_loop(store, ScriptedEmbedder([STRANGER_FACE]), matcher)

    await loop.tick()
    await loop.tick()
    await loop.tick()

    assert [p.person_id for p in store.created] == ["guest-1"]


async def test_guest_ids_do_not_collide(monkeypatch) -> None:
    monkeypatch.setenv("AUTO_GUEST", "true")
    monkeypatch.setattr("aura_brain.sightings._thumbnail", lambda b, width=320: b"JPG")
    store = RecordingStore({"guest-1": "Guest 1"})       # guest-1 already taken
    loop, _ = _guest_loop(store, ScriptedEmbedder([STRANGER_FACE]), EmbeddingMatcher(OMK))

    await loop.tick()

    assert store.created[0].person_id == "guest-2"


async def test_auto_guest_can_be_switched_off(monkeypatch) -> None:
    monkeypatch.setenv("AUTO_GUEST", "false")
    monkeypatch.setattr("aura_brain.sightings._thumbnail", lambda b, width=320: b"JPG")
    store = RecordingStore()
    loop, bus = _guest_loop(store, ScriptedEmbedder([STRANGER_FACE]), EmbeddingMatcher(OMK))

    await loop.tick()

    assert store.created == []                  # no biometrics captured
    (event,) = bus.published
    assert event.known is False                 # still just an unknown sighting
