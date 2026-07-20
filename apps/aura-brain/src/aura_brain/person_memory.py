"""U109: long-term memory per person.

Conversations are ephemeral (U42 keeps only per-session history). This module
distills what matters across sessions into a durable, rolling MEMORY for each
recognized person — stored as a single ``memory`` fact in the encrypted store,
so it is encrypted at rest and automatically injected into future turns via the
judgment layer.

Flow: after each turn with a recognized person the pipeline hook calls
``PersonMemory.record(person_id, user, assistant)``. Exchanges buffer per
person; once ``every`` have accumulated (or ``flush`` is called), the chat model
folds them into the existing memory — keeping durable facts (projects, promises,
preferences, recurring themes), dropping small talk. The result replaces the
``memory`` fact. Bounded length keeps the graph and prompt lean.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

MEMORY_KEY = "memory"
_MAX_MEMORY_CHARS = 1400

_DISTILL_PROMPT = """\
You maintain a durable MEMORY of a person for a personal assistant — the things
worth remembering across conversations, not a transcript.

Person: {name}

Existing memory (may be empty):
{memory}

New conversation exchanges (most recent last):
{exchanges}

Update the memory:
- Keep durable facts: projects, goals, promises/commitments, strong preferences,
  relationships, recurring themes, unresolved threads to follow up.
- Drop pleasantries, one-off questions, and anything already captured.
- Merge — do not just append; revise stale points, keep it tight.
- A concise bullet list, at most ~10 bullets, {max_chars} characters max.
- Same language as the exchanges.

Return ONLY the updated memory text (the bullets), no preamble.
"""

ChatFn = Callable[..., Awaitable[dict]]


class PersonMemory:
    def __init__(
        self,
        store: Any,
        chat_fn: ChatFn,
        model_getter: Callable[[], str | None] | None = None,
        every: int = 4,
    ) -> None:
        self._store = store
        self._chat = chat_fn
        self._model_getter = model_getter or (lambda: None)
        self._every = max(1, every)
        self._buffers: dict[str, list[tuple[str, str]]] = {}

    # -- buffering -------------------------------------------------------

    async def record(self, person_id: str, user: str, assistant: str) -> None:
        """Buffer one exchange; distil once ``every`` have accumulated."""
        user, assistant = (user or "").strip(), (assistant or "").strip()
        if not user or not assistant or assistant.startswith("[echo]"):
            return
        buf = self._buffers.setdefault(person_id, [])
        buf.append((user, assistant))
        if len(buf) >= self._every:
            await self.flush(person_id)

    async def flush(self, person_id: str) -> dict | None:
        """Distil the buffered exchanges into the person's memory now."""
        buf = self._buffers.get(person_id) or []
        if not buf:
            return None
        self._buffers[person_id] = []
        return await self._distill(person_id, buf)

    # -- store helpers ---------------------------------------------------

    async def _current_memory_fact(self, person_id: str):
        for f in await self._store.get_facts(person_id):
            if f.key == MEMORY_KEY:
                return f
        return None

    async def get_memory(self, person_id: str) -> str:
        fact = await self._current_memory_fact(person_id)
        return fact.value if fact else ""

    async def set_memory(self, person_id: str, text: str) -> None:
        from shared_schemas.knowledge import ProfileFact

        text = text.strip()[:_MAX_MEMORY_CHARS]
        old = await self._current_memory_fact(person_id)
        if old is not None:
            await self._store.delete_fact(str(old.fact_id))
        if text:
            await self._store.add_fact(ProfileFact(person_id=person_id, key=MEMORY_KEY, value=text))

    # -- distillation ----------------------------------------------------

    async def _distill(self, person_id: str, exchanges: list[tuple[str, str]]) -> dict | None:
        person = await self._store.get_person(person_id)
        if person is None:
            return None
        current = await self.get_memory(person_id)
        convo = "\n".join(f"- They said: {u}\n  You replied: {a}" for u, a in exchanges)
        prompt = _DISTILL_PROMPT.format(
            name=person.display_name, memory=current or "(none yet)",
            exchanges=convo, max_chars=_MAX_MEMORY_CHARS,
        )
        try:
            resp = await self._chat([{"role": "user", "content": prompt}], model=self._model_getter())
        except Exception as exc:  # noqa: BLE001 — offline / no key / quota
            logger.debug("memory distillation failed for %s: %s", person_id, exc)
            return None
        new_memory = (resp.get("content") or "").strip()
        if not new_memory or new_memory.startswith("[echo]"):
            return None
        await self.set_memory(person_id, new_memory)
        return {"person_id": person_id, "memory": new_memory[:_MAX_MEMORY_CHARS],
                "folded": len(exchanges)}
