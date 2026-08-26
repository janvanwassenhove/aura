"""U263: does the deck on screen match the one this scenario was written for?

Two silent failures the owner asked to have surfaced, both of which only show
themselves in front of an audience:

  * **The wrong deck.** `pptx:` in a scenario was documentation and nothing
    more. Open last month's version and every `slide:N` beat fires on whatever
    happens to be at that number now.
  * **A shifted deck.** Insert one slide in the middle and every trigger after
    it points one place too early. Nothing anywhere notices.

Neither is worth BLOCKING a talk over — the presenter may well know exactly
what they are doing, and a co-presenter that refuses to start two minutes
before a keynote is worse than a wrong remark. So these are warnings, phrased
so the reader can decide in one glance, and they carry what was expected next
to what is actually there.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


def _normalise(name: str) -> str:
    """Compare decks the way a person would: by name, not by path or version.

    Drops the folder, the extension, case, and the trailing "(2)" / " v3" /
    " - kopie" that saving a copy leaves behind. Those differ constantly for
    what is plainly the same talk, and a warning that cries wolf gets ignored
    precisely when it is right.
    """
    stem = re.split(r"[\\\\/]", (name or "").strip())[-1]
    stem = re.sub(r"\.(pptx?|key|pdf)$", "", stem, flags=re.I)
    stem = re.sub(r"[\s_-]*(\(\d+\)|v\d+|copy|kopie|final|def)\s*$", "", stem, flags=re.I)
    return re.sub(r"[^a-z0-9]+", "", stem.lower())


@dataclass(frozen=True)
class DeckWarning:
    kind: str        # "wrong_deck" | "beats_past_end"
    message: str


def check(
    expected_deck: str,
    actual_deck: str,
    total_slides: int,
    slide_triggers: list[int],
) -> list[DeckWarning]:
    """Everything worth telling the presenter before they start talking."""
    out: list[DeckWarning] = []

    if expected_deck and actual_deck:
        if _normalise(expected_deck) != _normalise(actual_deck):
            out.append(DeckWarning(
                "wrong_deck",
                f"This scenario was written for “{expected_deck}”, but "
                f"“{actual_deck}” is on screen. Slide cues will fire on that "
                f"deck's numbering.",
            ))

    if total_slides and slide_triggers:
        past = sorted({n for n in slide_triggers if n > total_slides})
        if past:
            which = ", ".join(str(n) for n in past[:5])
            more = f" (+{len(past) - 5} more)" if len(past) > 5 else ""
            out.append(DeckWarning(
                "beats_past_end",
                f"The deck has {total_slides} slides, but cues point at slide "
                f"{which}{more}. Those beats can never fire — did the deck "
                f"change after the scenario was written?",
            ))

    return out


def slide_triggers(scenario) -> list[int]:  # noqa: ANN001 — Scenario, avoiding a cycle
    """The slide numbers a scenario waits for."""
    out: list[int] = []
    for beat in getattr(scenario, "beats", []) or []:
        trigger = str(getattr(beat, "trigger", "") or "")
        if trigger.startswith("slide:"):
            try:
                out.append(int(trigger.split(":", 1)[1]))
            except ValueError:
                continue
    return out
