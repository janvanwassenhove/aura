---
feature: "001-foundation"
status: "in-progress"
owner: "platform"
priority: P1
risk: Low
created: "2026-04-25"
---

# Feature Specification: Foundation and Spec Kit Setup

**Feature Branch**: `001-foundation`
**Created**: 2026-04-25
**Status**: In Progress
**Owner**: platform
**Priority**: P1
**Risk**: Low

## User Scenarios & Testing

### User Story 1 — Repository and Spec Kit Structure Exists (Priority: P1)

A new contributor clones the repository and immediately understands the project's structure, principles, and development conventions without needing any external documentation.

**Why this priority**: Everything else depends on this. No feature work can begin without a known structure and agreed principles.

**Independent Test**: After cloning, `ls .specify/memory/constitution.md` succeeds and `cat AGENTS.md` shows the spec kit command reference.

**Acceptance Scenarios**:

1. **Given** a fresh clone of the repo, **When** the contributor reads `AGENTS.md`, **Then** they see the spec kit commands, project map, and key interface locations.
2. **Given** the repo, **When** the contributor reads `.specify/memory/constitution.md`, **Then** they see all eight principles, architecture constraints, and governance rules.
3. **Given** the repo, **When** the contributor lists `.specify/specs/`, **Then** they see folders `001-foundation` through `012-openclaw`, each containing at minimum a `spec.md`.

---

### User Story 2 — Docker Compose Skeleton Starts (Priority: P1)

A developer can run `docker compose up` from `infra/dev/` and see all service containers start (even if they only return health-check responses).

**Why this priority**: Establishes the local dev loop that all subsequent feature work depends on.

**Independent Test**: `docker compose -f infra/dev/docker-compose.yml up --build` completes without errors; `curl http://localhost:8001/health` returns 200.

**Acceptance Scenarios**:

1. **Given** Docker Desktop running, **When** `docker compose up` is run, **Then** all 6 service containers start and pass health checks within 60 seconds.
2. **Given** the stack is running, **When** any service container is stopped, **Then** the remaining services continue running.
3. **Given** `.env.example`, **When** copied to `.env` with no edits, **Then** `docker compose up` succeeds with mock/fake defaults.

---

### User Story 3 — All Services Have Placeholder READMEs (Priority: P2)

Every service, package, and app directory contains a `README.md` describing its purpose, responsibilities, and key interfaces.

**Why this priority**: Enables parallel onboarding across multiple contributors.

**Independent Test**: `find . -name README.md | wc -l` returns ≥ 15.

**Acceptance Scenarios**:

1. **Given** any service directory, **When** a contributor reads its `README.md`, **Then** they see: purpose, responsibilities, dependencies, and how to run it locally.

---

### Edge Cases

- What happens when `.env` is missing? → `docker compose` prints clear error listing required vars.
- What if a service fails to start? → Health check failure is visible in compose output; other services continue.

---

## Requirements

### Functional Requirements

- **FR-001**: Repository MUST contain `.specify/memory/constitution.md` with all eight principles.
- **FR-002**: Repository MUST contain `AGENTS.md` with Spec Kit command reference and project map.
- **FR-003**: Repository MUST contain `.specify/specs/001/` through `.specify/specs/012/`, each with `spec.md`.
- **FR-004**: Repository MUST contain `.specify/templates/spec-template.md`, `plan-template.md`, `tasks-template.md`.
- **FR-005**: Repository MUST contain `infra/dev/docker-compose.yml` defining all 6 backend services.
- **FR-006**: Repository MUST contain `infra/dev/.env.example` with all required environment variables documented.
- **FR-007**: Every directory under `services/`, `packages/`, and `apps/` MUST contain a `README.md`.
- **FR-008**: Repository MUST contain `docs/adr/` with at minimum ADR-001 through ADR-006.
- **FR-009**: Repository MUST contain `docs/architecture/overview.md` with a system-level Mermaid diagram.

### Key Entities

- **SpecKitSpec**: A folder under `.specify/specs/NNN-name/` containing `spec.md` (and optionally `plan.md`, `tasks.md`).
- **ADR**: A markdown file in `docs/adr/` following the standard template (Status, Context, Decision, Consequences).

---

## Success Criteria

### Measurable Outcomes

- **SC-001**: All 12 spec folders exist with valid `spec.md` files containing frontmatter, user stories, and acceptance criteria.
- **SC-002**: `docker compose up` completes with all services healthy in under 60 seconds on a developer machine.
- **SC-003**: All 5+1 ADRs exist with Status, Context, Decision, and Consequences sections.
- **SC-004**: `find . -name README.md | wc -l` returns ≥ 15.
- **SC-005**: Running `grep -r "RobotAdapter" services/orchestrator/` returns no matches (hardware abstraction validated).

---

## Assumptions

- Docker Desktop is installed and running on the developer machine.
- `uv` (Python package manager) is available for local service runs.
- `node` and `npm` are available for the operator console.
- All services default to mock/fake adapters when no hardware or M365 credentials are provided.

---

## References

- [Constitution](.specify/memory/constitution.md)
- [ADR-001](docs/adr/ADR-001-language-choice.md)
- [ADR-002](docs/adr/ADR-002-event-model.md)
- [Architecture Overview](docs/architecture/overview.md)
