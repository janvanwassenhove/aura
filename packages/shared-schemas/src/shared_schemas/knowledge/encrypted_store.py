"""EncryptedKnowledgeStore — per-person encrypted-at-rest store (ADR-008 §3/§4).

Each person's records live as ONE AES-256-GCM ciphertext bundle, encrypted under a
per-person DEK that is wrapped by the Owner Master Key (OMK). The at-rest bytes
are always ciphertext; plaintext exists only transiently in memory during an
operation. Deleting a person destroys their DEK + blob → cryptographic erasure.

Same `KnowledgeStore` interface as the in-memory store, so the brain can swap it
in transparently. Persistence of the ciphertext (to disk) is a thin layer over the
`_blobs`/`_wrapped_deks` maps and is left to the caller / a later unit; the crypto
boundary is what matters here.
"""

from __future__ import annotations

import json

from shared_schemas.knowledge import crypto
from shared_schemas.knowledge.models import (
    ConsentRecord,
    ObservedSignal,
    Person,
    ProfileFact,
    RecognitionLink,
    Relationship,
)
from shared_schemas.knowledge.store import KnowledgeStore, ensure_minor_learning_consent


class EncryptedKnowledgeStore(KnowledgeStore):
    def __init__(self, omk: bytes) -> None:
        if len(omk) != 32:
            raise ValueError("OMK must be 32 bytes (AES-256).")
        self._omk = omk
        self._wrapped_deks: dict[str, bytes] = {}
        self._blobs: dict[str, bytes] = {}  # person_id -> AES-GCM ciphertext bundle

    # ------------------------------------------------------------------
    # Bundle load/save (the only place plaintext exists, transiently)
    # ------------------------------------------------------------------

    def _empty(self) -> dict:
        return {"person": None, "facts": [], "signals": [], "rels": [],
                "consent": {}, "recognition": []}

    def _load(self, person_id: str) -> dict:
        blob = self._blobs.get(person_id)
        if blob is None:
            return self._empty()
        dek = crypto.unwrap_dek(self._wrapped_deks[person_id], self._omk)
        return json.loads(crypto.decrypt(dek, blob, aad=person_id.encode()))

    def _save(self, person_id: str, bundle: dict) -> None:
        wrapped = self._wrapped_deks.get(person_id)
        if wrapped is None:
            dek = crypto.generate_key()
            self._wrapped_deks[person_id] = crypto.wrap_dek(dek, self._omk)
        else:
            dek = crypto.unwrap_dek(wrapped, self._omk)
        self._blobs[person_id] = crypto.encrypt(
            dek, json.dumps(bundle).encode(), aad=person_id.encode()
        )

    # ------------------------------------------------------------------
    # People
    # ------------------------------------------------------------------

    async def upsert_person(self, person: Person) -> Person:
        bundle = self._load(person.person_id)
        bundle["person"] = person.model_dump(mode="json")
        self._save(person.person_id, bundle)
        return person

    async def get_person(self, person_id: str) -> Person | None:
        data = self._load(person_id).get("person")
        return Person.model_validate(data) if data else None

    async def list_people(self) -> list[Person]:
        out: list[Person] = []
        for pid in self._blobs:
            p = await self.get_person(pid)
            if p is not None:
                out.append(p)
        return out

    async def delete_person(self, person_id: str) -> None:
        # Destroy the wrapped DEK and ciphertext → data is unrecoverable.
        self._wrapped_deks.pop(person_id, None)
        self._blobs.pop(person_id, None)

    # ------------------------------------------------------------------
    # Facts
    # ------------------------------------------------------------------

    async def add_fact(self, fact: ProfileFact) -> ProfileFact:
        bundle = self._load(fact.person_id)
        bundle["facts"].append(fact.model_dump(mode="json"))
        self._save(fact.person_id, bundle)
        return fact

    async def get_facts(self, person_id: str) -> list[ProfileFact]:
        return [ProfileFact.model_validate(f) for f in self._load(person_id)["facts"]]

    async def delete_fact(self, fact_id: str) -> None:
        for pid in self._blobs:
            bundle = self._load(pid)
            kept = [f for f in bundle["facts"] if str(f["fact_id"]) != str(fact_id)]
            if len(kept) != len(bundle["facts"]):
                bundle["facts"] = kept
                self._save(pid, bundle)

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    async def record_signal(self, signal: ObservedSignal) -> ObservedSignal:
        await ensure_minor_learning_consent(self, signal.person_id)
        bundle = self._load(signal.person_id)
        existing = next((s for s in bundle["signals"] if s["kind"] == signal.kind), None)
        if existing is not None:
            existing.update({
                "value": signal.value,
                "confidence": min(1.0, existing["confidence"] + 0.1),
                "evidence_count": existing["evidence_count"] + 1,
                "last_seen": signal.last_seen.isoformat(),
                "decay_at": signal.decay_at.isoformat() if signal.decay_at else None,
            })
            result = ObservedSignal.model_validate(existing)
        else:
            bundle["signals"].append(signal.model_dump(mode="json"))
            result = signal
        self._save(signal.person_id, bundle)
        return result

    async def get_signals(self, person_id: str) -> list[ObservedSignal]:
        return [ObservedSignal.model_validate(s) for s in self._load(person_id)["signals"]]

    # ------------------------------------------------------------------
    # Relationships / consent / recognition
    # ------------------------------------------------------------------

    async def add_relationship(self, rel: Relationship) -> Relationship:
        bundle = self._load(rel.from_person_id)
        bundle["rels"].append(rel.model_dump(mode="json"))
        self._save(rel.from_person_id, bundle)
        return rel

    async def get_relationships(self, person_id: str) -> list[Relationship]:
        return [Relationship.model_validate(r) for r in self._load(person_id)["rels"]]

    async def set_consent(self, record: ConsentRecord) -> ConsentRecord:
        bundle = self._load(record.person_id)
        bundle["consent"][record.scope] = record.model_dump(mode="json")
        self._save(record.person_id, bundle)
        return record

    async def has_consent(self, person_id: str, scope: str) -> bool:
        rec = self._load(person_id)["consent"].get(scope)
        return rec is not None and rec.get("revoked_at") is None

    async def link_recognition(self, link: RecognitionLink) -> RecognitionLink:
        bundle = self._load(link.person_id)
        if link.embedding_ref not in bundle["recognition"]:
            bundle["recognition"].append(link.embedding_ref)
        self._save(link.person_id, bundle)
        return link

    async def resolve_recognition(self, embedding_ref: str) -> str | None:
        for pid in self._blobs:
            if embedding_ref in self._load(pid)["recognition"]:
                return pid
        return None
