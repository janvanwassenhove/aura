"""U281: he may add a person he hears about — without duplicating one.

The owner authorised it: "hij mag automatisch profiel maken (brain blijft
lokaal binnen familie)", with one condition — "indien persoon al bestaat (in
dit geval is er al jappe persona), moet hij link kunnen leggen gezien context
of voorstellen".

That condition is the whole difficulty. The model writes [[Jappe]]; the
profile is `jappe`; a naive create puts a second Jappe beside the first and
quietly splits everything known about one child across two pages.
"""

from __future__ import annotations

import pytest
from aura_brain.person_memory import PersonMemory
from shared_schemas.knowledge import InMemoryKnowledgeStore, Person


class _Chat:
    def __init__(self, reply: str) -> None:
        self.reply = reply

    async def __call__(self, messages, model=None):
        return {"content": self.reply}


async def _rig(reply: str, people: list[Person] | None = None):
    store = InMemoryKnowledgeStore()
    await store.upsert_person(Person(person_id="jan", display_name="Jan", role="owner"))
    for p in people or []:
        await store.upsert_person(p)
    return store, PersonMemory(store, _Chat(reply), every=1)


async def test_an_existing_person_is_linked_never_duplicated() -> None:
    """The owner's exact case: Jappe already has a profile."""
    store, pm = await _rig(
        "- Zijn zoon [[Jappe]] wordt 13 in november",
        [Person(person_id="jappe", display_name="Jappe", role="minor")])

    await pm.record("jan", "Jappe wordt 13", "Leuk!")

    ids = sorted(p.person_id for p in await store.list_people())
    assert ids == ["jan", "jappe"], "no second Jappe"
    # And the link points at the canonical id, so the graph can resolve it.
    assert "[[jappe]]" in await pm.get_memory("jan")


async def test_a_full_name_resolves_to_the_existing_profile() -> None:
    store, pm = await _rig(
        "- Werkt samen met [[Priya Sharma]]",
        [Person(person_id="priya", display_name="Priya Sharma", role="guest")])

    await pm.record("jan", "Priya helpt me", "Fijn")

    assert sorted(p.person_id for p in await store.list_people()) == ["jan", "priya"]
    assert "[[priya]]" in await pm.get_memory("jan")


async def test_a_first_name_resolves_when_it_is_unambiguous() -> None:
    store, pm = await _rig(
        "- Ging wandelen met [[Priya]]",
        [Person(person_id="priya", display_name="Priya Sharma", role="guest")])

    await pm.record("jan", "iets", "iets")

    assert "[[priya]]" in await pm.get_memory("jan")


async def test_two_people_share_a_name_so_he_refuses_to_guess() -> None:
    """Guessing would attach a child's birthday to the wrong profile."""
    store, pm = await _rig(
        "- Sprak met [[Jan]] over voetbal",
        [Person(person_id="jan-b", display_name="Jan Peeters", role="guest")])

    await pm.record("jan", "iets", "iets")

    memory = await pm.get_memory("jan")
    assert "[[" not in memory, "an unresolved link is a node pointing at nobody"
    assert "Jan" in memory, "but the sentence survives as prose"
    assert sorted(p.person_id for p in await store.list_people()) == ["jan", "jan-b"]


async def test_a_new_name_becomes_a_profile_he_is_marked_as_creating() -> None:
    store, pm = await _rig("- Zijn buurman [[Rik]] helpt met de tuin")

    await pm.record("jan", "Rik helpt me", "Aardig")

    rik = await store.get_person("rik")
    assert rik is not None and rik.display_name == "Rik"
    assert rik.auto_created is True, "the owner must be able to tell it from their own work"
    assert rik.role.value == "guest", "a conservative role the owner can promote"
    assert "[[rik]]" in await pm.get_memory("jan")


async def test_one_odd_reply_cannot_spawn_a_household() -> None:
    store, pm = await _rig(
        "- [[A]] en [[B]] en [[C]] en [[D]] en [[E]] waren er ook")

    await pm.record("jan", "iets", "iets")

    created = [p for p in await store.list_people() if p.auto_created]
    assert len(created) <= 3


async def test_the_speaker_is_never_linked_to_themselves() -> None:
    store, pm = await _rig("- [[jan]] houdt van hardlopen")

    await pm.record("jan", "iets", "iets")

    assert "[[" not in await pm.get_memory("jan")


async def test_he_can_get_it_wrong_and_the_mitigations_are_the_point() -> None:
    """An honest limitation, pinned rather than papered over.

    Anything the model wraps in [[...]] becomes a profile. The prompt says
    "only real people, never places, teams, products or pets", and a prompt is
    an instruction, not a guarantee — a product name confidently linked WILL
    get a profile. Nothing local can reliably tell "Rik" from "Reachy Mini".

    So the defences are the ones that survive being wrong: a cap, so one odd
    reply cannot fill the household; and a mark, so the owner can always see
    which profiles are his doing and delete them in one click. This test exists
    so nobody later mistakes the prompt for a filter.
    """
    store, pm = await _rig("- Bouwt aan een [[Reachy Mini]] robot")

    await pm.record("jan", "iets", "iets")

    made = [p for p in await store.list_people() if p.auto_created]
    assert len(made) == 1, "it happens — the prompt is not a filter"
    assert made[0].auto_created is True, "and it is always visibly his doing"
    assert made[0].role.value == "guest", "never something with standing"
