"""U160: the demo persona that ships with the app."""

from __future__ import annotations

import pytest
from aura_brain.demo_persona import DEMO_FACTS, DEMO_PERSON_ID, seed_demo_persona
from shared_schemas.knowledge import InMemoryKnowledgeStore
from shared_schemas.knowledge.models import ObservedSignal, Person, PersonRole
from shared_schemas.knowledge.store import ConsentError


@pytest.fixture()
def marker(tmp_path, monkeypatch):
    path = tmp_path / ".demo-persona-installed"
    monkeypatch.setenv("DEMO_PERSONA_MARKER", str(path))
    monkeypatch.delenv("DEMO_PERSONA", raising=False)
    return path


async def test_seeds_a_populated_demo_profile(marker) -> None:
    store = InMemoryKnowledgeStore()
    assert await seed_demo_persona(store) is True

    person = await store.get_person(DEMO_PERSON_ID)
    assert person is not None
    assert person.role == PersonRole.DEMO
    facts = await store.get_facts(DEMO_PERSON_ID)
    assert len(facts) == len(DEMO_FACTS)
    # The persona the owner asked for: sporty Java dev, 32, European roots.
    blob = " ".join(f.value for f in facts).lower()
    assert "[[java]]" in blob and "32 years old" in blob
    assert "[[ljubljana]]" in blob                       # European roots
    assert any(f.key == "sport" for f in facts)
    assert marker.exists()


async def test_seeding_is_idempotent(marker) -> None:
    store = InMemoryKnowledgeStore()
    assert await seed_demo_persona(store) is True
    assert await seed_demo_persona(store) is False       # marker → no re-run
    assert len(await store.get_facts(DEMO_PERSON_ID)) == len(DEMO_FACTS)


async def test_deleting_the_demo_keeps_it_gone(marker) -> None:
    """Installed once at setup — not resurrected on every boot."""
    store = InMemoryKnowledgeStore()
    await seed_demo_persona(store)
    await store.delete_person(DEMO_PERSON_ID)

    assert await seed_demo_persona(store) is False       # simulated restart
    assert await store.get_person(DEMO_PERSON_ID) is None


async def test_disabled_by_env(marker, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_PERSONA", "false")
    store = InMemoryKnowledgeStore()
    assert await seed_demo_persona(store) is False
    assert await store.get_person(DEMO_PERSON_ID) is None
    assert not marker.exists()                           # no marker → opt-in later


async def test_never_clobbers_an_existing_person(marker) -> None:
    store = InMemoryKnowledgeStore()
    await store.upsert_person(Person(
        person_id=DEMO_PERSON_ID, display_name="Mila (real)", role=PersonRole.FAMILY))

    assert await seed_demo_persona(store) is False
    person = await store.get_person(DEMO_PERSON_ID)
    assert person.display_name == "Mila (real)" and person.role == PersonRole.FAMILY


async def test_in_memory_store_writes_no_marker(tmp_path, monkeypatch) -> None:
    """Regression: with a non-persistent store the marker must NOT be written.

    It would outlive the data it describes — a test run (or any dev boot on the
    in-memory store) dropped a marker in ./data, which then silently stopped
    the REAL persistent install from ever seeding the demo profile.
    """
    monkeypatch.delenv("DEMO_PERSONA_MARKER", raising=False)
    monkeypatch.setenv("KNOWLEDGE_DB_PATH", str(tmp_path / "knowledge.enc.json"))
    store = InMemoryKnowledgeStore()

    assert await seed_demo_persona(store, persistent=False) is True
    assert not (tmp_path / ".demo-persona-installed").exists()
    # …and a fresh in-memory boot seeds her again (nothing survived anyway).
    assert await seed_demo_persona(InMemoryKnowledgeStore(), persistent=False) is True


async def test_demo_profile_refuses_passive_learning(marker) -> None:
    """Real conversations must not drift into the curated sample data."""
    store = InMemoryKnowledgeStore()
    await seed_demo_persona(store)

    with pytest.raises(ConsentError):
        await store.record_signal(ObservedSignal(
            person_id=DEMO_PERSON_ID, kind="prefers_short_answers", value="yes"))
