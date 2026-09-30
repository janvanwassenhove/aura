"""An untried refusal is not an answer — U381.

Reported (translated): *"can you ask chatgpt to generate an image about richie
mini with a canoe on the river"* → *"I don't have that possibility, but I can
help with something else!"* The turn held one model call and nothing else. The
skill for exactly this request was bound, and `find_app`, `open_app`,
`type_into` and `use_computer` were offered. He had every way to find out and
tried none of them.

U380 made "never tell the owner something cannot be done before you have tried
it" a sentence no rewrite can remove from the skill. But a sentence in a skill
is a request to the model. This is the check behind it, built the way U248's
promise check is: it fires only on a turn where NOTHING ran, only when a skill
for this request is loaded (so the claim "I can't" contradicts something he was
told), only when tools were offered, and at most once — then the answer stands,
bad or not, so it can never become a loop.

It deliberately does not fire when no skill applies. Then "I can't" may simply
be true, and pushing back would teach him to promise instead.
"""

from __future__ import annotations

import re

# "I can't / I don't have that" in the first person, Dutch and English — the
# assistant answers in the language it is spoken to. Like promise.py this is a
# word list: each new phrasing that gets through is added here.
_REFUSALS = (
    r"\b(?:die|deze|dat|daar|de) mogelijkheid\b.{0,20}\b(?:heb|bezit) ik niet\b",
    r"\bheb ik (?:geen|niet de) (?:mogelijkheid|toegang|functie)",
    r"\bdaar heb ik geen mogelijkheid\b",
    r"\bik heb geen (?:toegang|mogelijkheid|functie)\b",
    r"\b(?:dat|dit|het) kan ik niet\b",
    r"\bkan ik (?:helaas )?(?:niet|geen)\b",
    r"\bik kan (?:helaas )?(?:dat |dit |het )?(?:niet|geen)\b",
    r"\b(?:dat|dit|het) lukt (?:me|mij) niet\b",
    r"\bis niet beschikbaar\b",
    r"\bniet mogelijk\b",
    r"\bi (?:can't|can not|cannot)\b",
    r"\bi don't have (?:the )?(?:ability|access|possibility|option|capability)\b",
    r"\bi do not have (?:the )?(?:ability|access|possibility|option|capability)\b",
    r"\bi(?:'m| am) (?:not able|unable)\b",
    r"\bisn't something i can\b",
    r"\bis not something i can\b",
    r"\bnot available\b",
)

_RX = [re.compile(p, re.I) for p in _REFUSALS]


def looks_like_a_refusal(reply: str) -> bool:
    """Does this reply tell the owner it cannot be done?"""
    if not reply or not reply.strip():
        return False
    return any(rx.search(reply) for rx in _RX)


def nudge(skill_names: list[str]) -> str:
    """The one pushback: which skill covers this, and how to find out."""
    names = ", ".join(dict.fromkeys(skill_names))
    return (
        f"You are telling the owner this cannot be done, and you have not tried "
        f"a single tool this turn — while the skill {names} describes how to do "
        "exactly this. That refusal describes a boundary nobody has checked. "
        "Investigate first: find_app says whether an app is installed, "
        "list_windows whether it is already open, list_browser_tabs whether it "
        "is open (and so probably logged in) in the browser. Then follow the "
        "skill. If a real tool result shows something is genuinely missing, ask "
        "the owner ONE concrete question that would unblock it (\"Are you logged "
        "in to ChatGPT in Chrome?\") or call request_capability — do not answer "
        "with \"I can't\" and a menu of alternatives."
    )
