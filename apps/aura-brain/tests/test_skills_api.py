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
