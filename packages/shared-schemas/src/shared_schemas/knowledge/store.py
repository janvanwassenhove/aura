"""KnowledgeStore — per-person store for the knowledge layer (ADR-008, U19a).

The interface is person-scoped and erasure-first. This module ships the ABC and a
plain in-memory implementation; the encrypted, per-person-keyed, owner-gated
persistence is layered on in U19b/U19c behind the SAME interface (mirroring how
MemoryStore stays abstract over SQLite/Postgres).

Security behaviours baked in here (storage-agnostic, so every backend inherits them):
  - **Per-person scoping**: facts/signals/etc. are always keyed by person_id;
    one person's data is never returned under another.
  - **Erasure**: delete_person removes the person AND all their facts, signals,
    relationships, consent, and recognition links (right-to-be-forgotten).
  - **Minors are explicit-only (ADR-008 §10)**: record_signal refuses passive
    (observed) learning for role=MINOR unless the owner granted explicit consent.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from shared_schemas.knowledge.models import (
    ConsentRecord,
    ObservedSignal,
    Person,
    PersonRole,
    ProfileFact,
    RecognitionLink,
    Relationship,
)

_OBSERVED_LEARNING = "observed_learning"


class ConsentError(PermissionError):
    """Raised when passive learning is attempted without required consent."""


async def ensure_minor_learning_consent(store: "KnowledgeStore", person_id: str) -> None:
    """ADR-008 §10: a minor's profile gets no passive (observed) learning unless
    the owner granted explicit consent. Shared by every store implementation.

    U160: role=DEMO is refused outright — the shipped demo profile is fictional
    and curated; letting real conversations drift into it would quietly corrupt
    the canned data every demo depends on (and hide real signals in a fake
    person). Explicit facts can still be edited by the owner."""
    person = await store.get_person(person_id)
    if person is None:
        return
    if person.role == PersonRole.DEMO:
        raise ConsentError(
            f"Passive learning disabled for demo profile {person_id!r} "
            "(curated sample data — edit its facts explicitly instead)."
        )
    if person.role == PersonRole.MINOR:
        if not await store.has_consent(person_id, _OBSERVED_LEARNING):
            raise ConsentError(
                f"Passive learning disabled for minor {person_id!r} "
                "(no observed_learning consent)."
            )


class KnowledgeStore(ABC):
    # --- people ---
    @abstractmethod
    async def upsert_person(self, person: Person) -> Person: ...
    @abstractmethod
    async def get_person(self, person_id: str) -> Person | None: ...
    @abstractmethod
    async def list_people(self) -> list[Person]: ...
    @abstractmethod
    async def delete_person(self, person_id: str) -> None:
        """Erase the person and ALL their data (right-to-be-forgotten)."""

    # --- explicit facts ---
    @abstractmethod
    async def add_fact(self, fact: ProfileFact) -> ProfileFact: ...
    @abstractmethod
    async def get_facts(self, person_id: str) -> list[ProfileFact]: ...
    @abstractmethod
    async def delete_fact(self, fact_id: str) -> None: ...

    # --- observed signals ---
    @abstractmethod
    async def record_signal(self, signal: ObservedSignal) -> ObservedSignal: ...
    @abstractmethod
    async def get_signals(self, person_id: str) -> list[ObservedSignal]: ...

    # --- relationships / consent / recognition ---
    @abstractmethod
    async def add_relationship(self, rel: Relationship) -> Relationship: ...
    @abstractmethod
    async def get_relationships(self, person_id: str) -> list[Relationship]: ...
    @abstractmethod
    async def set_consent(self, record: ConsentRecord) -> ConsentRecord: ...
    @abstractmethod
    async def has_consent(self, person_id: str, scope: str) -> bool: ...
    @abstractmethod
    async def link_recognition(self, link: RecognitionLink) -> RecognitionLink: ...
    @abstractmethod
    async def resolve_recognition(self, embedding_ref: str) -> str | None:
        """Return the person_id for an embedding ref, or None."""


class InMemoryKnowledgeStore(KnowledgeStore):
    """Non-persistent reference implementation (dev/tests; U19b adds encryption)."""

    def __init__(self) -> None:
        self._people: dict[str, Person] = {}
        self._facts: dict[str, list[ProfileFact]] = {}
        self._signals: dict[str, list[ObservedSignal]] = {}
        self._rels: dict[str, list[Relationship]] = {}
        self._consent: dict[tuple[str, str], ConsentRecord] = {}
        self._recognition: dict[str, str] = {}  # embedding_ref -> person_id

    async def upsert_person(self, person: Person) -> Person:
        self._people[person.person_id] = person
        return person

    async def get_person(self, person_id: str) -> Person | None:
        return self._people.get(person_id)

    async def list_people(self) -> list[Person]:
        return list(self._people.values())

    async def delete_person(self, person_id: str) -> None:
        self._people.pop(person_id, None)
        self._facts.pop(person_id, None)
        self._signals.pop(person_id, None)
        self._rels.pop(person_id, None)
        for key in [k for k in self._consent if k[0] == person_id]:
            self._consent.pop(key, None)
        for ref in [r for r, pid in self._recognition.items() if pid == person_id]:
            self._recognition.pop(ref, None)

    async def add_fact(self, fact: ProfileFact) -> ProfileFact:
        self._facts.setdefault(fact.person_id, []).append(fact)
        return fact

    async def get_facts(self, person_id: str) -> list[ProfileFact]:
        return list(self._facts.get(person_id, []))

    async def delete_fact(self, fact_id: str) -> None:
        for facts in self._facts.values():
            for f in list(facts):
                if str(f.fact_id) == str(fact_id):
                    facts.remove(f)

    async def record_signal(self, signal: ObservedSignal) -> ObservedSignal:
        await ensure_minor_learning_consent(self, signal.person_id)
        # Reinforce an existing signal of the same kind instead of duplicating.
        existing = next(
            (s for s in self._signals.get(signal.person_id, []) if s.kind == signal.kind),
            None,
        )
        if existing is not None:
            updated = existing.model_copy(update={
                "value": signal.value,
                "confidence": min(1.0, existing.confidence + 0.1),
                "evidence_count": existing.evidence_count + 1,
                "last_seen": signal.last_seen,
                "decay_at": signal.decay_at,
            })
            sigs = self._signals[signal.person_id]
            sigs[sigs.index(existing)] = updated
            return updated
        self._signals.setdefault(signal.person_id, []).append(signal)
        return signal

    async def get_signals(self, person_id: str) -> list[ObservedSignal]:
        return list(self._signals.get(person_id, []))

    async def add_relationship(self, rel: Relationship) -> Relationship:
        self._rels.setdefault(rel.from_person_id, []).append(rel)
        return rel

    async def get_relationships(self, person_id: str) -> list[Relationship]:
        return list(self._rels.get(person_id, []))

    async def set_consent(self, record: ConsentRecord) -> ConsentRecord:
        self._consent[(record.person_id, record.scope)] = record
        return record

    async def has_consent(self, person_id: str, scope: str) -> bool:
        rec = self._consent.get((person_id, scope))
        return rec is not None and rec.is_active

    async def link_recognition(self, link: RecognitionLink) -> RecognitionLink:
        self._recognition[link.embedding_ref] = link.person_id
        return link

    async def resolve_recognition(self, embedding_ref: str) -> str | None:
        return self._recognition.get(embedding_ref)
