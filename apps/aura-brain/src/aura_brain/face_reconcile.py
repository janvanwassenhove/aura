"""Keep the face matcher and the knowledge store telling the same story — U244.

The matcher had twelve faces enrolled; the store had four people. Ten of those
enrolments pointed at guest profiles that had been deleted months earlier, and
nothing ever removed the face when the person went.

That is worse than untidy, in two ways.

*It breaks recognition.* ``identify()`` returns the single best cosine match
over EVERY enrolled face. An orphan enrolled from the owner at an awkward angle
can outscore the owner's own samples; the pipeline is then handed an id that
resolves to nobody, the judgment layer returns ``None``, and the assistant talks
to someone it has no context for — while the console still shows the last name
it saw.

*It breaks erasure.* Deleting a person is meant to be ADR-008 §9 erasure. A face
embedding is biometric data; leaving it behind, still decryptable under the
owner key, means "forget this person" quietly kept the most personal thing about
them.

So: the delete path forgets the face too (the leak), and startup reconciles what
the leak already produced (the mess).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def find_orphans(matcher: Any, store: Any) -> list[str]:
    """Enrolled face ids with no person behind them any more.

    Never treats an EMPTY store as "everybody was deleted". A store with no
    people is far more likely to be one that has not finished loading — and the
    cost of being wrong is every face in the house, unrecoverably.
    """
    people = {p.person_id for p in await store.list_people()}
    if not people:
        logger.debug("skipping face reconciliation: the store lists no people")
        return []
    return [pid for pid in matcher.enrolled_ids() if pid not in people]


async def reconcile(matcher: Any, store: Any) -> list[str]:
    """Drop orphaned enrolments. Returns the ids that were dropped."""
    orphans = await find_orphans(matcher, store)
    for person_id in orphans:
        matcher.forget(person_id)
    if orphans:
        logger.info(
            "face reconciliation: dropped %d enrolment(s) with no profile (%s)",
            len(orphans), ", ".join(orphans),
        )
    return orphans
