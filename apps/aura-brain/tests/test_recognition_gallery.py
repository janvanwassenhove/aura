"""U127: per-person recognition snapshots — throttled ring + gated API."""

from __future__ import annotations

import io
import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("LLM_PROVIDER", "echo")
os.environ.setdefault("STT_PROVIDER", "null")
os.environ.setdefault("TTS_PROVIDER", "null")

from aura_brain import knowledge_api
from aura_brain.main import create_app
from aura_brain.recognition_gallery import RecognitionGallery
from fastapi.testclient import TestClient


def _png(color=(80, 120, 200)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color).save(buf, format="PNG")
    return buf.getvalue()


def test_gallery_throttles_and_caps() -> None:
    g = RecognitionGallery(per_person=3, cooldown_s=1000.0)
    assert g.record("jan", _png(), 0.9) is not None
    # Same person within the cooldown → throttled.
    assert g.record("jan", _png(), 0.9) is None
    assert len(g.list("jan")) == 1

    g2 = RecognitionGallery(per_person=2, cooldown_s=0.0)
    for _ in range(5):
        g2.record("jan", _png(), 0.8)
    assert len(g2.list("jan")) == 2  # capped, newest first


def test_gallery_list_returns_data_uri() -> None:
    g = RecognitionGallery(cooldown_s=0.0)
    g.record("jan", _png(), 0.77)
    item = g.list("jan")[0]
    assert item["image"].startswith("data:image/jpeg;base64,")
    assert item["confidence"] == 0.77
    assert g.list("nobody") == []


def test_gallery_forget() -> None:
    g = RecognitionGallery(cooldown_s=0.0)
    g.record("jan", _png(), 0.9)
    assert g.forget("jan") == 1
    assert g.list("jan") == []


def test_snapshots_endpoint_and_forget_wipes() -> None:
    gallery = RecognitionGallery(cooldown_s=0.0)
    app = create_app()
    with TestClient(app) as client:
        knowledge_api.set_recognition_gallery(gallery)
        client.put("/knowledge/people/jan", json={"display_name": "Jan", "role": "owner"})
        gallery.record("jan", _png(), 0.95)

        r = client.get("/knowledge/people/jan/snapshots")
        assert r.status_code == 200
        snaps = r.json()["snapshots"]
        assert len(snaps) == 1 and snaps[0]["image"].startswith("data:image/jpeg")

        # Forgetting the person wipes their snapshots too.
        client.delete("/knowledge/people/jan")
        assert client.get("/knowledge/people/jan/snapshots").json()["snapshots"] == []


# ------------------------------------------------------------------
# U136: flag a misrecognition → removed + re-filed for correct tagging
# ------------------------------------------------------------------

def test_mark_wrong_removes_and_returns_snapshot() -> None:
    g = RecognitionGallery(cooldown_s=0.0)
    a = g.record("jan", _png(), 0.9, embedding=[0.1, 0.2])
    b = g.record("jan", _png((10, 20, 30)), 0.8, embedding=[0.3, 0.4])
    assert len(g.list("jan")) == 2

    removed = g.mark_wrong("jan", a.snapshot_id)
    assert removed is not None and removed.embedding == [0.1, 0.2]
    remaining = g.list("jan")
    assert len(remaining) == 1 and remaining[0]["snapshot_id"] == b.snapshot_id
    # Unknown ids are a no-op.
    assert g.mark_wrong("jan", "nope") is None
    assert g.mark_wrong("ghost", a.snapshot_id) is None


def test_wrong_endpoint_refiles_for_tagging() -> None:
    from aura_brain import recognition_api
    from aura_brain.sightings import SightingLog

    gallery = RecognitionGallery(cooldown_s=0.0)
    log = SightingLog(capture_cooldown_s=0.0)
    app = create_app()
    with TestClient(app) as client:
        knowledge_api.set_recognition_gallery(gallery)
        recognition_api.set_sightings(log)
        client.put("/knowledge/people/jappe", json={"display_name": "Jappe", "role": "family"})
        snap = gallery.record("jappe", _png(), 0.71, embedding=[0.5, 0.6])

        r = client.post(f"/knowledge/people/jappe/snapshots/{snap.snapshot_id}/wrong")
        assert r.status_code == 200
        body = r.json()
        assert body["removed"] == snap.snapshot_id
        assert body["refiled_for_tagging"] is True
        # Gone from the person, and back in the unknown-visitor log to re-tag.
        assert client.get("/knowledge/people/jappe/snapshots").json()["snapshots"] == []
        assert len(log.list()) == 1

        assert client.post("/knowledge/people/jappe/snapshots/bogus/wrong").status_code == 404


# ---------------------------------------------------------------------------
# U189: assign a guest to a real person (face moves, guest is absorbed)
# ---------------------------------------------------------------------------

async def test_merge_moves_face_and_absorbs_the_guest() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from aura_brain import recognition_api
    from shared_schemas.knowledge import InMemoryKnowledgeStore, crypto
    from shared_schemas.knowledge.models import Person, PersonRole
    from shared_schemas.knowledge.recognition import EmbeddingMatcher

    store = InMemoryKnowledgeStore()
    await store.upsert_person(Person(person_id="piet", display_name="Piet",
                                     role=PersonRole.FAMILY))
    await store.upsert_person(Person(person_id="guest-1", display_name="Guest 1",
                                     role=PersonRole.GUEST))
    matcher = EmbeddingMatcher(crypto.derive_omk("pw", b"0123456789abcdef"))
    face = [1.0, 0.0, 0.0]
    matcher.enroll("guest-1", face)
    recognition_api.init(matcher, None, None, store)

    app = FastAPI()
    app.include_router(recognition_api.router)
    client = TestClient(app)

    r = client.post("/recognition/merge",
                    json={"from_person_id": "guest-1", "to_person_id": "piet"})

    assert r.status_code == 200 and r.json()["faces_moved"] == 1
    assert matcher.identify(face)[0] == "piet"        # recognised as Piet now
    assert await store.get_person("guest-1") is None  # guest absorbed
    assert await store.get_person("piet") is not None


async def test_merge_rejects_unknown_target_and_self_merge() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from aura_brain import recognition_api
    from shared_schemas.knowledge import InMemoryKnowledgeStore, crypto
    from shared_schemas.knowledge.models import Person, PersonRole
    from shared_schemas.knowledge.recognition import EmbeddingMatcher

    store = InMemoryKnowledgeStore()
    await store.upsert_person(Person(person_id="guest-1", display_name="Guest 1",
                                     role=PersonRole.GUEST))
    recognition_api.init(EmbeddingMatcher(crypto.derive_omk("pw", b"0123456789abcdef")),
                         None, None, store)
    app = FastAPI()
    app.include_router(recognition_api.router)
    client = TestClient(app)

    assert client.post("/recognition/merge",
                       json={"from_person_id": "guest-1", "to_person_id": "nobody"}
                       ).status_code == 404
    assert client.post("/recognition/merge",
                       json={"from_person_id": "guest-1", "to_person_id": "guest-1"}
                       ).status_code == 422
    assert await store.get_person("guest-1") is not None   # nothing destroyed
