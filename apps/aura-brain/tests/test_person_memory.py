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
        return {"content": "- Building a [[Reachy Mini]] robot"}

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
