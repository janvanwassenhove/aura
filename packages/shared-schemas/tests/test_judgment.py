"""Tests for the judgment/anticipation layer (U19e, ADR-008 §1)."""

from __future__ import annotations

import pytest
from shared_schemas.knowledge.judgment import JudgmentLayer
from shared_schemas.knowledge.models import (
    ObservedSignal,
    Person,
    PersonRole,
    ProfileFact,
)
from shared_schemas.knowledge.store import InMemoryKnowledgeStore


@pytest.fixture
def store() -> InMemoryKnowledgeStore:
    return InMemoryKnowledgeStore()


@pytest.fixture
def judgment(store: InMemoryKnowledgeStore) -> JudgmentLayer:
    return JudgmentLayer(store, max_facts=4, signal_threshold=0.55)


# ---------------------------------------------------------------------------
# None / unknown person
# ---------------------------------------------------------------------------


async def test_none_person_id_returns_none(judgment: JudgmentLayer) -> None:
    assert await judgment.build_context(None) is None


async def test_unknown_person_id_returns_none(judgment: JudgmentLayer) -> None:
    assert await judgment.build_context("ghost") is None


# ---------------------------------------------------------------------------
# Guest — greeting name only
# ---------------------------------------------------------------------------


async def test_guest_returns_context_without_facts_or_signals(
    store: InMemoryKnowledgeStore, judgment: JudgmentLayer
) -> None:
    await store.upsert_person(Person(person_id="visitor", display_name="Visitor", role=PersonRole.GUEST))
    await store.add_fact(ProfileFact(person_id="visitor", key="job", value="unknown"))

    ctx = await judgment.build_context("visitor")
    assert ctx is not None
    assert ctx.person.role == PersonRole.GUEST
    assert ctx.facts == []
    assert ctx.signals == []


async def test_guest_system_note_contains_name(
    store: InMemoryKnowledgeStore, judgment: JudgmentLayer
) -> None:
    await store.upsert_person(Person(person_id="v", display_name="Alice", role=PersonRole.GUEST))
    ctx = await judgment.build_context("v")
    assert ctx is not None
    note = ctx.to_system_note()
    assert "Alice" in note
    assert "guest" in note


async def test_memory_fact_is_labelled_and_leads(
    store: InMemoryKnowledgeStore, judgment: JudgmentLayer
) -> None:
    """U109: the long-term `memory` fact renders distinctly, before plain facts."""
    from shared_schemas.knowledge import ProfileFact

    await store.upsert_person(Person(person_id="jan", display_name="Jan", role=PersonRole.OWNER))
    await store.add_fact(ProfileFact(person_id="jan", key="tone", value="concise"))
    await store.add_fact(ProfileFact(person_id="jan", key="memory", value="- Builds a robot"))
    ctx = await judgment.build_context("jan")
    note = ctx.to_system_note()
    assert "Memory from past conversations:" in note
    assert "- Builds a robot" in note
    # Memory label appears before the plain `tone` fact.
    assert note.index("Memory from past conversations") < note.index("tone: concise")


# ---------------------------------------------------------------------------
# Minor — explicit facts only, NO signals
# ---------------------------------------------------------------------------


async def test_minor_excludes_observed_signals(
    store: InMemoryKnowledgeStore, judgment: JudgmentLayer
) -> None:
    await store.upsert_person(Person(person_id="kid", display_name="Sam", role=PersonRole.MINOR))
    await store.add_fact(ProfileFact(person_id="kid", key="age", value="8"))

    # Record a high-confidence signal — it must NOT appear in the context.
    from shared_schemas.knowledge.models import ConsentRecord

    consent = ConsentRecord(person_id="kid", granted_by="owner", scope="observed_learning")
    await store.set_consent(consent)
    await store.record_signal(
        ObservedSignal(person_id="kid", kind="likes_maths", value="yes", confidence=0.9)
    )

    ctx = await judgment.build_context("kid")
    assert ctx is not None
    assert len(ctx.facts) == 1
    assert ctx.facts[0].key == "age"
    assert ctx.signals == []


async def test_minor_system_note_has_no_signal_lines(
    store: InMemoryKnowledgeStore, judgment: JudgmentLayer
) -> None:
    await store.upsert_person(Person(person_id="kid2", display_name="Jo", role=PersonRole.MINOR))
    await store.add_fact(ProfileFact(person_id="kid2", key="fav_color", value="blue"))
    ctx = await judgment.build_context("kid2")
    assert ctx is not None
    note = ctx.to_system_note()
    assert "fav_color" in note
    assert "confidence" not in note


