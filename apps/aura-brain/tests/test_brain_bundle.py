"""U342: take him with you — everything he learned, onto the other laptop.

Asked as: *"can we add option to do export of brain, so i can import it on
other laptop? so he doesn't need to learn everything all over again"*.

Three things were wrong with the answer "there is an export button":

1. **There was no import.** `GET /knowledge/export` has existed since U104 and
   nothing could ever read it back. A file you cannot load is a souvenir.
2. **It carried no faces.** People and facts travelled; the embeddings stayed.
   On the new machine he would know everything about you and not recognise you
   — which is the half the owner actually means by "learn all over again".
3. **It was plain text.** Every fact about the household, in a file on a USB
   stick. The knowledge store is encrypted at rest precisely so a copy is
   worthless; an export that undoes that undoes the promise with it.

So the transfer bundle is sealed with a passphrase the owner picks, carries the
faces, and merges on the far side instead of overwriting — importing the same
file twice must not double the graph, because someone will do exactly that.

The plain `GET /knowledge/export` stays as it is: it is the "what do you
actually hold about me" answer, and that one should be readable.
"""

from __future__ import annotations

import os

os.environ.setdefault("LLM_PROVIDER", "echo")

import pytest
from aura_brain import brain_transfer
from shared_schemas.knowledge import InMemoryKnowledgeStore, Person, ProfileFact
from shared_schemas.knowledge.recognition import EmbeddingMatcher

PASSPHRASE = "a passphrase the owner picks"
OMK = b"0" * 32


async def _populated(tmp_path):
    store = InMemoryKnowledgeStore()
    await store.upsert_person(Person(person_id="jan", display_name="Jan Testperson", role="owner"))
    await store.upsert_person(Person(person_id="ada", display_name="Ada", role="family"))
    await store.add_fact(ProfileFact(person_id="jan", key="project",
                                     value="Builds a [[Reachy Mini]] assistant"))
    await store.add_fact(ProfileFact(person_id="ada", key="drinks", value="tea, never coffee"))
    matcher = EmbeddingMatcher(OMK, path=tmp_path / "faces.enc.json")
    matcher.enroll("jan", [0.1, 0.2, 0.3])
    matcher.enroll("ada", [0.9, 0.8, 0.7])
    return store, matcher


async def _fresh(tmp_path, name="new"):
    return InMemoryKnowledgeStore(), EmbeddingMatcher(OMK, path=tmp_path / f"{name}.enc.json")


# ── the bundle itself ──────────────────────────────────────────────────────

async def test_the_bundle_is_sealed_and_the_facts_are_not_in_it(tmp_path) -> None:
    """A file on a memory stick is the case the store's encryption exists for."""
    store, matcher = await _populated(tmp_path)

    blob = await brain_transfer.seal_bundle(store, matcher, PASSPHRASE)

    assert b"Reachy Mini" not in blob
    assert b"tea, never coffee" not in blob
    # U365: three letters turn up in random base64 often enough to fail a
    # run for no reason. The property is "the plaintext is not readable",
    # so assert it with something long enough to mean that.
    assert b"Jan Testperson" not in blob


async def test_it_says_what_it_holds_without_saying_who(tmp_path) -> None:
    """You must be able to see what a file is before you import it — counts,
    never names."""
    import json

    store, matcher = await _populated(tmp_path)
    header = json.loads(await brain_transfer.seal_bundle(store, matcher, PASSPHRASE))

    assert header["format"] == "aura-brain-export"
    assert header["contents"]["people"] == 2
    assert header["contents"]["facts"] == 2
    assert header["contents"]["faces"] == 2
    # U365: same reason as above — the sealed blob is base64, and three
    # letters turn up in it by chance often enough to fail a run.
    assert "Jan Testperson" not in json.dumps(header)


async def test_everything_he_learned_arrives_on_the_other_machine(tmp_path) -> None:
    store, matcher = await _populated(tmp_path)
    blob = await brain_transfer.seal_bundle(store, matcher, PASSPHRASE)

    far_store, far_matcher = await _fresh(tmp_path)
    summary = await brain_transfer.open_bundle(far_store, far_matcher, blob, PASSPHRASE)

    assert summary["people"] == 2 and summary["facts"] == 2 and summary["faces"] == 2
    assert {p.person_id for p in await far_store.list_people()} == {"jan", "ada"}
    facts = await far_store.get_facts("jan")
    assert any("[[Reachy Mini]]" in f.value for f in facts)


async def test_he_recognises_you_there_too(tmp_path) -> None:
    """The half that made "he has to learn everything again" true."""
    store, matcher = await _populated(tmp_path)
    blob = await brain_transfer.seal_bundle(store, matcher, PASSPHRASE)

    far_store, far_matcher = await _fresh(tmp_path)
    await brain_transfer.open_bundle(far_store, far_matcher, blob, PASSPHRASE)

    who, confidence = far_matcher.identify([0.1, 0.2, 0.3])
    assert who == "jan", f"he did not know the face ({confidence})"


