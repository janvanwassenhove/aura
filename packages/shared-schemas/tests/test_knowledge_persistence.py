"""U29: encrypted knowledge store persists ciphertext to disk across restarts."""

from __future__ import annotations

import json

import pytest

from shared_schemas.knowledge import EncryptedKnowledgeStore, crypto
from shared_schemas.knowledge.models import Person, PersonRole, ProfileFact

OMK = crypto.derive_omk("test-passphrase", b"0123456789abcdef")


def _person(pid: str = "jan", name: str = "Jan") -> Person:
    return Person(person_id=pid, display_name=name, role=PersonRole.OWNER)


async def test_round_trips_across_store_instances(tmp_path) -> None:
    path = tmp_path / "knowledge.enc.json"
    store1 = EncryptedKnowledgeStore(OMK, path=path)
    await store1.upsert_person(_person())
    await store1.add_fact(ProfileFact(person_id="jan", key="likes", value="coffee", source="explicit"))

    # A brand-new instance (fresh process) sees the same data.
    store2 = EncryptedKnowledgeStore(OMK, path=path)
    person = await store2.get_person("jan")
    assert person is not None and person.display_name == "Jan"
    facts = await store2.get_facts("jan")
    assert [f.value for f in facts] == ["coffee"]


async def test_plaintext_never_touches_disk(tmp_path) -> None:
    path = tmp_path / "knowledge.enc.json"
    store = EncryptedKnowledgeStore(OMK, path=path)
    await store.upsert_person(_person(name="SecretName"))
    await store.add_fact(ProfileFact(person_id="jan", key="likes", value="SECRETVALUE", source="explicit"))

    raw = path.read_text(encoding="utf-8")
    assert "SecretName" not in raw
    assert "SECRETVALUE" not in raw
    # Structure is versioned ciphertext entries only.
    data = json.loads(raw)
    assert data["version"] == 1
    assert set(data["people"]["jan"].keys()) == {"wrapped_dek", "blob"}


async def test_delete_person_erases_from_disk(tmp_path) -> None:
    path = tmp_path / "knowledge.enc.json"
    store = EncryptedKnowledgeStore(OMK, path=path)
    await store.upsert_person(_person())
    await store.delete_person("jan")

    data = json.loads(path.read_text(encoding="utf-8"))
    assert "jan" not in data["people"]
    # And a fresh instance cannot resurrect them.
    store2 = EncryptedKnowledgeStore(OMK, path=path)
    assert await store2.get_person("jan") is None


async def test_wrong_passphrase_cannot_decrypt(tmp_path) -> None:
    path = tmp_path / "knowledge.enc.json"
    store = EncryptedKnowledgeStore(OMK, path=path)
    await store.upsert_person(_person())

    wrong = crypto.derive_omk("wrong-passphrase", b"0123456789abcdef")
    store2 = EncryptedKnowledgeStore(wrong, path=path)
    with pytest.raises(Exception):
        await store2.get_person("jan")


async def test_no_path_stays_in_memory(tmp_path) -> None:
    store = EncryptedKnowledgeStore(OMK)  # no path — ephemeral, unchanged behavior
    await store.upsert_person(_person())
    assert list(tmp_path.iterdir()) == []


async def test_missing_file_starts_empty(tmp_path) -> None:
    store = EncryptedKnowledgeStore(OMK, path=tmp_path / "does-not-exist-yet.json")
    assert await store.list_people() == []
