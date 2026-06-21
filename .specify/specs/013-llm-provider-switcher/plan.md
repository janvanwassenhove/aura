---
description: "Implementation plan for LLM provider/model runtime switcher"
---

# Implementation Plan: LLM Provider Switcher (013)

**Branch**: `013-llm-provider-switcher` | **Date**: 2026-04-29 | **Spec**: `.specify/specs/013-llm-provider-switcher/spec.md`

## Summary

Expose a `LLMConfig` singleton in the orchestrator process that is read by `llm.py` on every call. Add `GET` and `PATCH` REST endpoints for it. Add a Settings panel to the operator console that reads and writes that config.

## Technical Context

**Language/Version**: Python 3.11 (orchestrator), TypeScript (operator console)
**Primary Dependencies**: FastAPI, Pydantic v2, Vue 3 + Pinia, TailwindCSS
**Storage**: In-memory only (intentionally not persisted — env vars are the durable source of truth)
**Testing**: pytest + pytest-asyncio (backend), no frontend unit tests required
**Target Platform**: Linux container / Docker

## Constitution Check

- [x] Hardware abstraction respected — no robot adapter changes
- [x] Sensitive data excluded from logs — API keys never logged, only `key_set: bool`
- [x] Events: LLM config change is operational, not a domain event — no event bus publish required
- [x] Approval gate: LLM switching is an operator-only internal config — not a sensitive tool call
- [x] Test coverage planned for all acceptance criteria (SC-001 through SC-005)

## Project Structure

### Files Created / Modified

```text
services/orchestrator/src/orchestrator/
  config.py              ← NEW: LLMConfig dataclass + module-level singleton
  llm.py                 ← MODIFY: read from config singleton instead of os.environ per call
  routes.py              ← MODIFY: add GET/PATCH /orchestrator/config/llm endpoints

apps/operator-console/src/
  components/
    SettingsPanel.vue    ← NEW: gear icon + modal/drawer with provider dropdown + model input
  stores/
    settingsStore.ts     ← NEW: Pinia store — fetchConfig(), applyConfig()
  App.vue                ← MODIFY: mount SettingsPanel, wire gear icon
```

## Implementation Steps

### Phase 1: Orchestrator — LLMConfig singleton

**Goal**: Decouple `llm.py` from `os.environ` so provider/model can be changed at runtime.

1. Create `config.py` — a `LLMConfig` dataclass with `provider` and `model` fields, initialised from env at module import. Expose a module-level `_config` instance and `get_config()` / `update_config()` helpers.
2. Modify `llm.py` — replace all `os.environ.get("LLM_PROVIDER")` and model reads with `get_config()` calls. Remove the module-level `_LLM_PROVIDER` cached variable.
3. Add two route handlers in `routes.py`:
   - `GET /orchestrator/config/llm` → returns `LLMConfigResponse` (provider, model, openai_key_set, openrouter_key_set)
   - `PATCH /orchestrator/config/llm` → accepts `LLMConfigUpdate` (provider, model), calls `update_config()`, returns updated `LLMConfigResponse`
4. Add Pydantic models `LLMConfigResponse` and `LLMConfigUpdate` (inline in `routes.py` or a new `schemas.py` — keep it simple, inline is fine for two small models).

### Phase 2: Orchestrator — Tests

1. Unit tests in `services/orchestrator/tests/` covering:
   - `GET /orchestrator/config/llm` returns correct initial values from env
   - `PATCH` updates the runtime config
   - Subsequent `GET` returns new values
   - `PATCH` with invalid provider returns 422
   - `openai_chat` with `provider=echo` uses echo path (existing test, ensure it still passes after refactor)

### Phase 3: Operator Console — Settings store + panel

1. Create `settingsStore.ts` — Pinia store with `provider`, `model`, `openaiKeySet`, `openrouterKeySet`, `loading`, `error` state. Methods: `fetchConfig()` (GET), `applyConfig(provider, model)` (PATCH).
2. Create `SettingsPanel.vue` — modal opened by a gear (⚙) icon button. Contains:
   - Provider `<select>` with options: `openai`, `openrouter`, `echo`
   - Model `<input>` (text, pre-filled with current model, hidden/disabled when provider = echo)
   - Key status badges: green dot "API key set" / yellow dot "Key not configured" for openai and openrouter
   - Apply button (calls `settingsStore.applyConfig`) → shows inline success/error
   - Cancel button
3. Modify `App.vue` — add gear icon button to top-right of header, `v-if` mount `SettingsPanel` on click.

## Key Design Decisions

- **In-memory only**: The config singleton is intentionally ephemeral. On orchestrator restart env vars take effect again. No database write needed.
- **Single config object**: One module-level singleton in `config.py` avoids threading issues (asyncio is single-threaded).
- **No event bus publish**: LLM config change is an operator action, not a domain event. The console is the source — no need to broadcast back.
- **Pydantic validation on PATCH**: `provider` is a `Literal["openai", "openrouter", "echo"]` — FastAPI returns 422 automatically for invalid values.
- **API key presence only**: The GET endpoint reports `openai_key_set` and `openrouter_key_set` as booleans — keys are never returned.
