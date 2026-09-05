---
feature: "018-knowledge-people-and-judgment"
---

# Tasks: Knowledge, People and Judgment

Retro-specified; all done.

## Phase 1: The store

- [x] T001 [U19a] Knowledge schemas + person-scoped store (ADR-008)
- [x] T002 [U19b, U29] Envelope encryption; persisted to disk
- [x] T003 [U19c, U20] Owner-unlock tiers; outbound dev-agent tool
- [x] T004 [U19d, U93, U94] Transparency API and UI; Knowledge inside the Brain panel
- [x] T005 [U19e] Judgment layer, stateless over the store
- [x] T006 [U97] One undecryptable entry no longer 500s the whole people list

## Phase 2: Recognising people

- [x] T007 [U18] Embedding matcher + `PersonRecognized`
- [x] T008 [U271] Match faces at living-room distance (34 px)
- [x] T009 [U181, U190] Guest profiles for unknown faces, capped
- [x] T010 [U136, U189] Re-file a wrong sighting; name, attach or forget a guest
- [x] T011 [U213, U204] Honest teach feedback; the teach photo becomes the avatar
- [x] T012 [U218] Verify recognition survives an update instead of trusting a marker
- [x] T013 [U244] Deleting a person deletes their face

## Phase 3: Growing

- [x] T014 [U103, U105] Sources: blog, website, GitHub, with provenance
- [x] T015 [U104] Import ChatGPT/Claude exports; JSON export of the store
- [x] T016 [U109] Long-term memory per person
- [x] T017 [U276, U278] Memory that is actually written, shown and correctable
- [x] T018 [U272, U279] Memory as lines in the graph, with keywords, styling and a legend
- [x] T019 [U280] `[[links]]` become edges — what he learns about someone else lands on them
- [x] T020 [U281] Create a profile without duplicating an existing one
- [x] T021 [U293, U294] `household_note` before the turn; `look_up_person` during it
- [x] T022 [U106, U214] Pan, zoom, filter the graph by person

## Phase 4: Honesty

- [x] T023 [U180] The unlock badge in the owner's language
- [x] T024 [U290] The console and the brain agree on who is talking
- [x] T025 [U243, U245] Greet on arrival, not on a timer; the speech path knows who is there
- [x] T026 [U160] One fictional demo persona on a fresh install
