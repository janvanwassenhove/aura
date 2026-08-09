"""U225 (audit S9): key-parameter rotation against real store files.

These tests exist because the migration runs once, on data that cannot be
regenerated. Every failure mode that would cost the owner their knowledge base
is asserted here: wrong passphrase, interrupted run, repeated run.

The work factor is turned down (monkeypatched) so the suite stays fast — the
migration logic is what is under test, not scrypt.
"""

from __future__ import annotations

import asyncio
import base64
import json

import pytest
from shared_schemas.knowledge import crypto
from shared_schemas.knowledge import omk as omk_mod
from shared_schemas.knowledge.encrypted_store import EncryptedKnowledgeStore
from shared_schemas.knowledge.models import Person, PersonRole
from shared_schemas.knowledge.recognition import EmbeddingMatcher

PASSPHRASE = "correct-horse-battery-staple"  # test fixture, privacy-ok
TEST_N, TEST_LEGACY_N = 2**10, 2**8


@pytest.fixture(autouse=True)
def _cheap_kdf(monkeypatch):
    monkeypatch.setattr(crypto, "SCRYPT_N", TEST_N)
    monkeypatch.setattr(crypto, "LEGACY_SCRYPT_N", TEST_LEGACY_N)


def _legacy_omk(env_salt=None):
    return crypto.derive_omk(PASSPHRASE, omk_mod.legacy_salt(env_salt), n=TEST_LEGACY_N)


def _seed_knowledge(path, key) -> None:
    store = EncryptedKnowledgeStore(key, path=path)
    asyncio.run(store.upsert_person(
        Person(person_id="p1", display_name="Ada", role=PersonRole.OWNER)))
    asyncio.run(store.upsert_person(
        Person(person_id="p2", display_name="Grace", role=PersonRole.GUEST)))


def _seed_recognition(path, key) -> None:
    matcher = EmbeddingMatcher(key, path=path)
    matcher.enroll("p1", [0.1, 0.2, 0.3])
    matcher.enroll("p2", [0.9, 0.8, 0.7])


def _names(path, key) -> list[str]:
    store = EncryptedKnowledgeStore(key, path=path)
    return sorted(p.display_name for p in asyncio.run(store.list_people()))


# ---------------------------------------------------------------------------


def test_fresh_install_gets_a_random_salt_and_the_current_work_factor(tmp_path):
    params = tmp_path / "key-params.json"
    key, report = omk_mod.open_omk(passphrase=PASSPHRASE, params_path=params,
                                   knowledge_paths=[tmp_path / "k.json"])
    doc = json.loads(params.read_text())
    assert doc["current"]["n"] == TEST_N
    assert "migrating_from" not in doc          # nothing to migrate
    assert report["migrated"] == {}
    # The salt is random per install — never the old hardcoded default.
    assert base64.b64decode(doc["current"]["salt_b64"]) != omk_mod.LEGACY_DEFAULT_SALT
    assert len(key) == 32


def test_two_installs_do_not_share_a_salt(tmp_path):
    salts = set()
    for i in range(2):
        p = tmp_path / f"i{i}" / "key-params.json"
        omk_mod.open_omk(passphrase=PASSPHRASE, params_path=p)
        salts.add(json.loads(p.read_text())["current"]["salt_b64"])
    assert len(salts) == 2


def test_legacy_data_survives_the_migration(tmp_path):
    kpath, rpath = tmp_path / "k.json", tmp_path / "r.json"
    old = _legacy_omk()
    _seed_knowledge(kpath, old)
    _seed_recognition(rpath, old)

    key, report = omk_mod.open_omk(
        passphrase=PASSPHRASE, params_path=tmp_path / "key-params.json",
        knowledge_paths=[kpath], recognition_paths=[rpath])

    assert key != old                                  # the OMK really rotated
    assert report["migrated"] == {str(kpath): 2, str(rpath): 2}
    assert _names(kpath, key) == ["Ada", "Grace"]      # …and the data came along
    assert EmbeddingMatcher(key, path=rpath).identify([0.1, 0.2, 0.3])[0] == "p1"


def test_migration_preserves_an_existing_custom_salt_path(tmp_path):
    """An install that set KNOWLEDGE_SALT must be migrated off THAT salt."""
    kpath = tmp_path / "k.json"
    _seed_knowledge(kpath, _legacy_omk("deadbeefdeadbeef"))
    key, report = omk_mod.open_omk(
        passphrase=PASSPHRASE, params_path=tmp_path / "key-params.json",
        knowledge_paths=[kpath], env_salt="deadbeefdeadbeef")
    assert report["migrated"] == {str(kpath): 2}
    assert _names(kpath, key) == ["Ada", "Grace"]


def test_a_wrong_passphrase_aborts_without_touching_a_byte(tmp_path):
    kpath = tmp_path / "k.json"
    _seed_knowledge(kpath, _legacy_omk())
    before = kpath.read_bytes()

    with pytest.raises(omk_mod.OmkError):
        omk_mod.open_omk(passphrase="not-the-right-one",  # test fixture, privacy-ok
                         params_path=tmp_path / "key-params.json",
                         knowledge_paths=[kpath])

    assert kpath.read_bytes() == before
    # …and the real passphrase still opens it afterwards.
    key, _ = omk_mod.open_omk(passphrase=PASSPHRASE,
                              params_path=tmp_path / "key-params.json",
                              knowledge_paths=[kpath])
    assert _names(kpath, key) == ["Ada", "Grace"]


