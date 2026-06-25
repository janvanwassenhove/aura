"""U19b: EncryptedKnowledgeStore — at-rest is ciphertext; erasure is cryptographic."""

from __future__ import annotations

from shared_schemas.knowledge import (
    EncryptedKnowledgeStore,
    Person,
    PersonRole,
    ProfileFact,
)


async def test_data_at_rest_is_ciphertext() -> None:
    store = EncryptedKnowledgeStore(omk=b"k" * 32)
    await store.upsert_person(Person(person_id="jan", display_name="Jan", role=PersonRole.OWNER))
    await store.add_fact(ProfileFact(person_id="jan", key="secret", value="mail-pattern-XYZ"))

    # The stored blob must NOT contain the plaintext anywhere.
    blob = store._blobs["jan"]
    assert b"mail-pattern-XYZ" not in blob
    assert b"secret" not in blob
    # But it round-trips for the legitimate owner (correct OMK).
    assert (await store.get_facts("jan"))[0].value == "mail-pattern-XYZ"


async def test_wrong_omk_cannot_read() -> None:
    store = EncryptedKnowledgeStore(omk=b"k" * 32)
    await store.upsert_person(Person(person_id="jan", display_name="Jan"))

    # An attacker with the ciphertext but a different OMK gets nothing.
    attacker = EncryptedKnowledgeStore(omk=b"x" * 32)
    attacker._wrapped_deks = dict(store._wrapped_deks)
    attacker._blobs = dict(store._blobs)
    import pytest
    from cryptography.exceptions import InvalidTag

    with pytest.raises(InvalidTag):
        await attacker.get_person("jan")


async def test_erasure_destroys_key_and_blob() -> None:
    store = EncryptedKnowledgeStore(omk=b"k" * 32)
    await store.upsert_person(Person(person_id="jan", display_name="Jan"))
    await store.delete_person("jan")
    assert "jan" not in store._blobs
    assert "jan" not in store._wrapped_deks  # DEK gone → data unrecoverable
    assert await store.get_person("jan") is None
