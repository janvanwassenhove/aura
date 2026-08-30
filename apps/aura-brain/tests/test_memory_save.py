"""U278: correcting the memory note has to REPLACE it.

Reported as "bij memory, wanneer ik aanpassing (correctie) maak lijkt hij niet
te saven". It saved — as a SECOND fact. The console's Save button called
`addFact(person, "memory", text)`, which appends, while both readers (the
view and the brain's PersonMemory) took the FIRST match. So the correction was
stored, never displayed, and never reached the model.

The owner's own graph showed the damage plainly: eight nodes, all reading
"memory: - Jan is actief e…" — one per press of Save.

Correcting something wrong about yourself is exactly the moment it must take.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from shared_schemas.knowledge import InMemoryKnowledgeStore, Person, ProfileFact


@pytest.fixture()
def client():
    from aura_brain import knowledge_api

    store = InMemoryKnowledgeStore()
    knowledge_api.set_store(store)
    knowledge_api.set_omk_loaded(False)
    app = FastAPI()
    app.include_router(knowledge_api.router)
    return TestClient(app), store


async def _memory_facts(store, pid):
    return [f for f in await store.get_facts(pid) if f.key == "memory"]


async def test_saving_a_correction_replaces_the_note(client) -> None:
    c, store = client
    await store.upsert_person(Person(person_id="jan", display_name="Jan", role="owner"))
    c.put("/knowledge/people/jan/memory", json={"memory": "- Jan plays hockey"})
    c.put("/knowledge/people/jan/memory", json={"memory": "- Jan plays football"})

    notes = await _memory_facts(store, "jan")
    assert len(notes) == 1, "a correction must replace, not pile up"
    assert notes[0].value == "- Jan plays football"


async def test_a_store_already_full_of_duplicates_heals_on_the_next_save(client) -> None:
    """The owner's store had eight. The fix must collapse them, not add a ninth."""
    c, store = client
    await store.upsert_person(Person(person_id="jan", display_name="Jan", role="owner"))
    for i in range(8):
        await store.add_fact(ProfileFact(person_id="jan", key="memory", value=f"old {i}"))

    c.put("/knowledge/people/jan/memory", json={"memory": "the corrected note"})

    notes = await _memory_facts(store, "jan")
    assert len(notes) == 1
    assert notes[0].value == "the corrected note"


async def test_clearing_the_note_leaves_nothing_behind(client) -> None:
    c, store = client
    await store.upsert_person(Person(person_id="jan", display_name="Jan", role="owner"))
    c.put("/knowledge/people/jan/memory", json={"memory": "something"})

    body = c.put("/knowledge/people/jan/memory", json={"memory": "   "}).json()

    assert await _memory_facts(store, "jan") == []
    assert body["memory"] == ""


def test_an_unknown_person_is_refused(client) -> None:
    c, _ = client
    assert c.put("/knowledge/people/nobody/memory", json={"memory": "x"}).status_code == 404


async def test_other_facts_are_never_touched(client) -> None:
    c, store = client
    await store.upsert_person(Person(person_id="jan", display_name="Jan", role="owner"))
    await store.add_fact(ProfileFact(person_id="jan", key="hobby", value="hockey"))

    c.put("/knowledge/people/jan/memory", json={"memory": "a note"})

    keys = sorted(f.key for f in await store.get_facts("jan"))
    assert keys == ["hobby", "memory"]