async def test_importing_twice_does_not_double_anything(tmp_path) -> None:
    """Someone will do this. It must be boring when they do."""
    store, matcher = await _populated(tmp_path)
    blob = await brain_transfer.seal_bundle(store, matcher, PASSPHRASE)

    far_store, far_matcher = await _fresh(tmp_path)
    await brain_transfer.open_bundle(far_store, far_matcher, blob, PASSPHRASE)
    again = await brain_transfer.open_bundle(far_store, far_matcher, blob, PASSPHRASE)

    assert len(await far_store.get_facts("jan")) == 1
    assert again["facts"] == 0, "it added the same facts a second time"


async def test_what_is_already_known_there_is_kept(tmp_path) -> None:
    """Import merges. A machine that already knows somebody must not lose what
    it knows because a bundle from elsewhere is quieter about them."""
    store, matcher = await _populated(tmp_path)
    blob = await brain_transfer.seal_bundle(store, matcher, PASSPHRASE)

    far_store, far_matcher = await _fresh(tmp_path)
    await far_store.upsert_person(Person(person_id="ada", display_name="Ada", role="family"))
    await far_store.add_fact(ProfileFact(person_id="ada", key="local", value="only known here"))

    await brain_transfer.open_bundle(far_store, far_matcher, blob, PASSPHRASE)

    values = {f.value for f in await far_store.get_facts("ada")}
    assert "only known here" in values
    assert "tea, never coffee" in values


async def test_the_wrong_passphrase_is_refused_clearly(tmp_path) -> None:
    store, matcher = await _populated(tmp_path)
    blob = await brain_transfer.seal_bundle(store, matcher, PASSPHRASE)

    far_store, far_matcher = await _fresh(tmp_path)
    with pytest.raises(brain_transfer.BundleError) as exc:
        await brain_transfer.open_bundle(far_store, far_matcher, blob, "not the one")
    assert "passphrase" in str(exc.value).lower()


async def test_something_that_is_not_a_bundle_is_refused(tmp_path) -> None:
    far_store, far_matcher = await _fresh(tmp_path)
    for junk in (b"{}", b"not json at all", b'{"format": "something-else"}'):
        with pytest.raises(brain_transfer.BundleError):
            await brain_transfer.open_bundle(far_store, far_matcher, junk, PASSPHRASE)


async def test_skills_travel_and_are_never_silently_overwritten(tmp_path) -> None:
    """What he learned to DO is learning too. But a skill on the far machine
    may be the newer one, and losing it to an import nobody expected to write
    files would be the worst kind of surprise."""
    here, there = tmp_path / "here", tmp_path / "there"
    here.mkdir(), there.mkdir()
    (here / "spotify.md").write_text("# play a track\nfrom home", encoding="utf-8")
    (here / "vscode.md").write_text("# open a repo", encoding="utf-8")
    (there / "spotify.md").write_text("# play a track\nEDITED ON THIS MACHINE", encoding="utf-8")

    store, matcher = await _populated(tmp_path)
    blob = await brain_transfer.seal_bundle(store, matcher, PASSPHRASE, skills_dir=here)

    far_store, far_matcher = await _fresh(tmp_path)
    summary = await brain_transfer.open_bundle(far_store, far_matcher, blob, PASSPHRASE,
                                               skills_dir=there)

    assert (there / "vscode.md").exists()
    assert "EDITED ON THIS MACHINE" in (there / "spotify.md").read_text(encoding="utf-8")
    assert summary["skills"] == 1
    assert summary["skills_kept"] == 1


# ── through the API, the way the console will use it ───────────────────────

def test_the_round_trip_works_through_the_endpoints(monkeypatch, tmp_path) -> None:
    """Export on one machine, import on the next. The console does exactly
    these two calls, so this is the thing that has to hold."""
    from fastapi.testclient import TestClient

    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("SKILLS_DIR", str(tmp_path / "skills"))

    from aura_brain.main import create_app

    with TestClient(create_app()) as client:
        client.put("/knowledge/people/jan",
                   json={"display_name": "Jan", "role": "owner"})
        client.post("/knowledge/people/jan/facts",
                    json={"key": "project", "value": "Builds a [[Reachy Mini]] assistant"})

        sealed = client.post("/knowledge/transfer/export",
                             json={"passphrase": PASSPHRASE})
        assert sealed.status_code == 200, sealed.text
        assert b"Reachy Mini" not in sealed.content
        assert "attachment" in sealed.headers.get("content-disposition", "")

        # A fresh machine is a fresh store; here, the same one is enough to
        # prove the file reads back and merges without doubling.
        again = client.post("/knowledge/transfer/import",
                            json={"bundle": sealed.text, "passphrase": PASSPHRASE})
        assert again.status_code == 200, again.text
        assert again.json()["facts"] == 0, "it re-added what was already there"

        wrong = client.post("/knowledge/transfer/import",
                            json={"bundle": sealed.text, "passphrase": "wrong one"})
        assert wrong.status_code == 422
        assert "passphrase" in wrong.json()["error"].lower()


def test_a_short_passphrase_is_refused_before_anything_is_written(tmp_path) -> None:
    """Sealing a household's facts behind "1234" is not sealing them."""
    from fastapi.testclient import TestClient

    from aura_brain.main import create_app

    with TestClient(create_app()) as client:
        r = client.post("/knowledge/transfer/export", json={"passphrase": "short"})
        assert r.status_code == 422
        assert "8" in r.json()["error"]
