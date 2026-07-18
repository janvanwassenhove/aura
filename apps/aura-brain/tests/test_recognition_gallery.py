"""U127: per-person recognition snapshots — throttled ring + gated API."""

from __future__ import annotations

import io
import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("LLM_PROVIDER", "echo")
os.environ.setdefault("STT_PROVIDER", "null")
os.environ.setdefault("TTS_PROVIDER", "null")

import pytest
from fastapi.testclient import TestClient

from aura_brain import knowledge_api
from aura_brain.main import create_app
from aura_brain.recognition_gallery import RecognitionGallery


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
