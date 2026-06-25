"""U19a: KnowledgeStore contract — per-person scoping, erasure, signal
reinforcement, and the minors/consent guard (ADR-008 §10)."""

from __future__ import annotations

import pytest

from shared_schemas.knowledge import (
    ConsentError,
    ConsentRecord,
    EncryptedKnowledgeStore,
    InMemoryKnowledgeStore,
    ObservedSignal,
    Person,
    PersonRole,
    ProfileFact,
    RecognitionLink,
)


# The same contract must hold for the in-memory and the encrypted-at-rest store.
@pytest.fixture(params=["memory", "encrypted"])
def store(request):
    if request.param == "memory":
        return InMemoryKnowledgeStore()
    return EncryptedKnowledgeStore(omk=b"k" * 32)


async def test_facts_are_person_scoped(store) -> None:
    await store.upsert_person(Person(person_id="jan", display_name="Jan", role=PersonRole.OWNER))
    await store.upsert_person(Person(person_id="kid", display_name="Kid", role=PersonRole.FAMILY))
    await store.add_fact(ProfileFact(person_id="jan", key="tone", value="formal"))

    assert [f.value for f in await store.get_facts("jan")] == ["formal"]
    assert await store.get_facts("kid") == []  # never leaks across people


async def test_erasure_removes_everything(store) -> None:
    await store.upsert_person(Person(person_id="jan", display_name="Jan", role=PersonRole.OWNER))
    await store.add_fact(ProfileFact(person_id="jan", key="k", value="v"))
    await store.record_signal(ObservedSignal(person_id="jan", kind="late_riser", value="true"))
    await store.link_recognition(RecognitionLink(person_id="jan", embedding_ref="emb-1"))

    await store.delete_person("jan")

    assert await store.get_person("jan") is None
    assert await store.get_facts("jan") == []
    assert await store.get_signals("jan") == []
    assert await store.resolve_recognition("emb-1") is None  # right-to-be-forgotten


async def test_signal_reinforced_not_duplicated(store) -> None:
    await store.upsert_person(Person(person_id="jan", display_name="Jan", role=PersonRole.OWNER))
    await store.record_signal(ObservedSignal(person_id="jan", kind="prefers_morning", value="yes", confidence=0.5))
    await store.record_signal(ObservedSignal(person_id="jan", kind="prefers_morning", value="yes"))

    sigs = await store.get_signals("jan")
    assert len(sigs) == 1
    assert sigs[0].evidence_count == 2
    assert sigs[0].confidence > 0.5  # reinforced


async def test_minor_passive_learning_blocked_without_consent(store) -> None:
    await store.upsert_person(Person(person_id="kid", display_name="Kid", role=PersonRole.MINOR))

    with pytest.raises(ConsentError):
        await store.record_signal(ObservedSignal(person_id="kid", kind="likes_dinos", value="true"))

    # Explicit facts are always allowed (owner-taught), even for minors.
    await store.add_fact(ProfileFact(person_id="kid", key="bedtime", value="20:00"))
    assert len(await store.get_facts("kid")) == 1

    # With owner consent, passive learning is permitted.
    await store.set_consent(ConsentRecord(person_id="kid", granted_by="jan", scope="observed_learning"))
    sig = await store.record_signal(ObservedSignal(person_id="kid", kind="likes_dinos", value="true"))
    assert sig.kind == "likes_dinos"
