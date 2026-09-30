"""U382: what he works out himself, he offers to keep.

The goal behind U381, in the owner's words (translated): *"he should go looking
for ways to do it."* U381 made him look. But a route he finds by looking —
find_app, then open_app, then type_into and Enter — lived for exactly one turn.
Every learning path AURA had started from somebody else:

* ``save_skill`` described itself as saving "a procedure the owner taught
  you", and the prompt said to propose one "when the owner corrects your
  approach or shows you their way of working". A route he found himself was
  neither, so he never offered it.
* The U250 draft for a request no skill covered was written from the owner's
  requests alone. The tools that actually worked in those attempts were
  recorded (``tools`` in ``_unmatched.jsonl``) and never shown to the drafting
  model, so it guessed at a procedure the log already held.
"""

from __future__ import annotations

import json

from orchestrator.skill_optimizer import propose_new_skill
from orchestrator.skills import Skill, SkillStore
from orchestrator.tool_schemas import build_tool_specs


def _save_skill_description() -> str:
    spec = next(s for s in build_tool_specs(["save_skill"])
                if (s.get("function") or s).get("name") == "save_skill")
    return (spec.get("function") or spec)["description"]


# ── in the turn: offer the route he found ──────────────────────────────────

def test_save_skill_is_also_for_a_route_he_found_himself() -> None:
    desc = _save_skill_description()
    assert "worked out yourself" in desc
    assert "steps that actually worked" in desc


def test_the_prompt_tells_him_to_offer_it(tmp_path) -> None:
    store = SkillStore(str(tmp_path))
    for block in (store.prompt_block("iets", "work", None),        # no skills yet
                  _with_one_skill(store).prompt_block("iets", "work", None)):
        assert "worked out yourself" in block, block[:200]


def test_only_what_no_skill_covered_and_only_once() -> None:
    """An offer after every turn would bury the owner in cards — the same
    failure as never asking. It is for a route that took real finding."""
    desc = _save_skill_description()
    assert "no skill covered" in desc
    assert "once" in desc


def _with_one_skill(store: SkillStore) -> SkillStore:
    store.save(Skill(name="demo", description="a demo", triggers=["demo"],
                     body="1. Do the demo."))
    return store


# ── later: the draft is built on what worked ───────────────────────────────

class _Store:
    def __init__(self, unmatched: list[dict]) -> None:
        self._unmatched = unmatched

    def all(self):
        return []

    def unmatched(self):
        return self._unmatched


async def _draft_prompt(unmatched: list[dict]) -> str:
    seen: list[str] = []

    async def chat(messages, model=None):
        seen.append(messages[0]["content"])
        return {"content": json.dumps({"worth_adding": False, "rationale": "-"})}

    await propose_new_skill(_Store(unmatched), [e["request"] for e in unmatched], chat)
    return seen[0]


async def test_the_draft_is_shown_the_tools_that_worked() -> None:
    prompt = await _draft_prompt([
        {"request": "vraag chatgpt een afbeelding te maken",
         "tools": ["find_app", "open_app", "send_keys", "type_into"], "unavailable": []},
    ])
    assert "worked" in prompt
    for tool in ("find_app", "open_app", "type_into", "send_keys"):
        assert tool in prompt, tool


async def test_tools_from_an_attempt_that_hit_a_wall_are_not_called_working() -> None:
    prompt = await _draft_prompt([
        {"request": "vraag chatgpt iets", "tools": ["use_computer"],
         "unavailable": ["screen control"]},
    ])
    worked = [line for line in prompt.splitlines() if "worked" in line]
    assert not any("use_computer" in line for line in worked)


async def test_with_nothing_that_worked_the_prompt_is_unchanged() -> None:
    prompt = await _draft_prompt([{"request": "hoe laat is het", "tools": [],
                                   "unavailable": []}])
    assert "worked" not in prompt
