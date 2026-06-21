---
description: "Task list for spec 013 — LLM provider/model runtime switcher"
---

# Tasks: LLM Provider Switcher (013)

**Input**: `.specify/specs/013-llm-provider-switcher/plan.md` + `spec.md`
**Prerequisites**: plan.md ✓, spec.md ✓

---

## Phase 1: Orchestrator — Config Singleton

**Goal**: Decouple `llm.py` from `os.environ` so provider/model can change at runtime without restart.

- [x] T001 Create `services/orchestrator/src/orchestrator/config.py`
- [x] T002 Modify `services/orchestrator/src/orchestrator/llm.py`

**Checkpoint**: `llm.py` no longer caches env vars at module level — config is read from `config.py` on every call

---

## Phase 2: Orchestrator — Config REST Endpoints

**Goal**: Expose GET and PATCH endpoints for the runtime LLM config.

- [x] T003 Add `LLMConfigResponse` and `LLMConfigUpdate` Pydantic models inline in `services/orchestrator/src/orchestrator/routes.py`
- [x] T004 Add `GET /orchestrator/config/llm` route handler
- [x] T005 Add `PATCH /orchestrator/config/llm` route handler

**Checkpoint**: `curl localhost:8003/orchestrator/config/llm` returns JSON; PATCH updates it

---

## Phase 3: Orchestrator — Tests

**Goal**: Cover all spec SC-001–SC-005 acceptance criteria.

- [x] T006 [P] Add tests in `services/orchestrator/tests/test_llm_config.py`:
  - `GET /orchestrator/config/llm` returns env-initialised values
  - `PATCH` updates provider + model; subsequent `GET` returns new values
  - `PATCH` with invalid provider → 422
  - `openai_chat` with config `provider=echo` → echo path (regression check)

**Checkpoint**: `pytest services/orchestrator/tests/test_llm_config.py` — all pass

---

## Phase 4: Operator Console — Settings Store

**Goal**: Pinia store that wraps the two orchestrator config endpoints.

- [x] T007 Create `apps/operator-console/src/stores/settingsStore.ts`

**Checkpoint**: Store unit-testable in isolation (no component needed)

---

## Phase 5: Operator Console — Settings Panel UI

**Goal**: Gear icon + modal panel for switching provider/model.

- [x] T008 Create `apps/operator-console/src/components/SettingsPanel.vue`
- [x] T009 [P] Modify `apps/operator-console/src/App.vue`

**Checkpoint**: Open console → click gear → panel loads with current provider/model → change to echo → Apply → send message → reply starts with `[echo]`

---

## Dependencies & Execution Order

```
T001 → T002 (llm.py depends on config.py)
T002 → T003 → T004 → T005 (routes depend on config)
T005 → T006 (tests verify routes)
T007 → T008 → T009 (UI builds on store)
T006 and T007 can run in parallel (backend vs frontend)
```

## Notes

- [P] = no dependency on other in-flight tasks, can run in parallel
- Config is in-memory only — no migration, no DB change
- `LLMConfigUpdate.provider` is `Literal["openai", "openrouter", "echo"]` — FastAPI gives 422 for free
- API keys are NEVER returned by the GET endpoint — only boolean `key_set` flags
