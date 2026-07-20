"""U36c + U34-slice: gesture heuristics and in-app secure enable."""

from __future__ import annotations

import pytest
from aura_brain import setup_api
from aura_brain.embodiment import gesture_for
from fastapi import FastAPI
from fastapi.testclient import TestClient
from shared_schemas.knowledge import InMemoryKnowledgeStore
from shared_schemas.knowledge.models import Person, PersonRole, ProfileFact

# ── gesture heuristics ──────────────────────────────────────────────


@pytest.mark.parametrize("text,expected", [
    ("Hello Jan! Good to see you.", "wave"),
    ("Goedemorgen Jan!", "wave"),
    ("Bye for now!", "wave"),
    ("That is awesome!! Congratulations!", "gesture"),
    ("Would you like me to check your calendar?", "tilt"),
    ("Sorry, I can't reach the mail server.", "tilt"),
    ("Your next meeting is at 14:00.", "nod"),
])
def test_gesture_for(text: str, expected: str) -> None:
    assert gesture_for(text) == expected


# ── /setup/secure ───────────────────────────────────────────────────


@pytest.fixture()
def setup_client(tmp_path, monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_DB_PATH", str(tmp_path / "knowledge.enc.json"))
    monkeypatch.setenv("AURA_ENV_FILE", str(tmp_path / ".env"))
    monkeypatch.delenv("KNOWLEDGE_SALT", raising=False)

    old_store = InMemoryKnowledgeStore()
    state = {"store": old_store, "encrypted": False, "recognition_omk": None}

    def swap(new_store) -> None:
        state["store"] = new_store
        state["encrypted"] = True

    def start_rec(omk: bytes) -> None:
        state["recognition_omk"] = omk

    setup_api.init(
        get_store=lambda: state["store"],
        swap_store=swap,
        start_recognition=start_rec,
        already_encrypted=lambda: state["encrypted"],
    )
    app = FastAPI()
    app.include_router(setup_api.router)
    yield TestClient(app), old_store, state, tmp_path
    setup_api.init(lambda: None, lambda s: None, lambda o: None, lambda: False)


async def test_secure_migrates_people_and_starts_recognition(setup_client) -> None:
    client, old_store, state, tmp_path = setup_client
    await old_store.upsert_person(Person(person_id="jan", display_name="Jan", role=PersonRole.OWNER))
    await old_store.add_fact(ProfileFact(person_id="jan", key="hobby", value="cycling"))

    resp = client.post("/setup/secure", json={"passphrase": "correct-horse-battery", "remember": True})
    assert resp.status_code == 200
    body = resp.json()
    assert body["encrypted"] is True
    assert body["migrated_people"] == 1
    assert body["recognition_started"] is True
    assert body["remembered"] is True

    # The swapped store is encrypted and holds the migrated data.
    person = await state["store"].get_person("jan")
    assert person is not None and person.display_name == "Jan"
    facts = await state["store"].get_facts("jan")
    assert [f.value for f in facts] == ["cycling"]
    # Ciphertext on disk, passphrase persisted to the env file, never in the response.
    assert (tmp_path / "knowledge.enc.json").exists()
    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "KNOWLEDGE_PASSPHRASE=correct-horse-battery" in env_text
    assert "correct-horse-battery" not in resp.text


def test_secure_rejects_short_passphrase(setup_client) -> None:
    client, *_ = setup_client
    assert client.post("/setup/secure", json={"passphrase": "kort"}).status_code == 422


def test_secure_conflicts_when_already_encrypted(setup_client) -> None:
    client, _, state, _ = setup_client
    state["encrypted"] = True
    resp = client.post("/setup/secure", json={"passphrase": "long-enough-pass"})
    assert resp.status_code == 409


def test_secure_without_remember_skips_env(setup_client) -> None:
    client, _, _, tmp_path = setup_client
    resp = client.post("/setup/secure", json={"passphrase": "long-enough-pass", "remember": False})
    assert resp.json()["remembered"] is False
    assert not (tmp_path / ".env").exists()
