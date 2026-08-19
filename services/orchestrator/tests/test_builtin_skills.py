"""U194: the desktop skills that ship with the product."""

from __future__ import annotations

from dataclasses import replace

from orchestrator.builtin_skills import BUILTIN_SKILLS, seed_builtin_skills
from orchestrator.skills import Skill, SkillStore


def test_seeding_writes_every_builtin(tmp_path) -> None:
    store = SkillStore(str(tmp_path))
    added = seed_builtin_skills(store)

    assert set(added) == {s.name for s in BUILTIN_SKILLS}
    names = {s.name for s in store.all()}
    assert {"desktop-vscode", "desktop-spotify", "desktop-chrome",
            "desktop-ai-assistants"} <= names


def test_seeding_twice_adds_nothing(tmp_path) -> None:
    store = SkillStore(str(tmp_path))
    seed_builtin_skills(store)
    assert seed_builtin_skills(store) == []


def test_an_owner_edit_is_never_overwritten(tmp_path) -> None:
    """The contract: a default that reinstates itself is not a default.

    The owner rewrote the Spotify skill. A later boot must leave it alone —
    otherwise every restart silently undoes their work.
    """
    store = SkillStore(str(tmp_path))
    seed_builtin_skills(store)

    store.save(Skill(name="desktop-spotify", description="mine",
                     body="Only ever play jazz."))
    seed_builtin_skills(store)

    assert store.get("desktop-spotify").body == "Only ever play jazz."


def test_a_deleted_builtin_stays_deleted(tmp_path) -> None:
    store = SkillStore(str(tmp_path))
    seed_builtin_skills(store)
    store.delete("desktop-chrome")

    seed_builtin_skills(store)

    assert store.get("desktop-chrome") is None


def test_skills_fire_on_what_the_owner_would_actually_say(tmp_path) -> None:
    """Triggers are substring matches — a skill nobody can reach is dead code."""
    store = SkillStore(str(tmp_path))
    seed_builtin_skills(store)

    def relevant(text: str) -> set[str]:
        return {s.name for s in store.relevant(text, persona="default", person_id=None)}

    assert "desktop-spotify" in relevant("zet eens wat muziek op")
    assert "desktop-spotify" in relevant("play Radiohead on the kitchen speakers")
    assert "desktop-vscode" in relevant("open vscode voor mij")
    assert "desktop-vscode" in relevant("what does copilot say about this")
    assert "desktop-chrome" in relevant("open chrome en zoek het op")
    assert "desktop-ai-assistants" in relevant("vraag het aan claude")


def test_every_builtin_refuses_the_dangerous_things(tmp_path) -> None:
    """Screen control can type anything. Each skill must say what it won't."""
    for skill in BUILTIN_SKILLS:
        body = skill.body.lower()
        assert "password" in body, skill.name
        assert "use_computer" in body, skill.name
        # The escalation ladder keeps the slow, sensitive tool as a last resort.
        assert "escalation order" in body, skill.name


def test_builtins_are_not_scoped_to_a_person_or_persona() -> None:
    """These ship for everyone; scoping them would hide them from most turns."""
    for skill in BUILTIN_SKILLS:
        assert skill.person == "", skill.name
        assert skill.personas == [], skill.name
        assert skill.enabled is True, skill.name


# ---------------------------------------------------------------------------
# U253c: correcting a built-in the owner never touched
# ---------------------------------------------------------------------------


def _ai_skill() -> Skill:
    return next(s for s in BUILTIN_SKILLS if s.name == "desktop-ai-assistants")


def _with_new_body(monkeypatch, name: str, body: str) -> None:
    """Simulate the NEXT release shipping a corrected body for `name`."""
    import orchestrator.builtin_skills as bs

    patched = tuple(replace(s, body=body) if s.name == name else s
                    for s in bs.BUILTIN_SKILLS)
    monkeypatch.setattr(bs, "BUILTIN_SKILLS", patched)


def test_a_stale_untouched_builtin_is_corrected(tmp_path, monkeypatch) -> None:
    """The reported bug shipped inside a skill body, so a code fix alone
    could never reach the machines running it.

    `desktop-ai-assistants` told the model: "If the name is not in the
    allow-list, say so." The model said so — about an app that WAS in the
    list — without ever calling launch_app. Seeding is once-only by design,
    so every existing install would have kept that text forever.

    Untouched means OUR text, unchanged: safe to replace.
    """
    store = SkillStore(str(tmp_path))
    seed_builtin_skills(store)                       # ships the old text
    old_body = _stored(store).body

    _with_new_body(monkeypatch, "desktop-ai-assistants", "CALL the tool first.")
    seed_builtin_skills(store)                       # the next release boots

    assert _stored(store).body == "CALL the tool first."
    assert _stored(store).body != old_body


def test_an_owner_edited_builtin_is_still_never_corrected(tmp_path) -> None:
    """The correction must not become a licence to overwrite. Their text wins,
    stale or not — that is the whole point of the seeding rule."""
    store = SkillStore(str(tmp_path))
    seed_builtin_skills(store)

    mine = replace(_ai_skill(), body="Ask Claude the way I like it.")
    store.save(mine)
    seed_builtin_skills(store)
    assert _stored(store).body == "Ask Claude the way I like it."


def test_correcting_keeps_the_owners_switches(tmp_path, monkeypatch) -> None:
    """Only the procedure is ours. If they disabled it or scoped it to one
    person, a correction that silently re-enables it is a bug of its own."""
    store = SkillStore(str(tmp_path))
    seed_builtin_skills(store)

    store.save(replace(_stored(store), enabled=False, person="jan"))
    _with_new_body(monkeypatch, "desktop-ai-assistants", "corrected procedure")
    seed_builtin_skills(store)

    got = _stored(store)
    assert got.body == "corrected procedure"   # corrected
    assert got.enabled is False           # but still theirs
    assert got.person == "jan"


def test_the_updater_does_not_resurrect_a_deleted_builtin(tmp_path) -> None:
    """The correction pass walks the STORE, so a deleted skill is simply not
    there to correct — but the contract is worth its own test, because a
    future version that walked BUILTIN_SKILLS instead would quietly undo
    every deletion the owner ever made."""
    store = SkillStore(str(tmp_path))
    seed_builtin_skills(store)
    store.delete("desktop-ai-assistants")

    seed_builtin_skills(store)
    assert all(s.name != "desktop-ai-assistants" for s in store.all())


def _stored(store: SkillStore) -> Skill:
    return next(s for s in store.all() if s.name == "desktop-ai-assistants")
