---
feature: "018-knowledge-people-and-judgment"
---

# Implementation Plan: Knowledge, People and Judgment

**Prerequisites**: `spec.md`, [ADR-008](../../../docs/adr/ADR-008-knowledge-judgment-layer.md).
Retro-written from the code.

## Shape

```
camera ─▶ perception.py ─▶ PersonRecognized ─┐
                                             ├─▶ judgment layer ─▶ what may be
console header (manual pick) ────────────────┘    (role rules)       used/learned
                                                        │
                                          knowledge store (encrypted per person)
                                             Person · ProfileFact · memory · consent
```

The judgment layer is **stateless over the store**: it decides, per turn, what
this person's role permits. Nothing about a minor is retained by having thought
about it.

## Decisions

### One key per person, one owner key, no second copy

ADR-008 §4, implemented in U19b/U29 and hardened in U225. The passphrase lives
in the Windows credential store (DPAPI-protected by the Windows login), derives
the owner key, which wraps a key per person. Destroying a person's key leaves
unreadable ciphertext — which is what makes "forget this person" a real
promise rather than a hidden row.

The cost is stated plainly because it is real: **there is no recovery.** Losing
the passphrase loses the profiles and the face data.

### Memory is lines, not a blob

U272/U279/U280. Long-term memory was stored as one `ProfileFact` with key
`memory` whose value was the entire bullet list, and the graph drew one node per
fact. Everything he had learned about a person therefore arrived as a single
dot labelled `memory: - Jan is actief en…`, cut at 40 characters.
`lib/memoryGraph.ts` splits it into lines, extracts keywords for the label,
keeps the full sentence for the hover, colours memory distinctly, and reads
`[[links]]` as edges to other people.

### A mentioned person may be created, but never duplicated

U281. The owner's instruction was explicit: *"hij mag automatisch profiel maken
(brain blijft lokaal binnen familie), maar indien persoon al bestaat moet hij
link kunnen leggen gezien context of voorstellen"*. So creation is allowed and
matching comes first. U293 then gave the turn a `household_note` so he knows
who lives here **before** the conversation rather than only after it, and U294
gave him `look_up_person` so he can go and check on his own.

### Tagging a low-confidence sighting is training, not just correction

The owner's observation: *"ik ga er vanuit dat hier een mindere mate van
zekerheid is en zo bij kan dragen tot trainen als ik hier tag met juiste
persoon"*. Correct — a tagged sighting is added as evidence, so the ✕ on an
unknown-visitor card improves recognition rather than only tidying a list.

### The console must never invent a knowledge state

U276, U278, U290. Three separate cases of the console showing a state the brain
did not share, the last one because an internal helper returns a `Response`
object and the calling code treated it as JSON. Speaker selection now
reconciles in both directions, and the "nothing is being remembered" banner is
derived from the brain's answer rather than from the console's own guess.

## Files

| Path | Role |
|---|---|
| `packages/shared-schemas/src/shared_schemas/knowledge.py` | Person, ProfileFact, the store ABC, the in-memory store |
| `apps/aura-brain/src/aura_brain/knowledge_api.py` | Transparency API: inspect, edit, erase, unlock |
| `apps/aura-brain/src/aura_brain/person_memory.py` | Distilling turns into long-term memory |
| `apps/aura-brain/src/aura_brain/perception.py` | Camera → recognition → room awareness |
| `apps/aura-brain/src/aura_brain/recognition_api.py` | Teach a face, avatars, re-file a sighting |
| `apps/aura-brain/src/aura_brain/source_ingest.py` | Growing a profile from blogs, sites, exports |
| `services/orchestrator/src/orchestrator/pipeline.py` | `person_note`, `household_note`, `look_up_person`, role gating per turn |
| `apps/operator-console/src/lib/memoryGraph.ts` | Memory as lines, keywords, links, colour |
| `apps/operator-console/src/stores/knowledgeStore.ts` | Speaker, people, facts, memory, thresholds |
