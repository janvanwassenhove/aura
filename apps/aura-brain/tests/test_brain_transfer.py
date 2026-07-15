"""U104: brain import/export — mine ChatGPT/Claude data-exports for facts,
and dump everything AURA knows as one JSON document."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("LLM_PROVIDER", "echo")
os.environ.setdefault("STT_PROVIDER", "null")
os.environ.setdefault("TTS_PROVIDER", "null")

import pytest
from fastapi.testclient import TestClient

from aura_brain import brain_transfer
from aura_brain.main import create_app

_CHATGPT_EXPORT = [{
    "title": "Robot ideas",
    "mapping": {
        "n1": {"message": {"author": {"role": "user"},
                           "content": {"parts": ["I am building a Reachy Mini robot assistant."]}}},
        "n2": {"message": {"author": {"role": "assistant"},
                           "content": {"parts": ["Great idea! Here is how..."]}}},
        "n3": {"message": None},
    },
}]

_CLAUDE_EXPORT = [{
    "name": "3D printing help",
    "chat_messages": [
        {"sender": "human", "text": "My Prusa keeps stringing on PETG."},
        {"sender": "assistant", "text": "Try lowering the temperature."},
    ],
}]


# ------------------------------------------------------------------
# Pure parsing — no LLM, no store
# ------------------------------------------------------------------

def test_parse_chatgpt_export_keeps_only_user_words() -> None:
    convs = brain_transfer.parse_chat_export(_CHATGPT_EXPORT)
    assert convs == [{"title": "Robot ideas", "text": "I am building a Reachy Mini robot assistant."}]


def test_parse_claude_export_keeps_only_human_words() -> None:
    convs = brain_transfer.parse_chat_export(_CLAUDE_EXPORT)
    assert convs == [{"title": "3D printing help", "text": "My Prusa keeps stringing on PETG."}]


def test_parse_garbage_yields_empty() -> None:
    assert brain_transfer.parse_chat_export("not json {") == []
    assert brain_transfer.parse_chat_export({"weird": "shape"}) == []
    assert brain_transfer.parse_chat_export([{"weird": "shape"}]) == []


def test_chunking_packs_and_splits() -> None:
    convs = [{"title": "a", "text": "x" * 30}, {"title": "b", "text": "y" * 30}]
    chunks = brain_transfer.chunk_conversations(convs, chunk_chars=50)
    assert len(chunks) == 2  # each conversation is ~37 chars — no mid-split
    big = brain_transfer.chunk_conversations([{"title": "big", "text": "z" * 200}], chunk_chars=50)
    assert all(len(c) <= 50 for c in big)  # oversized conversation still chunks


# ------------------------------------------------------------------
# Import + export through the API (fake LLM at the seam)
# ------------------------------------------------------------------

@pytest.fixture()
def fake_distill(monkeypatch):
    async def _fake(name, text):
        return [{"key": "project", "value": "Builds a [[Reachy Mini]] assistant"}]

    monkeypatch.setattr(brain_transfer, "_distill_facts", _fake)


def test_import_chats_grows_facts_and_dedupes(fake_distill) -> None:
    app = create_app()
    with TestClient(app) as client:
        client.put("/knowledge/people/jan", json={"display_name": "Jan", "role": "owner"})

        r = client.post("/knowledge/people/jan/import-chats", json={"export": _CHATGPT_EXPORT})
        assert r.status_code == 200
        body = r.json()
        assert body["conversations"] == 1
        assert body["added_count"] == 1

        facts = client.get("/knowledge/people/jan").json()["facts"]
        assert any("[[Reachy Mini]]" in f["value"] for f in facts)

        # Re-import: same distilled fact → nothing added twice.
        again = client.post("/knowledge/people/jan/import-chats", json={"export": _CLAUDE_EXPORT}).json()
        assert again["added_count"] == 0


def test_import_unrecognised_export_is_422(fake_distill) -> None:
    app = create_app()
    with TestClient(app) as client:
        client.put("/knowledge/people/jan", json={"display_name": "Jan", "role": "owner"})
        r = client.post("/knowledge/people/jan/import-chats", json={"export": {"nope": 1}})
        assert r.status_code == 422
        assert client.post("/knowledge/people/jan/import-chats", json={}).status_code == 422


def test_import_unknown_person_is_404(fake_distill) -> None:
    app = create_app()
    with TestClient(app) as client:
        r = client.post("/knowledge/people/nobody/import-chats", json={"export": _CHATGPT_EXPORT})
        assert r.status_code == 404


def test_export_brain_dumps_people_and_facts() -> None:
    app = create_app()
    with TestClient(app) as client:
        client.put("/knowledge/people/jan", json={"display_name": "Jan", "role": "owner"})
        client.post("/knowledge/people/jan/facts", json={"key": "tone", "value": "concise"})

        r = client.get("/knowledge/export")
        assert r.status_code == 200
        body = r.json()
        assert body["exported_at"]
        jan = next(p for p in body["people"] if p["person"]["person_id"] == "jan")
        assert any(f["key"] == "tone" for f in jan["facts"])
