"""U280: linking what he learns to the people it is about.

Asked as "kan hij vandaag al linken leggen tss persona? bv. als ik praat als
jan, over jappe, dan kan hij ook kennis opbouwen over jappe op dat ogenblik".

He already remembered Jappe — "relationships" is in the distiller's keep-list,
so "Jan's son Jappe is 13" lands in Jan's memory. What he never did was
CONNECT them. The graph has turned [[name]] into a shared node all along, and a
name it recognises as a person into a clickable person node — the distiller had
simply never been told that syntax exists, so two people the owner had both
created sat in one household with nothing between them.

Only names he ALREADY knows are linked. Inventing a profile for every name
overheard is a different decision with different weight — especially for a
child, whom this app never learns about passively (ADR-008 §10).
"""

from __future__ import annotations

import pytest
from aura_brain.person_memory import PersonMemory
from shared_schemas.knowledge import InMemoryKnowledgeStore, Person


class _Chat:
    """Records the prompt it was handed; answers with a fixed note."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def __call__(self, messages, model=None):
        self.prompts.append(messages[0]["content"])
        return {"content": "- Jan's son [[jappe]] is 13"}


@pytest.fixture()
async def rig():
    store = InMemoryKnowledgeStore()
    await store.upsert_person(Person(person_id="jan", display_name="Jan", role="owner"))
    await store.upsert_person(Person(person_id="jappe", display_name="Jappe", role="minor"))
    chat = _Chat()
    return store, chat, PersonMemory(store, chat, every=1)


async def test_the_distiller_is_told_who_it_may_link_to(rig) -> None:
    store, chat, pm = rig
    await pm.record("jan", "Jappe wordt 13 in november", "Leuk!")

    prompt = chat.prompts[0]
    assert "[[Name]]" in prompt, "it has to know the syntax exists"
    assert "jappe" in prompt, "and who already has a profile to link to"


async def test_the_speaker_is_not_offered_a_link_to_themselves(rig) -> None:
    store, chat, pm = rig
    await pm.record("jan", "iets", "iets")

    line = [ln for ln in chat.prompts[0].splitlines() if "already have a profile" in ln]
    assert line, "the known-people line should be there"
    assert "jan" not in line[0].split(":", 1)[1], "linking a page to itself says nothing"


async def test_the_demo_profile_is_never_woven_into_a_real_household(rig) -> None:
    store, chat, pm = rig
    await store.upsert_person(Person(person_id="mila", display_name="Mila", role="demo"))
    await pm.record("jan", "iets", "iets")

    assert "mila" not in chat.prompts[0], "fiction must not link to real people"


async def test_a_household_of_one_gets_no_linking_instruction(rig) -> None:
    """Nobody else to link to — the prompt must not carry an empty list."""
    store = InMemoryKnowledgeStore()
    await store.upsert_person(Person(person_id="jan", display_name="Jan", role="owner"))
    chat = _Chat()
    pm = PersonMemory(store, chat, every=1)

    await pm.record("jan", "iets", "iets")

    assert "already have a profile" not in chat.prompts[0]


async def test_the_link_survives_into_the_stored_memory(rig) -> None:
    """What the graph reads is the stored note, so the syntax has to reach it."""
    store, chat, pm = rig
    await pm.record("jan", "Jappe wordt 13", "Leuk!")

    assert "[[jappe]]" in await pm.get_memory("jan")
