"""U244: the matcher knew twelve faces, the store knew four people.

The ten extras were guest profiles auto-created by U181 and later deleted by the
owner. Deleting a person never removed their face, so they lived on as ids that
win a match and then resolve to nobody.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from aura_brain.face_reconcile import find_orphans, reconcile


@dataclass
class _Person:
    person_id: str


class FakeStore:
    def __init__(self, ids: list[str]) -> None:
        self._ids = ids

    async def list_people(self) -> list[_Person]:
        return [_Person(pid) for pid in self._ids]


class FakeMatcher:
    def __init__(self, ids: list[str]) -> None:
        self.enrolled = list(ids)
        self.flushes = 0

    def enrolled_ids(self) -> list[str]:
        return list(self.enrolled)

    def forget(self, person_id: str) -> None:
        self.enrolled = [p for p in self.enrolled if p != person_id]
        self.flushes += 1


# The state actually observed on the owner's machine.
LIVE_ENROLLED = [
    "guest-1", "guest-2", "jappe", "guest-3", "guest-4", "guest-5",
    "guest-6", "guest-7", "guest-8", "guest-9", "guest-10", "jan",
]
LIVE_PEOPLE = ["mila", "jan", "jappe", "elke"]


@pytest.mark.asyncio
async def test_the_reported_state_drops_ten_and_keeps_two() -> None:
    matcher = FakeMatcher(LIVE_ENROLLED)
    dropped = await reconcile(matcher, FakeStore(LIVE_PEOPLE))
    assert len(dropped) == 10
    assert set(matcher.enrolled) == {"jan", "jappe"}, "real people keep their faces"


@pytest.mark.asyncio
async def test_a_person_without_an_enrolled_face_is_not_a_problem() -> None:
    """mila and elke exist but have never been taught a face. That is normal."""
    matcher = FakeMatcher(["jan"])
    assert await reconcile(matcher, FakeStore(LIVE_PEOPLE)) == []
    assert matcher.enrolled == ["jan"]


@pytest.mark.asyncio
async def test_an_empty_store_is_never_treated_as_everyone_deleted() -> None:
    """The dangerous case. A store that lists nobody is far more likely to be
    one that has not loaded than a house where everyone was erased — and being
    wrong here costs every face, with no way back."""
    matcher = FakeMatcher(["jan", "jappe"])
    assert await find_orphans(matcher, FakeStore([])) == []
    assert await reconcile(matcher, FakeStore([])) == []
    assert matcher.enrolled == ["jan", "jappe"], "nothing may be dropped"


@pytest.mark.asyncio
async def test_it_is_idempotent() -> None:
    matcher = FakeMatcher(LIVE_ENROLLED)
    await reconcile(matcher, FakeStore(LIVE_PEOPLE))
    flushes = matcher.flushes
    assert await reconcile(matcher, FakeStore(LIVE_PEOPLE)) == []
    assert matcher.flushes == flushes, "a clean run must not rewrite the file"


@pytest.mark.asyncio
async def test_every_drop_reaches_disk() -> None:
    """forget() flushes; erasure that only happens in memory is not erasure."""
    matcher = FakeMatcher(LIVE_ENROLLED)
    dropped = await reconcile(matcher, FakeStore(LIVE_PEOPLE))
    assert matcher.flushes == len(dropped)


def test_deleting_a_person_also_erases_their_face() -> None:
    """U244: the leak that made the orphans. Right-to-be-forgotten wiped the
    profile and the snapshots but left the biometric embedding enrolled — so
    the face kept winning matches, and the erasure was not one."""
    import os

    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    os.environ.setdefault("LLM_PROVIDER", "echo")
    os.environ.setdefault("STT_PROVIDER", "null")
    os.environ.setdefault("TTS_PROVIDER", "null")

    from aura_brain import recognition_api
    from aura_brain.main import create_app
    from fastapi.testclient import TestClient

    app = create_app()
    with TestClient(app) as client:
        assert client.put("/knowledge/people/jan",
                          json={"display_name": "Jan", "role": "owner"}).status_code == 200

        faces = FakeMatcher(["jan"])
        recognition_api.init(faces, None, None, None)
        try:
            assert client.delete("/knowledge/people/jan").status_code == 200
            assert faces.enrolled == [], "the face must go with the person"
        finally:
            recognition_api.init(None, None, None, None)


def test_deleting_a_person_works_with_recognition_switched_off() -> None:
    """Recognition is legitimately off without a passphrase — deleting a person
    must not depend on a matcher being there."""
    import os

    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

    from aura_brain import recognition_api
    from aura_brain.main import create_app
    from fastapi.testclient import TestClient

    recognition_api.init(None, None, None, None)
    app = create_app()
    with TestClient(app) as client:
        assert client.put("/knowledge/people/elke",
                          json={"display_name": "Elke", "role": "family"}).status_code == 200
        assert client.delete("/knowledge/people/elke").status_code == 200
