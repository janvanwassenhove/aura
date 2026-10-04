"""U404: a persona has a look, so the projector shows who is speaking.

Asked for (translated): *"make it possible"* — the avatar on the projector
switching with a beat's `persona:`. The subtitle already said who spoke
(U349); the picture stayed the one character chosen in the header.

A persona (the brain's: voice and character) and a look (the console's ten
drawn archetypes) had no link at all. Now a persona carries its look; the
built-ins come with one that fits them, and a persona file written before
this has it filled in on reading, because the owner's copies of the built-ins
were seeded long ago and are never rewritten.
"""

from __future__ import annotations

import json

import pytest
from aura_brain.characters import LOOKS, CharacterStore

BUILT_IN = {
    "friendly_assistant": "scout",
    "dry_tech_butler": "slab",
    "kids_companion": "buddy",
    "workshop_coach": "host",
    "quiet_mode": "orb",
}


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("CHARACTERS_DIR", str(tmp_path / "personas"))
    return CharacterStore(), tmp_path / "personas"


def test_the_looks_are_the_consoles_ten() -> None:
    assert set(LOOKS) == {"scout", "sentinel", "slab", "mender", "astro",
                          "grump", "halo", "buddy", "host", "orb"}


def test_every_built_in_persona_has_a_look_that_fits(store) -> None:
    s, _ = store
    assert {c.id: c.look for c in s.all() if c.id in BUILT_IN} == BUILT_IN


def test_a_persona_seeded_before_looks_existed_gets_its_own(store) -> None:
    s, folder = store
    s.all()                                        # seeds the built-ins
    path = folder / "dry_tech_butler.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("look", None)                         # as written before U404
    path.write_text(json.dumps(data), encoding="utf-8")
    assert s.get("dry_tech_butler").look == "slab"


def test_a_persona_of_your_own_has_no_look_until_you_give_it_one(store) -> None:
    s, folder = store
    s.all()
    (folder / "mine.json").write_text(json.dumps({"id": "mine", "display_name": "Mine"}),
                                      encoding="utf-8")
    assert s.get("mine").look == "", "no look: the header's character is shown"


def test_the_look_can_be_changed(store) -> None:
    s, _ = store
    assert s.update("dry_tech_butler", {"look": "grump"}).look == "grump"
    assert s.get("dry_tech_butler").look == "grump", "and it is kept"


def test_a_look_that_is_not_one_is_ignored(store) -> None:
    s, _ = store
    assert s.update("dry_tech_butler", {"look": "terminator"}).look == "slab"


def test_the_characters_api_says_each_ones_look(store) -> None:
    from aura_brain import setup_api
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(setup_api.router)
    chars = TestClient(app).get("/setup/characters").json()["characters"]
    assert {c["id"]: c["look"] for c in chars if c["id"] in BUILT_IN} == BUILT_IN
