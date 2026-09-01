"""U288: he can see more than one person, and listens accordingly.

Three questions, one unit:

  * "moeten we per persona al default taal meegeven (als hij persoon herkent
    hierop aanpassen)?" — the per-person language exists since U274, but it
    only ever shaped the REPLY. The microphone kept listening in the language
    of the house.
  * "wat wanneer hij 2 personen herkent?" — he never did. `embed()` returns
    the LARGEST face only, so everyone but the person nearest the camera was
    invisible, silently, for the whole life of the app.

Together those are one risk: pinning the microphone to one housemate's
language while a different one is talking. So the rule is deliberately
conservative — a language is only used when the room agrees on it.
"""

from __future__ import annotations

import pytest
from aura_brain import voice
from aura_brain.perception import PerceptionLoop
from shared_schemas.knowledge import InMemoryKnowledgeStore, Person


class _Matcher:
    """Identifies an embedding by its first element: [1] -> the first person."""

    def __init__(self, order: list[str]) -> None:
        self._order = order

    def identify(self, emb):
        idx = int(emb[0])
        return (self._order[idx], 0.9) if 0 <= idx < len(self._order) else (None, 0.0)


@pytest.fixture(autouse=True)
def _quiet_voice():
    voice.set_person_language("")
    yield
    voice.set_person_language("")


async def _loop(people: list[Person], order: list[str]) -> PerceptionLoop:
    store = InMemoryKnowledgeStore()
    for p in people:
        await store.upsert_person(p)
    loop = PerceptionLoop.__new__(PerceptionLoop)   # no camera, no robot
    loop._matcher = _Matcher(order)
    loop._store = store
    loop.people_present = []
    return loop


async def test_one_recognised_person_sets_the_listening_language() -> None:
    loop = await _loop(
        [Person(person_id="mila", display_name="Mila", role="family", language="fr")],
        ["mila"])

    loop._note_room([[0.0]])
    await loop._apply_room_language(loop.people_present)

    assert loop.people_present == ["mila"]
    assert voice._stt_language() == "fr"


async def test_everyone_in_frame_is_seen_not_just_the_nearest() -> None:
    loop = await _loop(
        [Person(person_id="jan", display_name="Jan", role="owner"),
         Person(person_id="mila", display_name="Mila", role="family")],
        ["jan", "mila"])

    loop._note_room([[0.0], [1.0]])

    assert loop.people_present == ["jan", "mila"], "the second person exists now"


async def test_two_people_who_disagree_get_no_pin(monkeypatch) -> None:
    """Choosing one of them is a guess made against the other."""
    monkeypatch.setenv("ASSISTANT_LANGUAGE", "auto")
    monkeypatch.setenv("LANGUAGE_FALLBACK", "nl")
    monkeypatch.setattr("locale.getlocale", lambda *a: (None, None))
    loop = await _loop(
        [Person(person_id="jan", display_name="Jan", role="owner", language="nl"),
         Person(person_id="mila", display_name="Mila", role="family", language="fr")],
        ["jan", "mila"])

    loop._note_room([[0.0], [1.0]])
    await loop._apply_room_language(loop.people_present)

    assert voice._stt_language() == "nl", "back to the household, not one of them"


async def test_two_people_who_share_a_language_still_get_it() -> None:
    loop = await _loop(
        [Person(person_id="jan", display_name="Jan", role="owner", language="fr"),
         Person(person_id="mila", display_name="Mila", role="family", language="fr")],
        ["jan", "mila"])

    loop._note_room([[0.0], [1.0]])
    await loop._apply_room_language(loop.people_present)

    assert voice._stt_language() == "fr"


async def test_an_empty_room_clears_the_hint() -> None:
    loop = await _loop(
        [Person(person_id="mila", display_name="Mila", role="family", language="fr")],
        ["mila"])
    loop._note_room([[0.0]])
    await loop._apply_room_language(loop.people_present)
    assert voice._stt_language() == "fr"

    loop._note_room([])
    await loop._apply_room_language([])

    assert loop.people_present == []
    assert voice._person_language == "", "he stops assuming when nobody is there"


async def test_a_person_without_a_language_changes_nothing(monkeypatch) -> None:
    monkeypatch.setenv("ASSISTANT_LANGUAGE", "auto")
    monkeypatch.setenv("LANGUAGE_FALLBACK", "nl")
    monkeypatch.setattr("locale.getlocale", lambda *a: (None, None))
    loop = await _loop(
        [Person(person_id="jan", display_name="Jan", role="owner")], ["jan"])

    loop._note_room([[0.0]])
    await loop._apply_room_language(loop.people_present)

    assert voice._stt_language() == "nl"
