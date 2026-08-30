"""U276: telling the brain who it is talking to.

Reported as "terwijl ik (jan) vertel tegen robot geef ik informatie, maar ik
zie dat hij niet gebruikt in zijn kennisopbouw".

The header has always let the owner say who is at the desk, and that choice
never left the browser: `setSpeaker` set a ref in a Pinia store and nothing
else. The brain's active person came from face recognition alone, so on a
profile with no face taught — which is every fresh one, and the state the
owner was in — the console showed "Jan · owner" while the brain knew nobody.
Long-term memory needs a person to attribute to (`if hook and
self._active_person_id`), so every word of those conversations was answered
properly and then dropped, silently, under a Memory tab promising the
opposite.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from shared_schemas.knowledge import InMemoryKnowledgeStore, Person


class _Pipeline:
    def __init__(self) -> None:
        self._active_person_id = None

    def set_active_person(self, person_id):
        self._active_person_id = person_id


@pytest.fixture()
def client(monkeypatch):
    from aura_brain import knowledge_api

    store = InMemoryKnowledgeStore()
    knowledge_api.set_store(store)
    knowledge_api.set_omk_loaded(False)
    pipeline = _Pipeline()
    monkeypatch.setattr(knowledge_api, "_pipeline", lambda: pipeline)

    app = FastAPI()
    app.include_router(knowledge_api.router)
    return TestClient(app), store, pipeline


async def test_choosing_a_speaker_reaches_the_brain(client) -> None:
    c, store, pipeline = client
    await store.upsert_person(Person(person_id="jan", display_name="Jan", role="owner"))

    body = c.post("/knowledge/speaker", json={"person_id": "jan"}).json()

    assert pipeline._active_person_id == "jan", "the console's choice must reach the brain"
    assert body["display_name"] == "Jan"
    assert body["remembering"] is True


def test_nobody_selected_means_nothing_is_remembered(client) -> None:
    c, _, pipeline = client
    body = c.get("/knowledge/speaker").json()
    assert body["person_id"] is None
    # The whole point: the console can now SAY this instead of implying the
    # opposite in the Memory tab.
    assert body["remembering"] is False


def test_a_guest_is_nobody_to_remember_against(client) -> None:
    c, _, pipeline = client
    body = c.post("/knowledge/speaker", json={"person_id": "guest"}).json()
    assert pipeline._active_person_id is None
    assert body["remembering"] is False


def test_an_unknown_person_is_refused_rather_than_silently_ignored(client) -> None:
    c, _, pipeline = client
    assert c.post("/knowledge/speaker", json={"person_id": "nobody"}).status_code == 404
    assert pipeline._active_person_id is None


async def test_clearing_the_speaker_stops_the_attribution(client) -> None:
    c, store, pipeline = client
    await store.upsert_person(Person(person_id="jan", display_name="Jan", role="owner"))
    c.post("/knowledge/speaker", json={"person_id": "jan"})

    body = c.post("/knowledge/speaker", json={"person_id": None}).json()

    assert pipeline._active_person_id is None
    assert body["remembering"] is False
