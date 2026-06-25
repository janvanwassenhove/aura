"""Personal Knowledge Layer (ADR-008) — models + store."""

from shared_schemas.knowledge.models import (
    ConsentRecord,
    ObservedSignal,
    Person,
    PersonRole,
    ProfileFact,
    RecognitionLink,
    Relationship,
)
from shared_schemas.knowledge.store import (
    ConsentError,
    InMemoryKnowledgeStore,
    KnowledgeStore,
)
from shared_schemas.knowledge.encrypted_store import EncryptedKnowledgeStore

__all__ = [
    "ConsentError",
    "ConsentRecord",
    "EncryptedKnowledgeStore",
    "InMemoryKnowledgeStore",
    "KnowledgeStore",
    "ObservedSignal",
    "Person",
    "PersonRole",
    "ProfileFact",
    "RecognitionLink",
    "Relationship",
]
