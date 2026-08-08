"""U213: teaching a face must say the TRUTH about what happened."""

from __future__ import annotations

from aura_brain import recognition_api
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(recognition_api.router)
    return TestClient(app)


class _NullEmbedder:
    name = "null"
    def embed(self, frame):  # never sees a face
        return None


class _RealEmbedder:
    name = "insightface"
    def __init__(self): self.calls = 0
    def embed(self, frame):
        self.calls += 1
        return [0.1, 0.2, 0.3]


class _Matcher:
    def __init__(self): self.samples = {}
    def enroll(self, pid, emb): self.samples[pid] = self.samples.get(pid, 0) + 1
    def identify(self, emb): return ("jan", 0.9)
    def sample_count(self, pid): return self.samples.get(pid, 0)


class _Robot:
    async def camera_frame(self): return b"\x89PNG frame"


class _Store:
    def __init__(self): self._p = {"jan": type("P", (), {"avatar": "x"})()}
    async def get_person(self, pid): return self._p.get(pid)
    async def upsert_person(self, p): ...


def _wire(embedder):
    recognition_api._matcher = _Matcher()
    recognition_api._embedder = embedder
    recognition_api._robot = _Robot()
    recognition_api._store = _Store()


def test_null_embedder_says_recognition_is_not_installed() -> None:
    """The reported bug: with no model, teaching returned 'no face in frame —
    look straight at the robot', sending the owner after a phantom positioning
    problem. It must name the real cause instead."""
    _wire(_NullEmbedder())
    r = _client().post("/recognition/enroll", json={"person_id": "jan"})
    assert r.status_code == 503
    body = r.json()
    assert body["reason"] == "embedder_unavailable"
    assert "isn't installed" in body["error"]
    assert "no face in frame" not in body["error"].lower()


def test_real_embedder_reports_samples_for_a_positive_confirmation() -> None:
    """A working teach returns the sample count + re-check so the console can
    say '✓ Face detected — learned jan (N samples)'."""
    _wire(_RealEmbedder())
    r = _client().post("/recognition/enroll", json={"person_id": "jan"})
    assert r.status_code == 200
    body = r.json()
    assert body["enrolled"] == "jan"
    assert body["samples"] >= 1
    assert body["ok"] is True
