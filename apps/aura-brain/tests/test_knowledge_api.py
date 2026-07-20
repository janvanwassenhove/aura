"""U19d: knowledge transparency API — inspect, edit, and erase a profile through
the brain (ADR-008 §7 'see exactly what AURA knows, edit it, delete it')."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("LLM_PROVIDER", "echo")
os.environ.setdefault("STT_PROVIDER", "null")
os.environ.setdefault("TTS_PROVIDER", "null")

from aura_brain.main import create_app
from fastapi.testclient import TestClient


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


def test_person_description_and_skill_references() -> None:
    """U63: describe a person + see their skills from their profile."""
    import tempfile

    from aura_brain import skills_api
    from orchestrator.skills import Skill, SkillStore

    app = create_app()
    with TestClient(app) as client, tempfile.TemporaryDirectory() as tmp:
        skills_api.init(SkillStore(tmp))
        assert client.put("/knowledge/people/elke", json={
            "display_name": "Elke", "role": "family",
            "description": "my partner; prefers short answers",
        }).status_code == 200

        # Description-only update MERGES: name/role untouched.
        assert client.put("/knowledge/people/elke", json={
            "description": "my partner; loves ska; prefers short answers",
        }).status_code == 200
        body = client.get("/knowledge/people/elke").json()
        assert body["person"]["display_name"] == "Elke"
        assert body["person"]["role"] == "family"
        assert "loves ska" in body["person"]["description"]

        # A skill scoped to this person shows up in their profile.
        skills_api.get_store().save(Skill(
            name="playlist-for-elke", description="how Elke likes music picked",
            person="elke", body="Skate punk first.",
        ))
        body = client.get("/knowledge/people/elke").json()
        assert [s["name"] for s in body["skills"]] == ["playlist-for-elke"]

        # Another person's profile does not list it.
        assert client.put("/knowledge/people/jan2", json={"display_name": "Jan"}).status_code == 200
        assert client.get("/knowledge/people/jan2").json()["skills"] == []


def test_description_lands_in_judgment_context() -> None:
    """The portrait personalizes conversations via the judgment layer."""
    from shared_schemas.knowledge import Person, PersonContext

    person = Person(person_id="elke", display_name="Elke", role="family",
                    description="my partner; prefers short answers")
    note = PersonContext(person=person).to_system_note()
    assert "About them: my partner; prefers short answers" in note


def test_wikilink_mentions_appear_as_backlinks() -> None:
    """U68: a skill that mentions [[person]] shows in their profile as backlink."""
    import tempfile

    from aura_brain import skills_api
    from orchestrator.skills import Skill, SkillStore

    app = create_app()
    with TestClient(app) as client, tempfile.TemporaryDirectory() as tmp:
        skills_api.init(SkillStore(tmp))
        assert client.put("/knowledge/people/jan3", json={"display_name": "Jan"}).status_code == 200
        skills_api.get_store().save(Skill(
            name="weekly-report", description="how the weekly report goes",
            body="Collect input, then ask [[jan3]] to review before sending.",
        ))
        body = client.get("/knowledge/people/jan3").json()
        assert body["skills"] == [{"name": "weekly-report",
                                   "description": "how the weekly report goes",
                                   "enabled": True, "via": "mention"}]


def test_lock_then_unlock_with_passphrase(monkeypatch) -> None:
    """U94: /knowledge/unlock re-elevates to SENSITIVE with the right passphrase."""
    import os
    import tempfile
    monkeypatch.setenv("KNOWLEDGE_PASSPHRASE", "super-secret-pass")
    monkeypatch.setenv("KNOWLEDGE_SALT", "testsalt")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    tmp = tempfile.mkdtemp()
    monkeypatch.setenv("KNOWLEDGE_DB_PATH", os.path.join(tmp, "k.enc.json"))
    app = create_app()
    with TestClient(app) as client:
        assert client.put("/knowledge/people/x", json={"display_name": "X", "role": "guest"}).status_code == 200
        # lock → benign → people 403
        assert client.post("/knowledge/lock").json()["locked"] is True
        assert client.get("/knowledge/people").status_code == 403
        # wrong passphrase stays locked
        assert client.post("/knowledge/unlock", json={"passphrase": "nope"}).status_code == 403
        assert client.get("/knowledge/people").status_code == 403
        # right passphrase unlocks
        assert client.post("/knowledge/unlock", json={"passphrase": "super-secret-pass"}).json()["unlocked"] is True
        assert client.get("/knowledge/people").status_code == 200
