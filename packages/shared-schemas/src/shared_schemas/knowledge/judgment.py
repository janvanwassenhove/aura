"""Judgment/anticipation layer (U19e, ADR-008 §1).

Stateless over the KnowledgeStore — reads a minimal profile slice per turn and
produces a PersonContext that can be injected into the LLM system prompt.
Persists nothing of its own.

Data-minimization rules (ADR-008 §6):
  - guest:  display_name only — enough for a polite greeting, nothing more.
  - minor:  explicit facts only; observed signals are NEVER included (ADR-008 §10:
            minors get no passive/observed learning by default).
  - family/owner: top-N explicit facts + signals above a confidence threshold.

The injected note is intentionally brief — the LLM gets a compact paragraph, not
the whole profile.  Raw biometrics and bulk-profile dumps never reach a cloud LLM.
"""

from __future__ import annotations

from pydantic import BaseModel

from shared_schemas.knowledge.models import (
    ObservedSignal,
    Person,
    PersonRole,
    ProfileFact,
)
from shared_schemas.knowledge.store import KnowledgeStore

_DEFAULT_MAX_FACTS = 8
_DEFAULT_SIGNAL_THRESHOLD = 0.55  # include signals with confidence >= this


class PersonContext(BaseModel):
    """Minimal profile slice for LLM injection.

    Created by JudgmentLayer.build_context(); call to_system_note() to get the
    text that goes into the LLM system prompt.
    """

    person: Person
    facts: list[ProfileFact] = []
    signals: list[ObservedSignal] = []

    def to_system_note(self) -> str:
        """Return a brief natural-language block for the LLM system prompt."""
        name = self.person.display_name
        role = self.person.role.value
        lines: list[str] = [f"Talking to: {name} ({role})."]
        if self.person.description:
            lines.append(f"  About them: {self.person.description}")

        # U109: long-term memory (from past conversations) leads — it's the most
        # useful continuity signal — and is labelled distinctly from plain facts.
        for fact in self.facts:
            if fact.key == "memory":
                lines.append(f"  Memory from past conversations:\n{fact.value}")
        for fact in self.facts:
            if fact.key != "memory":
                lines.append(f"  {fact.key}: {fact.value}")

        for signal in self.signals:
            pct = int(signal.confidence * 100)
            lines.append(f"  {signal.kind}: {signal.value} ({pct}% confidence)")

        return "\n".join(lines)


class JudgmentLayer:
    """Stateless judgment: reads a minimal profile slice and returns a PersonContext.

    Usage::

        judgment = JudgmentLayer(store)
        ctx = await judgment.build_context(person_id)
        if ctx:
            system_note = ctx.to_system_note()
    """

    def __init__(
        self,
        store: KnowledgeStore,
        max_facts: int = _DEFAULT_MAX_FACTS,
        signal_threshold: float = _DEFAULT_SIGNAL_THRESHOLD,
    ) -> None:
        self._store = store
        self._max_facts = max_facts
        self._threshold = signal_threshold

    async def build_context(self, person_id: str | None) -> PersonContext | None:
        """Return a minimal PersonContext, or None when the person is unknown.

        None means: inject nothing — the LLM turn proceeds without personal context.
        """
        if not person_id:
            return None
        person = await self._store.get_person(person_id)
        if person is None:
            return None

        # Guest: greeting name only — no facts, no signals.
        if person.role == PersonRole.GUEST:
            return PersonContext(person=person)

        # All other roles: load explicit facts, capped.
        facts = (await self._store.get_facts(person_id))[: self._max_facts]

        # Minors: explicit facts only (ADR-008 §10 — no observed/passive learning).
        if person.role == PersonRole.MINOR:
            return PersonContext(person=person, facts=facts)

        # Owner / Family: explicit facts + high-confidence observed signals.
        all_signals = await self._store.get_signals(person_id)
        signals = [s for s in all_signals if s.confidence >= self._threshold]
        signals.sort(key=lambda s: s.confidence, reverse=True)

        return PersonContext(person=person, facts=facts, signals=signals)
