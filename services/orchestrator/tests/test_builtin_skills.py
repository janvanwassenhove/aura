"""U194: the desktop skills that ship with the product."""

from __future__ import annotations

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
