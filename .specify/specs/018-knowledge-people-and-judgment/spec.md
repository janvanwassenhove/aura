---
feature: "018-knowledge-people-and-judgment"
status: "implemented"
owner: "aura-brain / knowledge"
priority: P1
risk: High
created: "2026-09-05"
units: [U18, U19a, U19b, U19c, U19d, U19e, U20, U29, U93, U94, U97, U103, U104, U105, U106, U109, U136, U160, U180, U181, U189, U190, U204, U213, U214, U218, U243, U244, U245, U271, U272, U274, U276, U277, U278, U279, U280, U281, U290, U293, U294, U36f]
amended: "2026-09-05"
---

# Feature Specification: Knowledge, People and Judgment

**Feature Branch**: `018-knowledge-people-and-judgment`
**Created**: 2026-09-05 (retro-specified — see [015-spec-coverage](../015-spec-coverage/spec.md))
**Status**: Implemented
**Owner**: aura-brain (`knowledge_api.py`, `person_memory.py`, `perception.py`, `recognition_api.py`) + orchestrator (`pipeline.py`)
**Priority**: P1
**Risk**: **High.** This is where the personal data lives. A defect here is not
a bad answer; it is a child's profile read by a guest, or a face nobody can
delete.

## Background

[ADR-008](../../../docs/adr/ADR-008-knowledge-judgment-layer.md) defines the
model: `Person`, `ProfileFact`, consent records, envelope encryption keyed to
the owner, unlock tiers, and role rules. It was written in June and is still
broadly right. What it does not describe is everything the layer learned to do
since — recognising faces in a living room, growing a profile from a
conversation, linking one person's memory to another, and being honest about
when it is doing none of that.

The owner's requirement, in their words, was that it be *"securely saved"*, and
that has shaped every decision here: the store is encrypted per person, the
owner key exists in exactly one place, and nothing is remembered about somebody
the system cannot name.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — He knows who is in front of him (Priority: P1)

**Acceptance Scenarios**:

1. **Given** a taught face, **When** that person appears, **Then**
   `PersonRecognized` is published with a confidence, and the console shows who
   he thinks it is (U18).
2. **Given** a face at the far end of a room, **When** it is only 34 pixels
   across, **Then** it is still matched — the pipeline was discarding anything
   too small to be a portrait, which is most of a living room (U271).
3. **Given** an unfamiliar face, **When** it is seen, **Then** it is filed as a
   guest profile with a snapshot rather than discarded (U36f, U181), the guest
   count is capped so a busy room cannot explode the store (U190), and the
   owner can name them, attach them to somebody already known, or forget them
   (U189).
4. **Given** a recognition the owner disagrees with, **When** they press the ✕
   on the sighting, **Then** it is re-filed for correct tagging (U136) — and
   tagging a low-confidence sighting with the right person **improves** the
   match rather than only correcting the record.
5. **Given** a person is deleted, **When** they are, **Then** their face goes
   with them. U244: it did not, so the deleted person kept being recognised.
6. **Given** an app update, **When** it installs, **Then** face recognition
   still works — U218 verified this rather than trusting a marker file, after
   recognition vanished after every update.
7. **Given** the owner teaches a face, **When** they do, **Then** the feedback
   is honest about what was captured (U213), and the photo becomes that
   person's avatar (U204).

### User Story 2 — What he learns, he learns about the right person (Priority: P1)

Reported as *"terwijl ik (jan) vertel tegen robot geef ik informatie, maar ik
zie dat hij niet gebruikt in zijn kennisopbouw"*, and later *"kan hij vandaag
al linken leggen tussen persona? bv. als ik praat als jan, over jappe, dan kan
hij ook kennis opbouwen over jappe op dat ogenblik"*.

**Acceptance Scenarios**:

1. **Given** a recognised or chosen speaker, **When** they say something worth
   keeping, **Then** it is distilled into that person's long-term memory
   (U109), and the console reflects it (U276 — it was silently dropped).
2. **Given** the conversation mentions somebody else in the household, **When**
   it does, **Then** what is learned about **them** hangs off their profile,
   linked with `[[wikilinks]]` (U280), and the graph draws the edge (U272,
   U279).
3. **Given** a name he has not met, **When** it comes up, **Then** he may
   create a profile himself — the brain stays local to the household — but he
   checks first whether that person already exists and links instead of
   creating a duplicate (U281).
4. **Given** the household's other members, **When** a turn is built, **Then**
   he already knows they exist (`household_note`, U293) rather than only
   learning it from the conversation, and he can go and look somebody up
   himself with the `look_up_person` tool (U294).
5. **Given** the owner corrects a remembered fact, **When** they save it,
   **Then** it is stored, shown and used (U278 — it was saved, shown nowhere
   and used never).
6. **Given** long-term memory, **When** it is drawn in the graph, **Then** it
   is one node per remembered line with its keywords, styled distinctly from
   skills and facts, with a legend that names it (U272, U279). It used to be a
   single dot labelled `memory: - Jan is actief en…`, truncated at 40
   characters.

### User Story 3 — He says when he is *not* remembering (Priority: P1)

Reported as *"why am I getting: 'Nothing is being remembered right now…'"* —
while he was, in fact, remembering.

**Acceptance Scenarios**:

1. **Given** no speaker is known, **When** a turn happens, **Then** the console
   says so plainly and says how to fix it (pick who you are, or teach the
   face).
