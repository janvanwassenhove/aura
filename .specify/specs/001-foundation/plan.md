---
spec: "001-foundation"
status: draft
created: 2025-01-01
---

# 001 — Foundation: Implementation Plan

## Summary

Create the repository skeleton: directory structure, package/service stubs, Docker Compose skeleton, and CI workflow. No functional code beyond `/health` endpoints and placeholder READMEs.

## Technical Context

- All services are Python 3.11+ FastAPI apps managed by `uv`
- All packages use `uv` workspaces
- Docker Compose runs all 7 containers
- GitHub Actions runs `pytest` + `docker compose up --dry-run` on every push

## Constitution Check

| Principle | Gate | Status |
|-----------|------|--------|
| Spec-First | Plan written before any code | ✅ |
| Hardware Abstraction | No Reachy SDK in stub code | ✅ |
| FakeRobot default | All stubs use `fake` adapters | ✅ |
| No sensitive data in logs | No log code in stubs | ✅ |

## Project Structure

```
C:\dev\reachy-chief-of-staff\
├── .github/workflows/ci.yml
├── packages/
│   ├── shared-schemas/       # pyproject.toml, src/shared_schemas/__init__.py
│   ├── shared-events/        # pyproject.toml, src/shared_events/__init__.py
│   ├── shared-policies/      # pyproject.toml, src/shared_policies/__init__.py
│   ├── shared-personas/      # pyproject.toml, src/shared_personas/__init__.py
│   └── shared-prompts/       # pyproject.toml, src/shared_prompts/__init__.py
├── services/
│   ├── robot-runtime/        # pyproject.toml, src/robot_runtime/main.py
│   ├── conversation-runtime/ # pyproject.toml, src/conversation_runtime/main.py
│   ├── orchestrator/         # pyproject.toml, src/orchestrator/main.py
│   ├── connector-service/    # pyproject.toml, src/connector_service/main.py
│   ├── memory-service/       # pyproject.toml, src/memory_service/main.py
│   └── identity-service/     # pyproject.toml, src/identity_service/main.py
└── apps/
    └── operator-console/     # package.json, vite.config.ts, src/
```

## Implementation Steps

### Phase 1: Package Stubs

For each package (`shared-schemas`, `shared-events`, `shared-policies`, `shared-personas`, `shared-prompts`):
1. Create `pyproject.toml` with `uv` project settings
2. Create `src/<package_name>/__init__.py` with `__version__ = "0.1.0"`
3. Create `tests/__init__.py`

### Phase 2: Service Stubs

For each service:
1. Create `pyproject.toml` with FastAPI, uvicorn, and shared package dependencies
2. Create `src/<service_name>/main.py` with `FastAPI()` app and `/health` → `{"status": "ok", "service": "<name>"}` route
3. Create `Dockerfile` using `python:3.11-slim`, `uv sync`, `uvicorn`
4. Create `tests/__init__.py`

### Phase 3: Operator Console Skeleton

1. `npm create vite@latest operator-console -- --template vue-ts`
2. Add TailwindCSS and Pinia
3. Replace default App.vue with AURA placeholder
4. Create `Dockerfile` with `node:20-slim`, `npm ci`, `npm run dev`

### Phase 4: Root Workspace

1. Create root `pyproject.toml` (uv workspace — lists all packages and services)
2. Verify `docker compose up --dry-run` passes
3. Verify `uv sync` at root installs all packages

### Phase 5: CI

1. Create `.github/workflows/ci.yml`
2. Steps: checkout, setup-python 3.11, install uv, `uv sync`, `pytest`, `docker compose config`

## Complexity Tracking

- Python files: ~20 stub files
- Docker files: 7 Dockerfiles + 1 docker-compose.yml
- Estimated effort: 2–3 hours
