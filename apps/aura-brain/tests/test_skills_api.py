"""U59: skills CRUD API."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aura_brain import skills_api
from orchestrator.skills import SkillStore


@pytest.fixture()
def client(tmp_path):
    skills_api.init(SkillStore(str(tmp_path)))
    app = FastAPI()
    app.include_router(skills_api.router)
    return TestClient(app)


def test_crud_roundtrip(client) -> None:
    assert client.get("/skills").json() == {"skills": []}

    resp = client.post("/skills", json={
        "name": "presenting-with-jan",
        "description": "how Jan presents",
        "triggers": ["presentation"],
        "personas": ["work"],
        "person": "jan",
        "body": "Wait for the nod.",
    })
    assert resp.status_code == 200
    assert resp.json()["name"] == "presenting-with-jan"

    one = client.get("/skills/presenting-with-jan").json()
    assert one["body"] == "Wait for the nod."
    assert one["person"] == "jan"

    assert client.delete("/skills/presenting-with-jan").json() == {"deleted": "presenting-with-jan"}
    assert client.get("/skills/presenting-with-jan").status_code == 404


def test_invalid_name_rejected(client) -> None:
    resp = client.post("/skills", json={"name": "Bad Name!", "body": "x"})
    assert resp.status_code == 422


def test_metrics_and_optimize(client, monkeypatch) -> None:
    """U107: usage metrics + owner-approved optimization proposal."""
    client.post("/skills", json={"name": "start-spotify", "description": "open spotify", "body": "1. Open.\n2. Play."})

    # No uses yet.
    assert client.get("/skills/start-spotify/metrics").json()["uses"] == 0
    assert client.get("/skills/nope/metrics").status_code == 404

    # Record a couple of uses directly on the store.
    store = skills_api.get_store()
    store.record_observation("start-spotify", {"request": "play the champions"})
    store.record_observation("start-spotify", {"request": "put on some jazz"})
    m = client.get("/skills/start-spotify/metrics").json()
    assert m["uses"] == 2 and m["new_since_optimized"] == 2

    # Optimize — patch the LLM so no network is needed.
    async def _fake_chat(messages, model=None):
        import json as _j
        return {"content": _j.dumps({"changed": True, "rationale": "Tighter.",
                                     "body": "1. Launch Spotify.\n2. Start the playlist; confirm playing."})}

    monkeypatch.setattr("orchestrator.llm.openai_chat", _fake_chat)
    prop = client.post("/skills/start-spotify/optimize", json={}).json()
    assert prop["changed"] is True and "Launch Spotify" in prop["proposed_body"]
    # Proposal alone must NOT change the stored skill.
    assert client.get("/skills/start-spotify").json()["body"].startswith("1. Open.")

    # Apply the rewrite (owner approval) + reset the counter.
    client.post("/skills", json={"name": "start-spotify", "description": "open spotify",
                                 "body": prop["proposed_body"], "mark_optimized": True})
    assert client.get("/skills/start-spotify").json()["body"].startswith("1. Launch Spotify.")
    assert client.get("/skills/start-spotify/metrics").json()["new_since_optimized"] == 0

    assert client.post("/skills/nope/optimize", json={}).status_code == 404
