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
import re
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

_LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")

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
{known_line}
Return ONLY the updated memory text (the bullets), no preamble.
"""

# U280: the link half. Asked as "kan hij vandaag al linken leggen tussen
# personas? bv. als ik praat als jan, over jappe, dan kan hij ook kennis
# opbouwen over jappe op dat ogenblik".
#
# He already REMEMBERED Jappe - "relationships" is in the keep-list above, so
# "Jan's son Jappe is 13" lands in Jan's memory. What he never did was CONNECT
# them: the graph turns [[name]] into a shared node, and a name it recognises
# as a person into a clickable person node, but the distiller had never been
# told that syntax exists. So two people the owner had both created sat in one
# household with nothing between them.
#
# Only names he ALREADY knows get linked. Inventing a profile for every name
# overheard in a conversation is a different decision with a different weight -
# especially for a child, whom this app deliberately never learns about
# passively (ADR-008 S10) - so that stays the owner's to make.
_KNOWN_LINE = """\
- Write the name of any PERSON the conversation is about as [[Name]] - family,
  friends, colleagues. These already have a profile: {names}; use exactly those
  spellings for them. Someone new gets [[Their Name]] too.
- Only real people, never places, teams, products or pets.
"""

# U281: without a profile the owner may not want, and without a duplicate.
#
# The owner authorised him to create profiles himself ("hij mag automatisch
# profiel maken (brain blijft lokaal binnen familie)"), with one condition:
# "indien persoon al bestaat ... moet hij link kunnen leggen gezien context of
# voorstellen". That condition is the whole difficulty. The model writes
# [[Jappe]]; the profile is `jappe`; a naive create would put a second Jappe
# beside the first and quietly split everything known about one child across
# two pages.
#
# So every link is RESOLVED before anything is written, and the three outcomes
# are deliberately different:
#   * resolves to exactly one known person  -> rewrite to their canonical id
#   * resolves to several (two Jans)        -> do NOT guess; drop the brackets
#     and leave the sentence as prose, so nothing is silently attached to the
#     wrong person
#   * resolves to nobody                    -> create the profile, flagged as
#     his doing, so the owner can always tell it from their own work
_MAX_NEW_PEOPLE = 3        # one odd reply must not spawn a household


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

    async def _memory_facts(self, person_id: str) -> list:
        """EVERY fact carrying the memory key — normally one.

        U278: the console's "Save memory" used to POST a NEW fact instead of
        replacing the note, so a store could end up with several. Both readers
        take the first, which is the OLDEST — so a correction was written,
        never shown, and never reached the model either. Returning them all is
        what lets a duplicated store heal itself on the next save.
        """
        return [f for f in await self._store.get_facts(person_id) if f.key == MEMORY_KEY]

    async def _current_memory_fact(self, person_id: str):
        facts = await self._memory_facts(person_id)
        # The LAST one is the most recently written — the one the owner meant.
        return facts[-1] if facts else None

    async def get_memory(self, person_id: str) -> str:
        fact = await self._current_memory_fact(person_id)
        return fact.value if fact else ""

    async def set_memory(self, person_id: str, text: str) -> None:
        from shared_schemas.knowledge import ProfileFact

        text = text.strip()[:_MAX_MEMORY_CHARS]
        # U278: delete ALL of them, not just the first. A store that already
        # collected duplicates is repaired by the next save rather than
        # accumulating another one.
        for old in await self._memory_facts(person_id):
            await self._store.delete_fact(str(old.fact_id))
        if text:
            await self._store.add_fact(ProfileFact(person_id=person_id, key=MEMORY_KEY, value=text))

    async def _known_people_line(self, speaker_id: str) -> str:
        """U280: the other people he already knows, so mentions become links.

        Everyone except the speaker (linking Jan's own page to itself says
        nothing) and except the demo profile, which is fiction and must never
        be woven into a real household.
        """
        try:
            people = await self._store.list_people()
        except Exception as exc:  # noqa: BLE001 - never break a distillation
            logger.debug("could not list people for linking: %s", exc)
            return ""
        names = [
            p.person_id for p in people
            if p.person_id != speaker_id
            and getattr(p.role, "value", p.role) != "demo"
        ]
        return _KNOWN_LINE.format(names=", ".join(sorted(names))) if names else ""

    # -- linking ---------------------------------------------------------

    @staticmethod
    def _slug(name: str) -> str:
        out = "".join(c if c.isalnum() else "-" for c in name.strip().lower())
        return re.sub(r"-+", "-", out).strip("-")[:48]

    async def _resolve_links(
        self, text: str, speaker_id: str,
    ) -> tuple[str, list[str], list[str]]:
        """Point every [[link]] at a real profile, creating one where needed.

        Returns the rewritten text, the ids he created, and the names he
        refused to guess at. See _MAX_NEW_PEOPLE above for why this exists.
        """
        from shared_schemas.knowledge import Person, PersonRole  # noqa: PLC0415

        names = {m.group(1).strip() for m in _LINK_RE.finditer(text)}
        names = {n for n in names if n}
        if not names:
            return text, [], []

        try:
            people = await self._store.list_people()
        except Exception as exc:  # noqa: BLE001 - never break a distillation
            logger.debug("could not list people for linking: %s", exc)
            return _LINK_RE.sub(r"\1", text), [], []

        by_id = {p.person_id.lower(): p.person_id for p in people}
        by_display: dict[str, list[str]] = {}
        by_first: dict[str, list[str]] = {}
        for p in people:
            if str(getattr(p.role, "value", p.role)) == "demo":
                continue          # fiction is never a link target
            by_display.setdefault(p.display_name.strip().lower(), []).append(p.person_id)
            first = p.display_name.strip().split()[0].lower() if p.display_name.strip() else ""
            if first:
                by_first.setdefault(first, []).append(p.person_id)

        mapping: dict[str, str] = {}
        created: list[str] = []
        ambiguous: list[str] = []
        for name in sorted(names):
            key = name.strip().lower()
            if key == speaker_id.lower():
                ambiguous.append(name)      # a page linking to itself says nothing
                continue
            hit = by_id.get(key)
            if hit is None:
                for table in (by_display, by_first):
                    found = table.get(key, [])
                    if len(found) == 1:
                        hit = found[0]
                        break
                    if len(found) > 1:
                        # Two people share this name. Guessing would attach a
                        # child's birthday to the wrong profile.
                        hit = None
                        ambiguous.append(name)
                        break
            if hit is not None:
                mapping[name] = hit
                continue
            if name in ambiguous:
                continue
            if len(created) >= _MAX_NEW_PEOPLE:
                ambiguous.append(name)
                continue
            new_id = self._slug(name)
            if not new_id or new_id in by_id:
                ambiguous.append(name)
                continue
            try:
                await self._store.upsert_person(Person(
                    person_id=new_id, display_name=name.strip(),
                    role=PersonRole.GUEST, auto_created=True))
            except Exception as exc:  # noqa: BLE001 - a profile is not worth a turn
                logger.debug("could not create %r: %s", new_id, exc)
                ambiguous.append(name)
                continue
            by_id[new_id] = new_id
            mapping[name] = new_id
            created.append(new_id)
            logger.info("U281: created profile %r from a conversation", new_id)

        def _rewrite(m):
            raw = m.group(1).strip()
            target = mapping.get(raw)
            # No target -> keep the words, drop the wiring. An unresolved
            # [[link]] on the canvas is a node pointing at nobody.
            return f"[[{target}]]" if target else raw

        return _LINK_RE.sub(_rewrite, text), created, ambiguous

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
            known_line=await self._known_people_line(person_id),
        )
        try:
            resp = await self._chat([{"role": "user", "content": prompt}], model=self._model_getter())
        except Exception as exc:  # noqa: BLE001 — offline / no key / quota
            logger.debug("memory distillation failed for %s: %s", person_id, exc)
            return None
        new_memory = (resp.get("content") or "").strip()
        if not new_memory or new_memory.startswith("[echo]"):
            return None
        new_memory, created, unresolved = await self._resolve_links(new_memory, person_id)
        await self.set_memory(person_id, new_memory)
        return {"person_id": person_id, "memory": new_memory[:_MAX_MEMORY_CHARS],
                "folded": len(exchanges),
                # U281: what he did to the household while distilling, so it is
                # reportable rather than something the owner discovers later.
                "created_people": created, "unresolved_names": unresolved}
