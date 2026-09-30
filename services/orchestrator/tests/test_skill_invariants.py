"""U380: a guardrail that a rewrite cannot remove.

Reported with a screenshot (translated): *"can you ask chatgpt to generate an
image about richie mini with a canoe on the river"* → *"I don't have that
possibility, but I can help with something else."* And the goal, stated right
after: *"he should go looking for ways to do it — check whether ChatGPT is
installed, or ask whether there is an account (logged in to Chrome?)."*

Measured before touching anything, and every link is evidence, not inference:

* The brain log for that turn holds **one** model call and nothing else — no
  tool, no approval, no skill observation beyond the match.
* Replaying the sentence against the installed 2.0.183 code: the skill
  `desktop-ai-assistants` **was** bound, and `open_app`, `type_into` and
  `use_computer` **were** offered.
* The owner's copy of that skill is not any version AURA ever shipped — it is
  a Dutch rewrite, and `.metrics/desktop-ai-assistants.optimized` was written
  at 23:12 the night before: the U107 self-optimizing loop proposed it and the
  proposal was approved. The loop's prompt says "same language as the current
  body"; it translated anyway. And it dropped the one sentence the skill
  existed for — *"ALWAYS call it … Do not tell the owner an app is unavailable
  unless a real launch_app result said so"* — replacing it with *"if the app
  is not on the allow-list, say so and point at Capabilities"*. He did exactly
  that.
* Once rewritten, the copy counts as the owner's: the seeder rightly leaves
  edited skills alone, so every later fix to the built-in (U377, U378) never
  reached it.
* The "usage evidence" the loop optimized on includes *"Hier ist auch die
  Riese ChatGPT."* and *"ChatGPT, my name is"* — the television, heard as
  commands.

So a better skill text alone would have lasted until the next optimization.
Built-in skills now carry **invariants**: sentences a rewrite may reword
around but may not remove. The optimizer restores any it dropped and says so;
on start, an edited copy that is missing one gets it back, and the rest of the
edit stays exactly as the owner approved it.
"""

from __future__ import annotations

import pytest
from orchestrator import builtin_skills, skill_optimizer
from orchestrator.builtin_skills import BUILTIN_SKILLS, INVARIANTS, restore_invariants
from orchestrator.skills import Skill, SkillStore

# The owner's copy, first lines verbatim: the rewrite that removed the rule.
DUTCH_REWRITE = (
    "Gebruik een andere AI-assistent die al op het bureaublad is geïnstalleerd.\n\n"
    "1. Kies eerst de juiste app: launch_app('claude') of launch_app('chatgpt'). "
    "Staat de gevraagde app niet op de allow-list, zeg dat dan en verwijs naar "
    "Capabilities.\n"
    "2. Wacht tot het venster volledig geopend is. Klik daarna in het berichtveld, "
    "typ de vraag van de eigenaar exact zoals gegeven en druk op Enter.\n"
)


# ── the invariants themselves ──────────────────────────────────────────────

def test_every_built_in_ships_its_own_invariants() -> None:
    """Defined once, embedded in the body by construction — so the definition
    and the text can never drift apart."""
    for skill in BUILTIN_SKILLS:
        for sentence in INVARIANTS.get(skill.name, ()):
            assert sentence in skill.body, (skill.name, sentence[:60])


def test_the_ai_assistant_skill_forbids_an_untried_refusal() -> None:
    rules = " ".join(INVARIANTS["desktop-ai-assistants"]).lower()
    assert "never tell the owner" in rules and "tried" in rules


def test_restoring_is_idempotent_and_keeps_the_edit() -> None:
    body, restored = restore_invariants("desktop-ai-assistants", DUTCH_REWRITE)
    assert restored, "the rule the rewrite dropped must come back"
    assert body.startswith(DUTCH_REWRITE.rstrip()), "the owner's text must stay as it was"
    again, restored_again = restore_invariants("desktop-ai-assistants", body)
    assert again == body and restored_again == [], "restoring twice must not duplicate"


def test_a_skill_without_invariants_is_never_touched() -> None:
    body, restored = restore_invariants("the-owners-own-skill", "whatever they wrote")
    assert body == "whatever they wrote" and restored == []


# ── the optimizer cannot remove them ───────────────────────────────────────

class _Store:
    def __init__(self, body: str) -> None:
        self._skill = Skill(name="desktop-ai-assistants", description="ask another AI",
                            triggers=["chatgpt"], body=body)

    def get(self, name):
        return self._skill if name == self._skill.name else None

    def observations(self, name):
        return [{"request": "Hier ist auch die Riese ChatGPT."}]


async def test_an_optimization_that_drops_a_guardrail_gets_it_back() -> None:
    """The exact thing that happened at 23:12, as a test."""
    builtin = next(s for s in BUILTIN_SKILLS if s.name == "desktop-ai-assistants")

    async def chat(messages, model=None):
        import json
        return {"content": json.dumps({"changed": True, "rationale": "tightened",
                                       "body": DUTCH_REWRITE})}

    out = await skill_optimizer.propose_optimization(_Store(builtin.body),
                                                     "desktop-ai-assistants", chat)
    for sentence in INVARIANTS["desktop-ai-assistants"]:
        assert sentence in out["proposed_body"], "the proposal still drops the rule"
    assert "kept" in out["rationale"].lower(), "the owner must be told what was put back"


# ── and on start, an edited copy is repaired, not replaced ─────────────────

@pytest.fixture()
def store(tmp_path):
    return SkillStore(str(tmp_path))


def test_the_owners_rewritten_copy_gets_its_guardrail_back_on_start(store) -> None:
    builtin_skills.seed_builtin_skills(store)                     # first boot
    edited = store.get("desktop-ai-assistants")
    store.save(Skill(name=edited.name, description=edited.description,
                     triggers=edited.triggers, body=DUTCH_REWRITE, enabled=edited.enabled))

    builtin_skills.seed_builtin_skills(store)                     # the next start

    after = store.get("desktop-ai-assistants").body
    assert after.startswith(DUTCH_REWRITE.rstrip()), "the approved rewrite must stay"
    for sentence in INVARIANTS["desktop-ai-assistants"]:
        assert sentence in after


def test_an_edited_copy_that_still_has_its_guardrails_is_left_exactly_alone(store) -> None:
    builtin_skills.seed_builtin_skills(store)
    edited = store.get("desktop-ai-assistants")
    mine = edited.body + "\n\nMy own extra step: always greet ChatGPT politely."
    store.save(Skill(name=edited.name, description=edited.description,
                     triggers=edited.triggers, body=mine, enabled=edited.enabled))

    builtin_skills.seed_builtin_skills(store)
    assert store.get("desktop-ai-assistants").body.strip() == mine.strip()


def test_repairing_twice_does_not_grow_the_skill(store) -> None:
    builtin_skills.seed_builtin_skills(store)
    edited = store.get("desktop-ai-assistants")
    store.save(Skill(name=edited.name, description=edited.description,
                     triggers=edited.triggers, body=DUTCH_REWRITE, enabled=edited.enabled))
    builtin_skills.seed_builtin_skills(store)
    once = store.get("desktop-ai-assistants").body
    builtin_skills.seed_builtin_skills(store)
    assert store.get("desktop-ai-assistants").body == once
