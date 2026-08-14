"""A promise is not an answer — U248.

Reported: "zoek het op in google in chrome" → *"Ik ga nu Chrome openen en een
zoekopdracht voor je uitvoeren. Even geduld, alsjeblieft!"* — one second later,
and nothing happened. No tool ran. The turn ended on an announcement.

The pipeline had no defence: a model reply with no tool calls ends the loop and
becomes the spoken answer, whatever it says. So the assistant could describe
work it had not done and the system would agree with it.

That is the mirror image of the failure this project keeps running into. Silent
failure is bad; ANNOUNCED success that never happened is worse, because the
owner walks away believing something is underway.

Detection is deliberately narrow. It fires only on a turn where NOTHING ran, so
a reply that describes work actually done can never trip it, and the phrases
are the ones that state an imminent action in the first person — not ordinary
offers ("zal ik…?", "wil je dat ik…?"), which are exactly the right thing to
say when it cannot do something.
"""

from __future__ import annotations

import re

# First person, present or immediate future, about to act. Dutch and English:
# the assistant answers in the language it is spoken to, so both must be here.
_PROMISES = (
    r"\bik ga (nu )?\w+",              # ik ga nu Chrome openen
    r"\bik zal (nu |even )?\w+en\b",   # ik zal even kijken
    r"\bik open (nu |even )",
    r"\bik zoek (het |dat )?(nu |even )",
    r"\bik start (nu |even )",
    r"\beven geduld",
    r"\bmomentje\b",
    r"\bogenblikje\b",
    r"\bi(?:'| a)?m going to \w+",
    r"\bi(?:'| wi)ll (now |just )?\w+",
    r"\bi(?:'| a)?m (now )?(opening|searching|starting|launching)\b",
    r"\bone moment\b",
    r"\bhang on\b",
    r"\bgive me a (second|moment)\b",
)

# A question is an offer, not a claim. "Zal ik Chrome openen?" is the honest
# answer when it cannot act, and must never be treated as a broken promise.
_OFFERS = (
    r"\bzal ik\b", r"\bwil je dat ik\b", r"\bwould you like me to\b",
    r"\bshall i\b", r"\bdo you want me to\b",
)

_RX = [re.compile(p, re.I) for p in _PROMISES]
_OFFER_RX = [re.compile(p, re.I) for p in _OFFERS]


def looks_like_a_promise(reply: str) -> bool:
    """Does this reply claim an action is about to happen?"""
    if not reply or not reply.strip():
        return False
    text = reply.strip()
    if any(rx.search(text) for rx in _OFFER_RX):
        return False
    return any(rx.search(text) for rx in _RX)


NUDGE = (
    "You just told the owner you were about to do something, and you have not "
    "called a single tool this turn — so nothing is happening and they are "
    "waiting. Do it NOW with the tools you have. If you cannot: say plainly "
    "that you cannot, name exactly what is missing, and propose the smallest "
    "concrete change that would let you do it next time. Never describe work "
    "you have not done."
)
