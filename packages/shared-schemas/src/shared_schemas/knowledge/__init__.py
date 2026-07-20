"""Personal Knowledge Layer (ADR-008) — models + store."""

from shared_schemas.knowledge.encrypted_store import EncryptedKnowledgeStore
from shared_schemas.knowledge.judgment import JudgmentLayer, PersonContext
from shared_schemas.knowledge.models import (
    ConsentRecord,
    ObservedSignal,
    Person,
    PersonRole,
    ProfileFact,
    RecognitionLink,
    Relationship,
)
from shared_schemas.knowledge.recognition import EmbeddingMatcher
from shared_schemas.knowledge.store import (
    ConsentError,
    InMemoryKnowledgeStore,
    KnowledgeStore,
)

__all__ = [
    "ConsentError",
    "ConsentRecord",
    "EmbeddingMatcher",
    "EncryptedKnowledgeStore",
    "InMemoryKnowledgeStore",
    "JudgmentLayer",
    "KnowledgeStore",
    "ObservedSignal",
    "Person",
    "PersonContext",
    "PersonRole",
    "ProfileFact",
    "RecognitionLink",
    "Relationship",
]
