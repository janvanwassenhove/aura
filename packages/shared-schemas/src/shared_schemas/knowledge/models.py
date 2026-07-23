"""Personal Knowledge Layer — domain models ("geweten en kennisbank", ADR-008).

A per-person, evolving model of how the owner and family work/react. These are
the DURABLE entities; the judgment/anticipation layer (U19e) is stateless over
them. Encryption-at-rest + owner-gated access are layered on by the store
(U19b/U19c) — the models themselves are storage-agnostic.

SECURITY (ADR-008): this is special-category personal data. `RecognitionLink`
holds an opaque embedding *reference*, never the biometric embedding itself.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(UTC)


class PersonRole(StrEnum):
    OWNER = "owner"      # the device owner — full, sensitive-tier profile
    FAMILY = "family"    # known household member — own limited profile
    GUEST = "guest"      # recognised but minimal
    MINOR = "minor"      # child — explicit-only by default, no passive learning (ADR-008 §10)
    # U160: fictional, pre-filled profile that ships with the app so the owner
    # can demo the brain (profile, graph, skills) without exposing real people
    # or hand-typing data first. NOT a real person: it is never recognised from
    # a face, and nothing is ever passively learned into it.
    DEMO = "demo"


class Person(BaseModel):
    person_id: str                       # stable slug, e.g. "jan"
    display_name: str
    role: PersonRole = PersonRole.GUEST
    # Owner-written free-text portrait ("my partner; works in healthcare;
    # prefers short answers"). Part of the digital twin; encrypted at rest
    # like everything else. Optional -> old persisted data loads unchanged.
    description: str = ""
    # U204: a small avatar icon — a `data:image/...;base64,` URI, set from the
    # face-teach frame or chosen by the owner. Part of the person's encrypted
    # bundle like everything else; empty -> the console falls back to initials,
    # so old persisted data loads unchanged.
    avatar: str = ""
    created_at: datetime = Field(default_factory=_now)


class ProfileFact(BaseModel):
    """An EXPLICIT, owner-taught fact. Always inspectable and editable."""

    fact_id: UUID = Field(default_factory=uuid4)
    person_id: str
    key: str
    value: str
    source: Literal["explicit"] = "explicit"
    editable: bool = True
    created_at: datetime = Field(default_factory=_now)


class ObservedSignal(BaseModel):
    """A LEARNED preference/pattern distilled from interactions.

    Carries confidence + evidence and decays if not reinforced — the model
    forgets stale guesses instead of compounding them. Explicit facts outrank
    observed signals on conflict (resolved in the judgment layer).
    """

    signal_id: UUID = Field(default_factory=uuid4)
    person_id: str
    kind: str                            # e.g. "prefers_morning_deep_work"
    value: str
    confidence: float = 0.5              # 0..1
    evidence_count: int = 1
    last_seen: datetime = Field(default_factory=_now)
    decay_at: datetime | None = None
    source: Literal["observed"] = "observed"


class Relationship(BaseModel):
    from_person_id: str
    to_person_id: str
    kind: str                            # e.g. "partner", "child"


class ConsentRecord(BaseModel):
    """Consent for modelling a non-owner person, granted by the owner (ADR-008)."""

    person_id: str
    granted_by: str                      # owner person_id
    scope: str                           # e.g. "observed_learning"
    granted_at: datetime = Field(default_factory=_now)
    revoked_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


class RecognitionLink(BaseModel):
    """Maps a face identity (perception, U18) → person_id.

    Holds an OPAQUE reference to the embedding, never the embedding itself.
    """

    person_id: str
    embedding_ref: str
