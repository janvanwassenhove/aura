"""When should the assistant bring a skill up by itself? — U250.

U107 could already propose a rewrite; U247 gave it real evidence to rewrite
FROM; U249 made the trigger notice failure instead of popularity. What was
still missing is the smallest part and the one the owner actually asked for:
nobody ever looked. The proposal waited behind a button, so a skill could die
at the same step every day and the loop would never say a word.

This module is the deciding, kept away from the doing. Pure functions on
counts, so "does this deserve the owner's attention" can be tested without a
model, a clock or a console.

Two kinds of proposal come out of it:

  * REWRITE — a skill exists and keeps going wrong.
  * NEW — the same thing is asked for again and again and no skill covers it.

Neither ever writes. The owner approves both, as with every other skill write
since U59.
"""

from __future__ import annotations

import os
import re
import time
from collections import Counter
from dataclasses import dataclass


def _int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default


def blocked_threshold() -> int:
    return _int_env("SKILL_BLOCKED_THRESHOLD", 2)


def use_threshold() -> int:
    return _int_env("SKILL_OPTIMIZE_THRESHOLD", 8)


def unmatched_threshold() -> int:
    """How often the same kind of request must go uncovered before it is worth
    proposing a procedure for it. Low, but not one: a single odd question is
    not a habit."""
    return _int_env("SKILL_NEW_THRESHOLD", 3)


def review_cooldown_s() -> float:
    """A tick runs every five minutes. Without this the same skill would be
    raised twelve times an hour, which is how a useful signal becomes noise the
    owner learns to ignore."""
    try:
        return float(os.environ.get("SKILL_REVIEW_COOLDOWN_S", 86_400))
    except (TypeError, ValueError):
        return 86_400.0


@dataclass(frozen=True)
class Review:
    """One thing worth raising, and why in the owner's terms."""

    kind: str          # "rewrite" | "new"
    name: str          # skill name, or the proposed topic for a new one
    reason: str
    urgency: int       # higher first; failures outrank volume
    # For a NEW skill: the owner's own requests that went uncovered. The draft
    # is written from these, so the procedure describes what they actually ask
    # for rather than what the topic word suggests.
    examples: tuple[str, ...] = ()


def reason_to_review(metrics: dict) -> Review | None:
    """Does this skill's recent record deserve the owner's attention?"""
    blocked = int(metrics.get("blocked") or 0)
    missing = metrics.get("missing") or {}
    recent = int(metrics.get("recent") or 0)
    new_uses = int(metrics.get("new_since_optimized") or 0)
    name = str(metrics.get("name") or "")

    if blocked >= blocked_threshold():
        caps = ", ".join(sorted(missing)) or "something it needs"
        return Review(
            kind="rewrite", name=name,
            reason=(f"stopped {blocked} of the last {recent} times because "
                    f"{caps} was not available"),
            # A skill that fails is worth more attention than one that is
            # merely popular, and one that fails MORE is worth more again.
            urgency=1000 + blocked,
        )
    if new_uses >= use_threshold():
        return Review(
            kind="rewrite", name=name,
            reason=f"{new_uses} new uses since the last rewrite",
            urgency=new_uses,
        )
    return None


_WORD = re.compile(r"[a-zà-ÿ0-9]{4,}", re.I)

# Words that carry no topic. Deliberately short — an over-eager stop list makes
# every request look like every other one, and then the clustering below finds
# "patterns" that are really just Dutch grammar.
_STOP = {
    "kan", "kun", "kunt", "kunnen", "wil", "wilt", "willen", "even", "eens",
    "graag", "alsjeblieft", "please", "could", "would", "should", "have",
    "want", "need", "make", "your", "with", "that", "this", "from", "voor",
    "naar", "over", "maar", "ook", "niet", "geen", "waar", "wanneer", "hoe",
}


def _topic_words(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text or "")} - _STOP


def repeated_topic(unmatched: list[dict], threshold: int | None = None) -> Review | None:
    """A subject that keeps coming up with no skill behind it.

    Clustering is deliberately crude — shared content words, counted. Anything
    cleverer would be a similarity model whose mistakes nobody could explain,
    and the output here is a SUGGESTION a human reads, not a decision.
    """
    need = threshold or unmatched_threshold()
    if len(unmatched) < need:
        return None
    counts: Counter[str] = Counter()
    for entry in unmatched:
        # sorted(): _topic_words returns a SET, and set iteration order for
        # strings varies per process (hash randomisation). Feeding that to a
        # Counter made most_common() pick a different winner on different
        # runs when two words tied — a proposal generator that says "hockey"
        # today and "geven" tomorrow, for the same input. Caught by the suite
        # only because a tie happened to exist.
        counts.update(sorted(_topic_words(str(entry.get("request", "")))))
    if not counts:
        return None
    # Ties broken by length, then alphabetically: deterministic, and a longer
    # word is usually the subject rather than the verb around it. Crude, and
    # the output is a suggestion a human reads, not a decision.
    word, hits = max(counts.items(), key=lambda kv: (kv[1], len(kv[0]), kv[0]))
    if hits < need:
        return None
    examples = [str(e.get("request", "")) for e in unmatched
                if word in _topic_words(str(e.get("request", "")))]
    return Review(
        kind="new", name=word,
        reason=(f"asked about \"{word}\" {hits} times with no skill covering it"),
        urgency=hits,
        examples=tuple(examples[-12:]),
    )


def pick(store, *, now: float | None = None, last_raised: dict | None = None) -> Review | None:
    """The single most useful thing to raise right now, or None.

    One at a time on purpose. A list of five proposals is a backlog; one, with
    a reason, is a question the owner can answer.
    """
    now = time.time() if now is None else now
    seen = last_raised or {}
    cooldown = review_cooldown_s()
    candidates: list[Review] = []

    for skill in store.all():
        metrics = dict(store.metrics(skill.name))
        metrics["name"] = skill.name
        review = reason_to_review(metrics)
        if review is not None:
            candidates.append(review)

    topic = repeated_topic(store.unmatched())
    if topic is not None:
        candidates.append(topic)

    fresh = [c for c in candidates
             if now - float(seen.get(f"{c.kind}:{c.name}", 0)) >= cooldown]
    if not fresh:
        return None
    fresh.sort(key=lambda c: -c.urgency)
    return fresh[0]
