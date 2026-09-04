"""U294: he can go and look someone up himself.

Asked as "hij moet zich dit zelf aanleren bij de personen te gaan kijken (ook
als er dan bv. nieuwe bijkomen)".

U293's roster answers WHO exists — rebuilt from the store every turn, so
somebody added mid-conversation is there in the next sentence. It deliberately
carries names and roles only, because pushing everyone's details into every
prompt would let a guest overhear the household's private life.

This is the other half: a tool, so when a name actually matters he can look it
up rather than guess from the conversation. Routed through the JUDGMENT LAYER,
never the store directly — that is where the role rules live (a guest yields a
name and nothing more; a minor yields explicit facts and never observed
signals, ADR-008 §10). A tool that read around it would be a hole in the
consent model dressed up as a convenience.
"""

from __future__ import annotations

import pytest
from orchestrator.pipeline import OrchestratorPipeline
from shared_schemas.knowledge import InMemoryKnowledgeStore, Person


class _Ctx:
    def __init__(self, note: str) -> None:
        self._note = note

    def to_system_note(self) -> str:
        return self._note


class _Judgment:
    """Stands in for the real layer, and records that it was consulted."""

    def __init__(self, store, note: str = "Plays football on Sundays.") -> None:
        self._store = store
        self._note = note
        self.asked_about: list[str] = []

    async def build_context(self, person_id):
        self.asked_about.append(person_id)
        return _Ctx(self._note) if self._note else None


async def _pipe(people: list[Person], note: str = "Plays football on Sundays."):
    store = InMemoryKnowledgeStore()
    for p in people:
        await store.upsert_person(p)
    pipe = OrchestratorPipeline.__new__(OrchestratorPipeline)
    pipe._judgment = _Judgment(store, note)
    pipe._active_person_id = "jan"
    return pipe


HOUSE = [
    Person(person_id="jan", display_name="Jan", role="owner"),
    Person(person_id="limme", display_name="Limme", role="family"),
    Person(person_id="jappe", display_name="Jappe", role="minor"),
]


async def test_he_can_look_up_someone_he_knows() -> None:
    pipe = await _pipe(HOUSE)
    out = await pipe._look_up_person("Limme")
    assert "Limme" in out and "family" in out
    assert "football" in out


async def test_the_answer_comes_through_the_judgment_layer() -> None:
    """Not from the store. The layer is what decides what may be said."""
    pipe = await _pipe(HOUSE)
    await pipe._look_up_person("Jappe")
    assert pipe._judgment.asked_about == ["jappe"], "the consent rules must run"


async def test_a_first_name_is_enough() -> None:
    pipe = await _pipe([
        Person(person_id="jan", display_name="Jan", role="owner"),
        Person(person_id="priya", display_name="Priya Sharma", role="guest"),
    ])
    assert "Priya" in await pipe._look_up_person("Priya")


async def test_an_exact_name_wins_over_a_shared_first_name() -> None:
    """"Jan" IS someone's whole name here; "Jan Peeters" merely starts the
    same. Calling that ambiguous would make the common case useless."""
    pipe = await _pipe([
        Person(person_id="jan", display_name="Jan", role="owner"),
        Person(person_id="jan-p", display_name="Jan Peeters", role="guest"),
    ])
    out = await pipe._look_up_person("Jan")
    assert "Peeters" not in out


async def test_two_people_with_one_first_name_are_never_guessed_between() -> None:
    """Attaching one person's life to another is worse than asking which."""
    pipe = await _pipe([
        Person(person_id="jan", display_name="Jan", role="owner"),
        Person(person_id="jan-p", display_name="Jan Peeters", role="guest"),
        Person(person_id="jan-w", display_name="Jan Willems", role="guest"),
    ])
    out = await pipe._look_up_person("jan peeters")
    assert "Peeters" in out, "a full name still resolves"

    out = await pipe._look_up_person("Jannes")
    assert "no profile" in out.lower(), "a near-miss is not a match"


async def test_somebody_he_does_not_know_is_said_plainly() -> None:
    pipe = await _pipe(HOUSE)
    out = await pipe._look_up_person("Nora")
    assert "no profile" in out.lower()
    assert "new to me" in out.lower(), "an honest gap, not a failure"


async def test_a_person_he_may_say_nothing_about_still_resolves() -> None:
    """A guest with no shareable context: he knows they exist and says so,
    rather than inventing or claiming never to have heard of them."""
    pipe = await _pipe(HOUSE, note="")
    out = await pipe._look_up_person("Limme")
    assert "Limme" in out
    assert "nothing I may share" in out


async def test_an_empty_name_asks_rather_than_searching() -> None:
    pipe = await _pipe(HOUSE)
    assert "name" in (await pipe._look_up_person("  ")).lower()


def test_the_tool_is_offered_in_every_mode() -> None:
    """Knowing who is being discussed is not a capability to switch on."""
    from shared_policies import MODE_TOOL_MAP

    for mode, tools in MODE_TOOL_MAP.items():
        assert "look_up_person" in tools, mode


def test_the_tool_is_shaped_like_every_other_tool() -> None:
    """It was hand-written as a bare dict first, and the model is handed
    OpenAI function specs — so it broke two unrelated tests that walk the
    schema list. Built with the same helper now."""
    from orchestrator.tool_schemas import TOOL_SCHEMAS

    spec = TOOL_SCHEMAS["look_up_person"]
    assert spec["type"] == "function"
    assert spec["function"]["name"] == "look_up_person"
    assert "name" in spec["function"]["parameters"]["properties"]
