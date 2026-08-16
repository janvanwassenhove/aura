"""Where a raised proposal waits for the owner — U251.

U250 made the assistant bring a skill up by itself, and published it on the
event bus. That is fine for a console that happens to be open and useless for
one that is not: the maintenance tick runs every five minutes, all day, and the
owner looks at the app for ten minutes in the evening. Every proposal raised in
between existed for a few milliseconds and was gone.

So they wait here. A small in-memory inbox, deliberately not a database:

  * it holds a handful of open questions, not a history,
  * losing it on restart is correct — the tick will raise anything still true,
  * and nothing here is the owner's data, only drafts about their procedures.

Answering is the point. A proposal leaves the inbox when it is applied or
dismissed, and a subject that already has one waiting is never queued twice —
two cards asking the same question is how an owner learns to ignore both.
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

_MAX_OPEN = 5   # more than a handful of open questions is a backlog, not a nudge


class ProposalInbox:
    def __init__(self, max_open: int = _MAX_OPEN) -> None:
        self._open: list[dict] = []
        self._max = max_open
        self._seq = 0

    def add(self, proposal: dict) -> dict:
        """File a raised proposal. Returns it with an id attached."""
        key = self._key(proposal)
        for existing in self._open:
            if self._key(existing) == key:
                # Same question, newer draft: replace rather than pile up.
                existing.update(proposal, id=existing["id"], raised_at=time.time())
                return existing
        self._seq += 1
        entry = dict(proposal, id=f"p{self._seq}", raised_at=time.time())
        self._open.append(entry)
        # Oldest first out: an unanswered question from this morning matters
        # less than the one raised a minute ago.
        del self._open[:-self._max]
        return entry

    def all(self) -> list[dict]:
        return list(self._open)

    def get(self, proposal_id: str) -> dict | None:
        return next((p for p in self._open if p["id"] == proposal_id), None)

    def resolve(self, proposal_id: str) -> bool:
        """Applied or dismissed — either way it stops being a question."""
        before = len(self._open)
        self._open = [p for p in self._open if p["id"] != proposal_id]
        return len(self._open) != before

    def has(self, kind: str, skill: str) -> bool:
        return any(p["kind"] == kind and p["skill"] == skill for p in self._open)

    @staticmethod
    def _key(proposal: dict) -> tuple[str, str]:
        return (str(proposal.get("kind", "")), str(proposal.get("skill", "")))


# One per process, like the other module-level singletons in this app.
INBOX = ProposalInbox()


def file(proposal: dict) -> dict:
    return INBOX.add(proposal)


def open_proposals() -> list[dict]:
    return INBOX.all()


def resolve(proposal_id: str) -> bool:
    return INBOX.resolve(proposal_id)


def waiting_for(kind: str, skill: str) -> bool:
    """Is this subject already on the owner's plate? Asked before raising, so
    a tick every five minutes cannot file the same question twelve times."""
    try:
        return INBOX.has(kind, skill)
    except Exception as exc:  # noqa: BLE001 — never break a tick
        logger.debug("inbox check failed: %s", exc)
        return False


def _reset_for_tests() -> None:
    global INBOX
    INBOX = ProposalInbox()
