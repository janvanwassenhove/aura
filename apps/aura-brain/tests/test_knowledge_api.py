"""U19d: knowledge transparency API — inspect, edit, and erase a profile through
the brain (ADR-008 §7 'see exactly what AURA knows, edit it, delete it')."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("LLM_PROVIDER", "echo")
os.environ.setdefault("STT_PROVIDER", "null")
os.environ.setdefault("TTS_PROVIDER", "null")

from fastapi.testclient import TestClient

from aura_brain.main import create_app


def test_inspect_edit_erase_profile() -> None:
    app = create_app()
    with TestClient(app) as client:
        # Create a person and teach AURA an explicit fact.
        assert client.put("/knowledge/people/jan", json={"display_name": "Jan", "role": "owner"}).status_code == 200
        fact = client.post("/knowledge/people/jan/facts", json={"key": "tone", "value": "concise"})
        assert fact.status_code == 200
        fact_id = fact.json()["fact_id"]

        # Inspect: the owner sees exactly what AURA knows.
        seen = client.get("/knowledge/people/jan")
        assert seen.status_code == 200
        body = seen.json()
        assert body["person"]["display_name"] == "Jan"
        assert any(f["key"] == "tone" and f["value"] == "concise" for f in body["facts"])

        # Edit: remove a fact.
        assert client.delete(f"/knowledge/facts/{fact_id}").status_code == 200
        assert client.get("/knowledge/people/jan").json()["facts"] == []

        # Listed among people.
        assert "jan" in [p["person_id"] for p in client.get("/knowledge/people").json()]

        # Erase: right-to-be-forgotten.
        assert client.delete("/knowledge/people/jan").status_code == 200
        assert client.get("/knowledge/people/jan").status_code == 404


def test_unknown_person_is_404() -> None:
    app = create_app()
    with TestClient(app) as client:
        assert client.get("/knowledge/people/nobody").status_code == 404
