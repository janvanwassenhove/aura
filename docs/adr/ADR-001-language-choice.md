# ADR-001: Language and Framework Choice

**Status**: Accepted  
**Date**: 2026-04-25  
**Deciders**: AURA Platform Team

---

## Context

AURA is a modular embodied AI assistant requiring:
- Async I/O for concurrent audio, motion, LLM, and event handling
- WebSocket support for real-time event streaming
- Strong typing and schema validation for inter-service communication
- A lightweight frontend for the operator console
- Low setup friction for contributors

We needed to choose: backend language, framework, async model, package manager, and frontend stack.

---

## Decision

**Backend**: Python 3.11+ with FastAPI and asyncio  
**Data Models**: Pydantic v2  
**Package Manager**: `uv` (replaces pip/poetry for speed and reproducibility)  
**Frontend**: Vue 3 + Vite + TypeScript + Pinia + TailwindCSS  
**Containerization**: Docker + Docker Compose  

---

## Rationale

### Python 3.11+
- Native asyncio with excellent library support (httpx, SQLAlchemy async, openai)
- First-class support from OpenAI, Whisper, MSAL, and Reachy SDK
- Strong type annotation ecosystem (Pydantic v2, mypy)
- 3.11 performance improvements justify the version pin

### FastAPI + asyncio
- Async-first: handles concurrent WebSocket, audio, and LLM calls without threads
- Auto-generates OpenAPI docs from type annotations
- Pydantic v2 integration for request/response validation
- WebSocket support built-in (needed for operator console and event streaming)

### Pydantic v2
- 5-10x faster than v1; Rust-based core
- Required for OpenAI function-call schema generation
- Enables shared event schemas across all services

### `uv`
- 10-100x faster than pip for dependency resolution
- Reproducible lockfiles
- `uv run` replaces virtualenv activation in development scripts

### Vue 3 + TypeScript
- Composition API is a natural fit for reactive event-driven UI
- Pinia is the Vue-endorsed state manager (replaces Vuex)
- TypeScript catches schema mismatches between backend events and frontend models
- TailwindCSS for rapid UI development without custom CSS overhead

---

## Consequences

### Positive
- asyncio handles all concurrent workloads without threading complexity
- Pydantic v2 models serve as the contract between all services
- `uv` speeds up CI dependency installation significantly
- Vue 3's reactivity system maps cleanly to the event-driven backend

### Negative
- Python GIL limits true CPU parallelism (mitigated by asyncio for I/O-bound work)
- `uv` is newer than pip; some CI environments may need setup
- Requires contributors to know both Python and TypeScript

### Neutral
- Node/npm is required for the frontend; developers need both runtimes installed

---

## Alternatives Considered

| Option | Reason Rejected |
|--------|----------------|
| Node.js (Express) backend | Less natural for audio/ML workloads; Reachy SDK is Python-only |
| Go backend | No mature Whisper/OpenAI bindings; team expertise not available |
| Flask instead of FastAPI | No native async support; no OpenAPI generation |
| React frontend | Team preference for Vue; Pinia's composition API integrates more naturally |
| Poetry package manager | Slower than uv; no `run` shortcut |
