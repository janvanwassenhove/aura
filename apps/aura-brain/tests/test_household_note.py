"""U293: he should already know the people in the house.

Reported with a screenshot: the owner talks about Jappe, Elke and Limme — all
three of whom have profiles — and says so out loud. He answers "Ik ken de
namen uit ons gesprek": true, and exactly the problem.

He was only ever told who was standing in front of him. The roster reached
the memory distiller (U280 links a remembered line to the person it is about)
and nothing else, so DURING a conversation a familiar name arrived as a
stranger. "Leert hij dit zichzelf niet aan?" — he does, afterwards. This is
about the moment itself.

Names and roles only. What he knows ABOUT each of them stays behind the
judgment layer, where the role rules live: a minor is not passively learned
about (ADR-008 §10), and putting everyone's facts in every prompt would let a
guest overhear the household's private life.
"""

from __future__ import annotations

import pytest
from orchestrator.pipeline import OrchestratorPipeline
from shared_schemas.knowledge import InMemoryKnowledgeStore, Person


class _Judgment:
    def __init__(self, store) -> None:
        self._store = store


async def _pipeline(people: list[Person], active: str | None = None):
    store = InMemoryKnowledgeStore()
    for p in people:
        await store.upsert_person(p)
    pipe = OrchestratorPipeline.__new__(OrchestratorPipeline)
    pipe._judgment = _Judgment(store)
    pipe._active_person_id = active
    return pipe


HOUSEHOLD = [
    Person(person_id="jan", display_name="Jan", role="owner"),
    Person(person_id="jappe", display_name="Jappe", role="minor"),
    Person(person_id="elke", display_name="Elke", role="family"),
    Person(person_id="limme", display_name="Limme", role="family"),
]


async def test_he_is_told_who_else_he_knows() -> None:
    pipe = await _pipeline(HOUSEHOLD, active="jan")
    note = await pipe.household_note()

    for name in ("Jappe", "Elke", "Limme"):
        assert name in note, f"{name} has a profile; he should know that"


async def test_the_person_in_front_of_him_is_not_repeated() -> None:
    """person_note already covers them, in far more detail."""
    pipe = await _pipeline(HOUSEHOLD, active="jan")
    assert "Jan" not in await pipe.household_note()


async def test_it_says_he_already_knows_them() -> None:
    """The exact sentence the screenshot was about."""
    pipe = await _pipeline(HOUSEHOLD, active="jan")
    note = await pipe.household_note()
    assert "already know" in note
    assert "only know the name from" in note


async def test_guests_and_the_demo_profile_stay_out() -> None:
    """A guest is not remembered, and the demo persona is fiction."""
    pipe = await _pipeline(HOUSEHOLD + [
        Person(person_id="guest-1", display_name="Guest 1", role="guest"),
        Person(person_id="mila", display_name="Mila Kovač", role="demo"),
    ], active="jan")
    note = await pipe.household_note()

    assert "Guest 1" not in note
    assert "Mila" not in note


async def test_only_names_and_roles_travel() -> None:
    """Not their facts — that is the judgment layer's call, per person."""
    store_people = [
        Person(person_id="jan", display_name="Jan", role="owner"),
        Person(person_id="elke", display_name="Elke", role="family",
               description="works nights at the hospital"),
    ]
    pipe = await _pipeline(store_people, active="jan")
    note = await pipe.household_note()

    assert "Elke" in note
    assert "hospital" not in note, "a description is not roster material"


async def test_a_household_of_one_says_nothing() -> None:
    pipe = await _pipeline([Person(person_id="jan", display_name="Jan", role="owner")],
                           active="jan")
    assert await pipe.household_note() == "", "no empty heading when there is nobody"


async def test_a_broken_store_costs_the_roster_not_the_turn() -> None:
    class _Boom:
        async def list_people(self):
            raise RuntimeError("store is locked")

    pipe = OrchestratorPipeline.__new__(OrchestratorPipeline)
    pipe._judgment = _Judgment(_Boom())
    pipe._active_person_id = "jan"

    assert await pipe.household_note() == ""
