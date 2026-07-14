"""U36f: unknown-visitor log + tagging trains recognition."""

from __future__ import annotations

import io

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aura_brain import recognition_api
from aura_brain.sightings import SightingLog
from shared_schemas.knowledge import crypto
from shared_schemas.knowledge.recognition import EmbeddingMatcher

OMK = crypto.derive_omk("test-passphrase", b"0123456789abcdef")
FACE_A = [1.0, 0.0, 0.0]
FACE_A2 = [0.95, 0.05, 0.0]  # same person, slightly different shot
FACE_B = [0.0, 1.0, 0.0]


def _png() -> bytes:
    from PIL import Image

    img = Image.new("RGB", (640, 360), (40, 40, 40))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _log(**kw) -> SightingLog:
    kw.setdefault("capture_cooldown_s", 0.0)  # deterministic in tests
    return SightingLog(**kw)


def test_same_face_merges_into_one_sighting() -> None:
    log = _log()
    log.record(_png(), FACE_A)
    log.record(_png(), FACE_A2)
    entries = log.list()
    assert len(entries) == 1
    assert entries[0]["count"] == 2


def test_different_faces_are_separate() -> None:
    log = _log()
    log.record(_png(), FACE_A)
    log.record(_png(), FACE_B)
    assert len(log.list()) == 2


def test_cooldown_suppresses_burst_captures() -> None:
    log = SightingLog(capture_cooldown_s=60.0)
    log.record(_png(), FACE_A)
    log.record(_png(), FACE_B)  # within cooldown → dropped
    assert len(log.list()) == 1


def test_log_is_capped() -> None:
    log = _log(max_entries=3, merge_threshold=0.99)
    for i in range(5):
        vec = [0.0] * 5
        vec[i] = 1.0
        log.record(_png(), vec)
    assert len(log.list()) == 3


def test_remove_and_get() -> None:
    log = _log()
    entry = log.record(_png(), FACE_A)
    assert log.get(entry.sighting_id) is not None
    assert log.remove(entry.sighting_id) is True
    assert log.get(entry.sighting_id) is None


# ── API + tagging flow ─────────────────────────────────────────────


class FakeStore:
    async def get_person(self, person_id):
        from types import SimpleNamespace

        return SimpleNamespace(display_name="Oma") if person_id == "oma" else None


@pytest.fixture()
def api():
    log = _log()
    matcher = EmbeddingMatcher(OMK)
    recognition_api.set_sightings(log)
    recognition_api.init(matcher, None, None, FakeStore())
    app = FastAPI()
    app.include_router(recognition_api.router)
    yield TestClient(app), log, matcher
    recognition_api.set_sightings(None)
    recognition_api.init(None, None, None, None)


def test_tag_enrolls_and_purges(api) -> None:
    client, log, matcher = api
    entry = log.record(_png(), FACE_A)
    log._last_capture = 0.0
    log.record(_png(), FACE_B)  # a different unknown stays

    resp = client.post(f"/recognition/sightings/{entry.sighting_id}/tag",
                       json={"person_id": "oma"})
    assert resp.status_code == 200
    assert resp.json()["tagged"] == "oma"
    # Oma is now enrolled: her face matches, the other unknown remains.
    assert matcher.identify(FACE_A2)[0] == "oma"
    remaining = log.list()
    assert len(remaining) == 1


def test_tag_unknown_person_404s(api) -> None:
    client, log, _ = api
    entry = log.record(_png(), FACE_A)
    resp = client.post(f"/recognition/sightings/{entry.sighting_id}/tag",
                       json={"person_id": "ghost"})
    assert resp.status_code == 404


def test_tag_without_matcher_409s() -> None:
    log = _log()
    entry = log.record(_png(), FACE_A)
    recognition_api.set_sightings(log)
    recognition_api.init(None, None, None, None)  # recognition not enabled
    app = FastAPI()
    app.include_router(recognition_api.router)
    resp = TestClient(app).post(
        f"/recognition/sightings/{entry.sighting_id}/tag", json={"person_id": "oma"},
    )
    assert resp.status_code == 409
    recognition_api.set_sightings(None)


def test_sighting_image_and_dismiss(api) -> None:
    client, log, _ = api
    entry = log.record(_png(), FACE_A)
    img = client.get(f"/recognition/sightings/{entry.sighting_id}/image")
    assert img.status_code == 200
    assert img.headers["content-type"] == "image/jpeg"
    assert client.delete(f"/recognition/sightings/{entry.sighting_id}").status_code == 200
    assert client.get(f"/recognition/sightings/{entry.sighting_id}/image").status_code == 404
