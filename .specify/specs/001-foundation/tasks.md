# 001 — Foundation: Task List

Format: `[ID] [P?] Description` — `[P]` = can run in parallel; tasks without `[P]` are sequential.

## Phase 0: Workspace Config

- [x] `T001` Create root `pyproject.toml` with uv workspace listing all packages and services
- [x] `T002` [P] Create `.python-version` file with `3.11`

## Phase 1: Shared Package Stubs (all [P])

- [x] `T003` [P] `packages/shared-schemas/pyproject.toml` — name `shared-schemas`, version `0.1.0`
- [x] `T004` [P] `packages/shared-schemas/src/shared_schemas/__init__.py` — `__version__ = "0.1.0"`
- [x] `T005` [P] `packages/shared-events/pyproject.toml` — depends on `shared-schemas`
- [x] `T006` [P] `packages/shared-events/src/shared_events/__init__.py`
- [x] `T007` [P] `packages/shared-policies/pyproject.toml` — depends on `shared-schemas`
- [x] `T008` [P] `packages/shared-policies/src/shared_policies/__init__.py`
- [x] `T009` [P] `packages/shared-personas/pyproject.toml` — depends on `shared-schemas`
- [x] `T010` [P] `packages/shared-personas/src/shared_personas/__init__.py`
- [x] `T011` [P] `packages/shared-prompts/pyproject.toml` — no workspace deps
- [x] `T012` [P] `packages/shared-prompts/src/shared_prompts/__init__.py`

## Phase 2: Service Stubs (all [P])

- [x] `T013` [P] `services/robot-runtime/pyproject.toml` — FastAPI, uvicorn, shared-schemas, shared-events
- [x] `T014` [P] `services/robot-runtime/src/robot_runtime/main.py` — `/health` route only
- [x] `T015` [P] `services/robot-runtime/Dockerfile`
- [x] `T016` [P] `services/conversation-runtime/pyproject.toml`
- [x] `T017` [P] `services/conversation-runtime/src/conversation_runtime/main.py`
- [x] `T018` [P] `services/conversation-runtime/Dockerfile`
- [x] `T019` [P] `services/orchestrator/pyproject.toml`
- [x] `T020` [P] `services/orchestrator/src/orchestrator/main.py`
- [x] `T021` [P] `services/orchestrator/Dockerfile`
- [x] `T022` [P] `services/connector-service/pyproject.toml`
- [x] `T023` [P] `services/connector-service/src/connector_service/main.py`
- [x] `T024` [P] `services/connector-service/Dockerfile`
- [x] `T025` [P] `services/memory-service/pyproject.toml`
- [x] `T026` [P] `services/memory-service/src/memory_service/main.py`
- [x] `T027` [P] `services/memory-service/Dockerfile`
- [x] `T028` [P] `services/identity-service/pyproject.toml`
- [x] `T029` [P] `services/identity-service/src/identity_service/main.py`
- [x] `T030` [P] `services/identity-service/Dockerfile`

## Phase 3: Operator Console Skeleton

- [x] `T031` `apps/operator-console/package.json` — Vue 3 + Vite + TypeScript + Pinia + TailwindCSS
- [x] `T032` `apps/operator-console/vite.config.ts`
- [x] `T033` `apps/operator-console/src/main.ts`
- [x] `T034` `apps/operator-console/src/App.vue` — placeholder layout
- [x] `T035` `apps/operator-console/Dockerfile`

## Phase 4: CI

- [x] `T036` `.github/workflows/ci.yml` — steps: checkout, setup-python 3.11, install uv, `uv sync`, `pytest tests/ -x`, `docker compose -f infra/dev/docker-compose.yml config`

## Phase 5: Verification

- [x] `T037` Run `uv sync` at repo root — verify all packages resolve
- [x] `T038` Run `docker compose -f infra/dev/docker-compose.yml config` — verify YAML valid
- [x] `T039` `curl http://localhost:8001/health` through `curl http://localhost:8006/health` — all return 200

## Acceptance Criteria (from spec.md SC-001 through SC-005)

- SC-001: `docker compose up` builds and all containers reach healthy state
- SC-002: All 6 services return `{"status": "ok"}` from `/health`
- SC-003: `uv sync` at root resolves without error
- SC-004: Console loads at `http://localhost:5173` without JS errors
- SC-005: CI workflow passes on main branch