def test_a_store_missed_on_the_first_run_is_still_recoverable(tmp_path):
    """The knowledge store rotates but recognition is never reached — the
    process died, or the extra was not installed that boot. The old parameters
    must survive so the next boot can still finish the job."""
    kpath, rpath = tmp_path / "k.json", tmp_path / "r.json"
    params = tmp_path / "key-params.json"
    old = _legacy_omk()
    _seed_knowledge(kpath, old)
    _seed_recognition(rpath, old)

    key1, _ = omk_mod.open_omk(passphrase=PASSPHRASE, params_path=params,
                               knowledge_paths=[kpath])
    assert "migrating_from" in json.loads(params.read_text())

    key2, report = omk_mod.open_omk(passphrase=PASSPHRASE, params_path=params,
                                    knowledge_paths=[kpath],
                                    recognition_paths=[rpath])
    assert key2 == key1
    assert str(kpath) in report["already_current"]     # not rewrapped twice
    assert report["migrated"] == {str(rpath): 2}
    assert _names(kpath, key2) == ["Ada", "Grace"]
    assert EmbeddingMatcher(key2, path=rpath).identify([0.9, 0.8, 0.7])[0] == "p2"


def test_a_foreign_store_does_not_take_the_readable_one_down_with_it(tmp_path):
    """recognition.enc.json left over from another install (different
    passphrase) must not stop the knowledge store from opening."""
    kpath, rpath = tmp_path / "k.json", tmp_path / "r.json"
    _seed_knowledge(kpath, _legacy_omk())
    _seed_recognition(rpath, crypto.derive_omk("a-totally-different-one",
                                               b"x" * 16, n=TEST_LEGACY_N))

    key, report = omk_mod.open_omk(
        passphrase=PASSPHRASE, params_path=tmp_path / "key-params.json",
        knowledge_paths=[kpath], recognition_paths=[rpath])

    assert report["migrated"] == {str(kpath): 2}
    assert report["unreadable"] == [str(rpath)]
    assert _names(kpath, key) == ["Ada", "Grace"]
    assert rpath.read_text()  # left exactly as it was, not rewritten or deleted


def test_a_foreign_recognition_file_alone_is_never_fatal(tmp_path):
    """No knowledge store yet (fresh install) + someone else's embeddings.
    There is nothing to protect, so the brain must still come up."""
    rpath = tmp_path / "r.json"
    _seed_recognition(rpath, crypto.derive_omk("someone-elses", b"x" * 16,
                                               n=TEST_LEGACY_N))
    key, report = omk_mod.open_omk(
        passphrase=PASSPHRASE, params_path=tmp_path / "key-params.json",
        knowledge_paths=[tmp_path / "k.json"], recognition_paths=[rpath])
    assert len(key) == 32
    assert report["unreadable"] == [str(rpath)]


def test_running_it_again_is_a_no_op(tmp_path):
    kpath = tmp_path / "k.json"
    params = tmp_path / "key-params.json"
    _seed_knowledge(kpath, _legacy_omk())
    key1, _ = omk_mod.open_omk(passphrase=PASSPHRASE, params_path=params,
                               knowledge_paths=[kpath])
    digest = kpath.read_bytes()
    key2, report = omk_mod.open_omk(passphrase=PASSPHRASE, params_path=params,
                                    knowledge_paths=[kpath])
    assert key2 == key1
    assert report["migrated"] == {}
    assert kpath.read_bytes() == digest


def test_legacy_salt_matches_the_pre_u225_derivation_exactly():
    # Byte-for-byte the old `.encode().ljust(16, b"0")[:16]`. If this changes,
    # every install from before U225 loses its data.
    assert omk_mod.legacy_salt(None) == b"aura-knowledge00"
    assert omk_mod.legacy_salt("testsalt") == b"testsalt00000000"
    assert omk_mod.legacy_salt("0123456789abcdefTOOLONG") == b"0123456789abcdef"


def test_an_unreadable_entry_does_not_block_the_others(tmp_path):
    """Bundles written under a different key already exist in the wild
    (list_people skips them). One must not make the whole upgrade impossible."""
    kpath = tmp_path / "k.json"
    _seed_knowledge(kpath, _legacy_omk())
    doc = json.loads(kpath.read_text())
    doc["people"]["ghost"] = {"wrapped_dek": base64.b64encode(b"x" * 40).decode(),
                              "blob": base64.b64encode(b"y" * 40).decode()}
    kpath.write_text(json.dumps(doc))

    key, report = omk_mod.open_omk(passphrase=PASSPHRASE,
                                   params_path=tmp_path / "key-params.json",
                                   knowledge_paths=[kpath])
    assert report["migrated"] == {str(kpath): 2}     # the two real people
    assert _names(kpath, key) == ["Ada", "Grace"]
    # The dead entry is carried across untouched, not silently deleted.
    assert "ghost" in json.loads(kpath.read_text())["people"]
