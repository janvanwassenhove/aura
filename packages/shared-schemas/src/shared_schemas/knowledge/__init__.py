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

__all__ = [
    "ConsentError",
    "ConsentRecord",
    "InMemoryKnowledgeStore",
    "KnowledgeStore",
    "ObservedSignal",
    "Person",
    "PersonRole",
    "ProfileFact",
    "RecognitionLink",
    "Relationship",
]