# ---------------------------------------------------------------------------
# Owner / Family — facts + high-confidence signals
# ---------------------------------------------------------------------------


async def test_owner_includes_high_confidence_signals(
    store: InMemoryKnowledgeStore, judgment: JudgmentLayer
) -> None:
    await store.upsert_person(Person(person_id="jan", display_name="Jan", role=PersonRole.OWNER))
    await store.add_fact(ProfileFact(person_id="jan", key="language", value="Dutch"))
    await store.record_signal(
        ObservedSignal(person_id="jan", kind="prefers_morning_work", value="yes", confidence=0.8)
    )
    await store.record_signal(
        ObservedSignal(person_id="jan", kind="rarely_checks_email", value="true", confidence=0.3)
    )

    ctx = await judgment.build_context("jan")
    assert ctx is not None
    assert len(ctx.facts) == 1
    signal_kinds = {s.kind for s in ctx.signals}
    assert "prefers_morning_work" in signal_kinds
    assert "rarely_checks_email" not in signal_kinds  # below threshold


async def test_family_includes_signals_above_threshold(
    store: InMemoryKnowledgeStore, judgment: JudgmentLayer
) -> None:
    await store.upsert_person(
        Person(person_id="spouse", display_name="Kim", role=PersonRole.FAMILY)
    )
    await store.record_signal(
        ObservedSignal(person_id="spouse", kind="dislikes_early_calls", value="true", confidence=0.6)
    )
    await store.record_signal(
        ObservedSignal(person_id="spouse", kind="low_signal", value="maybe", confidence=0.4)
    )

    ctx = await judgment.build_context("spouse")
    assert ctx is not None
    assert any(s.kind == "dislikes_early_calls" for s in ctx.signals)
    assert all(s.kind != "low_signal" for s in ctx.signals)


async def test_signals_sorted_by_confidence_descending(
    store: InMemoryKnowledgeStore, judgment: JudgmentLayer
) -> None:
    await store.upsert_person(Person(person_id="u", display_name="U", role=PersonRole.OWNER))
    await store.record_signal(
        ObservedSignal(person_id="u", kind="alpha", value="a", confidence=0.6)
    )
    await store.record_signal(
        ObservedSignal(person_id="u", kind="beta", value="b", confidence=0.9)
    )
    await store.record_signal(
        ObservedSignal(person_id="u", kind="gamma", value="g", confidence=0.7)
    )

    ctx = await judgment.build_context("u")
    assert ctx is not None
    confidences = [s.confidence for s in ctx.signals]
    assert confidences == sorted(confidences, reverse=True)


async def test_max_facts_cap_respected(
    store: InMemoryKnowledgeStore, judgment: JudgmentLayer
) -> None:
    await store.upsert_person(Person(person_id="rich", display_name="Rich", role=PersonRole.OWNER))
    for i in range(10):
        await store.add_fact(ProfileFact(person_id="rich", key=f"k{i}", value=f"v{i}"))

    ctx = await judgment.build_context("rich")
    assert ctx is not None
    assert len(ctx.facts) <= 4  # max_facts fixture value


# ---------------------------------------------------------------------------
# system_note format
# ---------------------------------------------------------------------------


async def test_system_note_includes_name_and_role(
    store: InMemoryKnowledgeStore, judgment: JudgmentLayer
) -> None:
    await store.upsert_person(
        Person(person_id="jan", display_name="Jan", role=PersonRole.OWNER)
    )
    ctx = await judgment.build_context("jan")
    assert ctx is not None
    note = ctx.to_system_note()
    assert "Jan" in note
    assert "owner" in note


async def test_system_note_includes_facts_and_signals(
    store: InMemoryKnowledgeStore, judgment: JudgmentLayer
) -> None:
    await store.upsert_person(Person(person_id="jan", display_name="Jan", role=PersonRole.OWNER))
    await store.add_fact(ProfileFact(person_id="jan", key="lang", value="Dutch"))
    await store.record_signal(
        ObservedSignal(person_id="jan", kind="morning_focus", value="yes", confidence=0.8)
    )

    ctx = await judgment.build_context("jan")
    assert ctx is not None
    note = ctx.to_system_note()
    assert "Dutch" in note
    assert "morning_focus" in note
    assert "80%" in note
