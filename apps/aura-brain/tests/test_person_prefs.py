"""U274: per-person language and character.

Asked as "per person, add option to select default language and default
robot" — the robot being which of his characters he becomes for that person.
Both are empty by default and empty means "whatever the house is set to", so
a per-person setting never quietly becomes a second global one.

Also pins a bug found in the same endpoint: PUT /people/{id} promised
"omitted fields keep their current value" but rebuilt the Person from three
named fields, so everything added since — the avatar — was reset to its
default on any update. Changing someone's role deleted their photo.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from shared_schemas.knowledge import InMemoryKnowledgeStore, Person


@pytest.fixture()
def client():
    from aura_brain import knowledge_api

    store = InMemoryKnowledgeStore()
    knowledge_api.set_store(store)
    knowledge_api.set_omk_loaded(False)
    app = FastAPI()
    app.include_router(knowledge_api.router)
    return TestClient(app), store


def test_a_person_starts_with_no_overrides(client) -> None:
    c, _ = client
    c.put("/knowledge/people/jan", json={"display_name": "Jan", "role": "owner"})
    p = c.get("/knowledge/people/jan").json()["person"]
    assert p["language"] == ""      # "same as everyone"
    assert p["character"] == ""


def test_language_and_character_round_trip(client) -> None:
    c, _ = client
    c.put("/knowledge/people/mila", json={"display_name": "Mila", "role": "minor"})
    c.put("/knowledge/people/mila", json={"language": "fr", "character": "buddy"})
    p = c.get("/knowledge/people/mila").json()["person"]
    assert p["language"] == "fr"
    assert p["character"] == "buddy"
    assert p["display_name"] == "Mila"       # untouched by the second call
    assert p["role"] == "minor"


def test_clearing_an_override_is_a_real_choice(client) -> None:
    """Empty means "follow the house" — it must be settable, not just absent."""
    c, _ = client
    c.put("/knowledge/people/mila", json={"display_name": "Mila", "language": "fr"})
    c.put("/knowledge/people/mila", json={"language": ""})
    assert c.get("/knowledge/people/mila").json()["person"]["language"] == ""


async def test_updating_a_person_no_longer_deletes_their_photo(client) -> None:
    """The merge comment was only ever true of the fields it named."""
    c, store = client
    await store.upsert_person(Person(
        person_id="jan", display_name="Jan", role="owner",
        avatar="data:image/png;base64,AAAA", language="nl"))

    c.put("/knowledge/people/jan", json={"role": "family"})

    p = c.get("/knowledge/people/jan").json()["person"]
    assert p["role"] == "family"
    assert p["avatar"] == "data:image/png;base64,AAAA", "a role change must not wipe the avatar"
    assert p["language"] == "nl", "nor any other field it does not mention"


def test_every_role_the_console_offers_is_one_the_brain_accepts(client) -> None:
    """U274: the People screen offered "kid". No such role has ever existed —
    the brain knows owner/family/guest/minor/demo — so every attempt to mark
    somebody a child was rejected with 422, and rejected silently, because a
    failed role change rendered nothing. It is also the role that matters
    most: a minor is never learned about passively (ADR-008 §10).

    Read from the actual .vue so the two cannot drift apart again.
    """
    import re
    from pathlib import Path

    from shared_schemas.knowledge import PersonRole

    view = Path(__file__).resolve().parents[3] / "apps/operator-console/src/views/PeopleView.vue"
    if not view.exists():          # brain suite may run without the console
        pytest.skip("operator console not present")

    template = view.read_text(encoding="utf-8").split("<script", 1)[0]
    # Only the ROLE selects — the same file also offers consent scopes and,
    # since U274, languages and characters.
    blocks = re.findall(r'<select[^>]*aria-label="Role"[^>]*>(.*?)</select>',
                        template, re.S)
    assert blocks, "the role selects should still be there"
    # Both spellings: `<option value="minor">label</option>` and the bare
    # `<option>guest</option>`. The broken one was bare, so a pattern that
    # only understood the attribute form would have passed against it —
    # a test that agrees with the bug is worse than no test.
    offered = set()
    for b in blocks:
        for tag, body in re.findall(r'<option([^>]*)>([^<]*)</option>', b):
            attr = re.search(r'value="([^"]*)"', tag)
            offered.add((attr.group(1) if attr else body).strip())
    known = {r.value for r in PersonRole}
    assert offered <= known, f"the console offers roles the brain rejects: {offered - known}"