2. **Given** a speaker **is** set, **When** the console asks, **Then** it
   reports that — U290: the console called an internal helper that returns a
   `Response` and read it as JSON, so it concluded "nobody" while the brain
   knew exactly who was talking. The console and the brain now reconcile in
   both directions (`fetchSpeaker`).
3. **Given** the owner chooses a speaker in the header, **When** they do,
   **Then** the choice reaches the brain (`syncSpeaker`) and survives a reload.

### User Story 4 — Role decides what may be learned and shown (Priority: P1)

**Acceptance Scenarios**:

1. **Given** a person with `role=minor`, **When** they talk, **Then** passive
   learning does **not** happen; it requires the owner to opt in deliberately
   (ADR-008 §10).
2. **Given** a guest, **When** they talk, **Then** only their name is retained.
3. **Given** the owner is not present, **When** anything sensitive is
   requested, **Then** the unlock tier gates it (U19c, U20), and the badge
   explaining the tier is written in the owner's language rather than the word
   `BENIGN` (U180).
4. **Given** any person, **When** the owner opens their profile, **Then** they
   can see exactly what is known, edit it, and erase it (U19d) — including the
   provenance of anything mined from a source (U105).
5. **Given** the store, **When** it is at rest, **Then** it is encrypted per
   person under an owner key that exists only in the OS credential store
   (U19b, U29). There is no second copy: losing the passphrase loses the
   profiles and the face data.

### User Story 5 — The profile grows from more than conversation (Priority: P2)

**Acceptance Scenarios**:

1. **Given** a blog, website or GitHub profile, **When** it is added as a
   source, **Then** the persona graph grows from it with provenance topics
   (U103, U105).
2. **Given** a ChatGPT or Claude export, **When** it is imported, **Then** it
   is mined into the brain, and the whole store can be exported as JSON (U104).
3. **Given** a large graph, **When** it is explored, **Then** it can be panned,
   zoomed (U106) and filtered by person (U214).
4. **Given** a fresh install, **When** it starts, **Then** exactly one
   fictional demo persona exists (U160) — which is what makes the release
   screenshots safe to publish by construction.

### User Story 6 — He greets people, once (Priority: P2)

1. **Given** somebody arrives, **When** they are recognised, **Then** he greets
   them by name (U36a).
2. **Given** they stay in the room, **When** they do, **Then** he does not greet
   them again every two minutes (U243).
3. **Given** the speech path, **When** it speaks, **Then** it knows who is
   standing there — U245: it did not, so the greeting was personalised while
   the reply was not.

## Functional Requirements

- **FR-001**: One `Person` per human, with a role. Role gates learning and
  disclosure per ADR-008 §10.
- **FR-002**: The store is encrypted with envelope encryption: a passphrase in
  the OS credential store derives an owner key that is never written to disk;
  the owner key wraps one key per person; each person's key encrypts only their
  own records.
- **FR-003**: Long-term memory is per person, distilled from turns, editable by
  the owner, and rendered as individual lines with keywords and links — never
  as one opaque blob.
- **FR-004**: A person mentioned in conversation may be created or linked
  automatically, but never duplicated when a profile already exists.
- **FR-005**: Face recognition matches at living-room distance, files unknowns
  as capped guest profiles with snapshots, and deletes face data with the
  person.
- **FR-006**: The console never claims a memory state the brain does not share,
  in either direction.
- **FR-007**: A fresh install contains exactly one fictional demo persona and
  no real data.

## Out of scope

- The camera and the tracking of a face in the room — see
  [016-embodiment-and-presence](../016-embodiment-and-presence/spec.md).
- Which language a person is met in is *stored* here and *consumed* by
  [017-voice-and-language](../017-voice-and-language/spec.md) (U274).
- Skills scoped to a person — see
  [019-skills-and-automation](../019-skills-and-automation/spec.md).

## Traceability

| Units | What they delivered |
|---|---|
| U19a, U19b, U29 | Schemas and the person-scoped store; envelope crypto; persisted encrypted to disk |
| U19c, U20, U180 | Owner-unlock tiers, the outbound dev-agent tool, and a badge that speaks the owner's language |
| U19d, U93, U94, U97 | Transparency API and UI: inspect, edit, erase; Knowledge inside the Brain panel; add a person back; and the 500 that made everybody "vanish" |
| U19e | The judgment / anticipation layer, stateless over the store |
| U18, U271, U213, U218, U244 | Recognition: the embedding matcher, faces at 34 pixels, honest teach feedback, surviving updates, and a deleted person who kept their face |
| U136, U181, U189, U190 | Flagging a wrong recognition; guest profiles; naming or attaching a guest; capping the guest explosion |
| U103, U104, U105, U106, U214 | Growing from sources, import/export, provenance, pan/zoom, filter by person |
| U109, U276, U278 | Long-term memory per person — written, shown, and correctable |
| U272, U279, U280 | Memory in the graph: split into lines with keywords, its own styling and legend, and edges to the people it mentions |
| U281, U293, U294 | Creating a profile without duplicating one; knowing the household before the conversation; looking somebody up on his own |
| U290 | The console reading a `Response` as JSON, and telling the owner nothing was being remembered while it was |
| U243, U245, U204 | Greeting on arrival rather than every two minutes; the speech path knowing who is there; per-person avatars |
| U160 | The fictional demo persona that ships with the app |
