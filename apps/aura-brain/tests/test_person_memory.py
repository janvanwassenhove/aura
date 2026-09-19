"""U109: long-term memory per person — buffer exchanges, distil into a durable
`memory` fact, injected into future turns via the judgment layer."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("LLM_PROVIDER", "echo")

import pytest
from aura_brain.person_memory import MEMORY_KEY, PersonMemory
from shared_schemas.knowledge import InMemoryKnowledgeStore, Person, PersonRole


@pytest.fixture()
async def store():
    s = InMemoryKnowledgeStore()
    await s.upsert_person(Person(person_id="jan", display_name="Jan", role=PersonRole.OWNER))
    return s


def _chat_returning(text: str):
    async def _fn(messages, model=None):
        return {"content": text}
    return _fn


async def test_buffers_then_distills_every_n(store) -> None:
    calls = []

    async def _chat(messages, model=None):
        calls.append(messages)
        # U281: no [[link]] here on purpose. This test is about the BUFFER
        # (distil after N exchanges); links are resolved by _resolve_links and
        # covered in test_person_autocreate.py, where a product name wrapped
        # in brackets would — correctly — become a profile.
        return {"content": "- Building a Reachy Mini robot"}

    pm = PersonMemory(store, _chat, every=3)
    await pm.record("jan", "I'm building a robot", "Nice!")
    await pm.record("jan", "It's a Reachy Mini", "Cool!")
    assert calls == []  # not yet — buffer below threshold
    assert await pm.get_memory("jan") == ""

    await pm.record("jan", "Antennas move", "Great!")  # 3rd → distil
    assert len(calls) == 1
    assert "Reachy Mini" in await pm.get_memory("jan")


async def test_memory_is_a_single_replaced_fact(store) -> None:
    pm = PersonMemory(store, _chat_returning("- first memory"), every=1)
    await pm.record("jan", "hi", "hello")
    await pm.record("jan", "again", "yes")
    # After two distils there is still exactly ONE memory fact (replaced, not appended).
    mem_facts = [f for f in await store.get_facts("jan") if f.key == MEMORY_KEY]
    assert len(mem_facts) == 1


async def test_flush_distills_partial_buffer(store) -> None:
    pm = PersonMemory(store, _chat_returning("- remembered"), every=10)
    await pm.record("jan", "note this", "ok")
    assert await pm.get_memory("jan") == ""  # buffered, not yet distilled
    result = await pm.flush("jan")
    assert result["folded"] == 1
    assert await pm.get_memory("jan") == "- remembered"


async def test_skips_empty_and_echo(store) -> None:
    pm = PersonMemory(store, _chat_returning("x"), every=1)
    await pm.record("jan", "", "reply")           # empty user → ignored
    await pm.record("jan", "hi", "[echo] hi")     # echo reply → ignored
    assert await pm.get_memory("jan") == ""


async def test_unknown_person_no_crash(store) -> None:
    pm = PersonMemory(store, _chat_returning("x"), every=1)
    await pm.record("ghost", "hi", "hello")  # no such person → best-effort no-op
    assert await pm.get_memory("ghost") == ""


# -- U364: no passive learning about a minor ---------------------------------


async def test_minor_is_not_remembered_without_consent(store) -> None:
    """ADR-008 section 10: a child's conversations are not distilled into a
    memory unless the owner opted in. Nothing is sent to the model either."""
    calls = []

    async def _chat(messages, model=None):
        calls.append(messages)
        return {"content": "- Is in Scandinavia"}

    await store.upsert_person(Person(person_id="kid", display_name="Sam", role=PersonRole.MINOR))
    pm = PersonMemory(store, _chat, every=1)
    await pm.record("kid", "I like loud music", "Noted!")
    assert calls == []
    assert await pm.get_memory("kid") == ""
    assert await pm.flush("kid") is None


async def test_minor_is_remembered_with_owner_consent(store) -> None:
    from shared_schemas.knowledge import ConsentRecord

    await store.upsert_person(Person(person_id="kid", display_name="Sam", role=PersonRole.MINOR))
    await store.set_consent(
        ConsentRecord(person_id="kid", granted_by="owner", scope="observed_learning"))
    pm = PersonMemory(store, _chat_returning("- Likes chess"), every=1)
    await pm.record("kid", "I like chess", "Great!")
    assert await pm.get_memory("kid") == "- Likes chess"


async def test_role_changed_to_minor_before_flush_is_not_distilled(store) -> None:
    """The gate holds at distillation too, not only when a turn is buffered."""
    await store.upsert_person(Person(person_id="sam", display_name="Sam", role=PersonRole.FAMILY))
    pm = PersonMemory(store, _chat_returning("- remembered"), every=10)
    await pm.record("sam", "note this", "ok")
    await store.upsert_person(Person(person_id="sam", display_name="Sam", role=PersonRole.MINOR))
    assert await pm.flush("sam") is None
    assert await pm.get_memory("sam") == ""


async def test_owner_can_still_write_a_minors_memory_explicitly(store) -> None:
    """Only passive learning is gated; the owner editing it by hand is explicit."""
    await store.upsert_person(Person(person_id="kid", display_name="Sam", role=PersonRole.MINOR))
    pm = PersonMemory(store, _chat_returning("x"), every=1)
    await pm.set_memory("kid", "- Plays hockey")
    assert await pm.get_memory("kid") == "- Plays hockey"
