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


def test_already_optimal_verdict_consumes_the_signals(client, monkeypatch) -> None:
    """U159: an 'already optimal' review used to be a dead end — nothing to
    apply meant mark_optimized never ran, so the suggestion badge stuck
    forever and grew with every further use."""
    client.post("/skills", json={"name": "music", "description": "play music",
                                 "body": "1. Open Spotify.\n2. Play."})
    store = skills_api.get_store()
    for i in range(9):  # past SKILL_OPTIMIZE_THRESHOLD (8)
        store.record_observation("music", {"request": f"play thing {i}"})
    assert client.get("/skills/music/metrics").json()["new_since_optimized"] == 9
    assert [s["name"] for s in client.get("/skills/suggestions").json()["suggestions"]] == ["music"]

    async def _fake_chat(messages, model=None):
        import json as _j
        return {"content": _j.dumps({"changed": False, "rationale": "Already tight.",
                                     "body": "1. Open Spotify.\n2. Play."})}

    monkeypatch.setattr("orchestrator.llm.openai_chat", _fake_chat)
    prop = client.post("/skills/music/optimize", json={}).json()
    assert prop["changed"] is False           # nothing to apply…
    # …but the evidence WAS reviewed: counter reset, suggestion gone.
    assert client.get("/skills/music/metrics").json()["new_since_optimized"] == 0
    assert client.get("/skills/suggestions").json()["suggestions"] == []
    # The stored body is untouched — a verdict is not a rewrite.
    assert client.get("/skills/music").json()["body"].startswith("1. Open Spotify.")


def test_polish_endpoint(client, monkeypatch) -> None:
    """U118: /skills/polish rewrites a draft body without saving anything."""
    async def _fake_chat(messages, model=None):
        import json as _j
        return {"content": _j.dumps({"changed": True, "rationale": "Tighter.",
                                     "body": "1. Do it properly."})}

    monkeypatch.setattr("orchestrator.llm.openai_chat", _fake_chat)
    r = client.post("/skills/polish", json={"name": "x", "description": "d", "body": "do it"})
    assert r.status_code == 200
    assert r.json()["body"] == "1. Do it properly."
    # Nothing was saved — polish is advisory.
    assert client.get("/skills").json()["skills"] == []
    # Empty body → 422.
    assert client.post("/skills/polish", json={"body": "  "}).status_code == 422


def test_optimization_suggestions(client, monkeypatch) -> None:
    """U108: skills with enough new signals surface as proactive suggestions."""
    monkeypatch.setenv("SKILL_OPTIMIZE_THRESHOLD", "3")
    client.post("/skills", json={"name": "start-spotify", "body": "1. Open."})
    client.post("/skills", json={"name": "greet-guest", "body": "1. Wave."})
    store = skills_api.get_store()

    # Below threshold → not suggested.
    store.record_observation("start-spotify", {"request": "a"})
    assert client.get("/skills/suggestions").json()["suggestions"] == []

    # At/above threshold → suggested.
    for _ in range(3):
        store.record_observation("greet-guest", {"request": "hi"})
    sug = client.get("/skills/suggestions").json()
    assert sug["threshold"] == 3
    assert [s["name"] for s in sug["suggestions"]] == ["greet-guest"]

    # Applying an optimization clears the suggestion.
    store.mark_optimized("greet-guest")
    assert client.get("/skills/suggestions").json()["suggestions"] == []

    # "suggestions" must not be mistaken for a skill name.
    assert client.get("/skills/suggestions").status_code == 200
