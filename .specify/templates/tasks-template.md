---
description: "Task list template for feature implementation"
---

# Tasks: [FEATURE NAME]

**Input**: Design documents from `.specify/specs/[NNN-feature-name]/`
**Prerequisites**: `plan.md` (required), `spec.md` (required)

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2)
- Include exact file paths in descriptions

---

## Phase 1: Setup

- [ ] T001 Create project structure per implementation plan
- [ ] T002 [P] Initialize package with dependencies

---

## Phase 2: Foundational

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T003 Create base models / schemas
- [ ] T004 Configure service skeleton

**Checkpoint**: Foundation ready

---

## Phase 3: User Story 1 - [Title] (Priority: P1)

**Goal**: [Brief description]
**Independent Test**: [How to verify]

- [ ] T005 [P] [US1] [Task description] in [file path]
- [ ] T006 [US1] [Task description] in [file path]

**Checkpoint**: User Story 1 fully functional

---

## Dependencies & Execution Order

- Setup → Foundational → User Stories (in parallel if staffed)
- [P] tasks within a phase can run simultaneously

## Notes

- [P] = different files, no dependencies
- Story label maps task to spec user story for traceability
- Verify tests fail before implementing (TDD where applicable)
