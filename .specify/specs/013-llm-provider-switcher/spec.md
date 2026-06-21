---
description: "Runtime LLM provider and model switcher — operator console UI + orchestrator config API"
---

# Feature Specification: LLM Provider Switcher

**Feature Branch**: `013-llm-provider-switcher`
**Created**: 2026-04-29
**Status**: Implemented
**Owner**: TBD
**Priority**: P2
**Risk**: Low
**Input**: User request — switch LLM provider/model from the operator console without restarting containers

## Background

The orchestrator currently reads `LLM_PROVIDER`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `GEMINI_API_KEY`, and `GEMINI_MODEL` from environment variables at container start. Changing provider or model requires stopping and restarting the orchestrator container. Operators need to switch without a restart — especially when testing free vs paid models.

**Amendment (2026-05-01)**: Gemini (Google `google-genai` SDK) was added as a first-class provider alongside OpenAI and OpenRouter. This extension follows the same pluggable pattern as the original providers and required no structural changes — only an additional branch in `llm.py`, an additional env var (`GEMINI_API_KEY` / `GEMINI_MODEL`), and UI additions to the Settings panel.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Operator switches LLM provider at runtime (Priority: P1)

As an operator, I want to change the active LLM provider and model from the console UI without restarting the orchestrator, so I can quickly switch between OpenAI, OpenRouter, Gemini, and echo mode.

**Why this priority**: Core pain point — the primary ask that triggered this spec.

**Independent Test**: Open the operator console Settings panel, change provider to `echo`, send a message — the reply must begin with `[echo]`. Change back to `openrouter`, send again — the reply must NOT begin with `[echo]`.

**Acceptance Scenarios**:

1. **Given** the orchestrator is running with `LLM_PROVIDER=openai`, **When** the operator selects `openrouter` + `openai/gpt-oss-120b:free` in the Settings panel and clicks Apply, **Then** the next chat turn is routed through OpenRouter.
2. **Given** the orchestrator is running, **When** the operator selects `echo` provider, **Then** all subsequent replies begin with `[echo]`.
3. **Given** the operator selects `gemini` + `gemini-2.5-flash` in the Settings panel and clicks Apply, **Then** the next chat turn is routed through Gemini (Google `google-genai` SDK).
4. **Given** the operator has switched provider, **When** they reload the console page, **Then** the Settings panel reflects the current active provider/model as reported by the orchestrator.
5. **Given** an invalid model string is entered, **When** Apply is clicked, **Then** the UI shows an inline error and the previous provider remains active.

---

### User Story 2 — Settings panel shows current LLM config (Priority: P1)

As an operator, I want the Settings panel to always display the currently active provider and model, so I know exactly what the orchestrator is using.

**Why this priority**: Without this, the switcher is hard to trust.

**Independent Test**: Hit `GET /orchestrator/config/llm` directly with curl/Invoke-RestMethod — it must return the current provider and model. Verify the panel reflects the same values on load.

**Acceptance Scenarios**:

1. **Given** the orchestrator started with `LLM_PROVIDER=openrouter` and `OPENROUTER_MODEL=openai/gpt-oss-20b:free`, **When** the console loads, **Then** the Settings panel shows provider `openrouter` and model `openai/gpt-oss-20b:free`.
2. **Given** the provider was changed via the API, **When** the operator opens the Settings panel, **Then** the current values are fetched fresh from the orchestrator.

---

### Edge Cases

- OpenRouter key not set in env → UI shows warning "OPENROUTER_API_KEY not configured" when openrouter is selected.
- OpenAI key not set → similar warning for openai.
- Gemini key not set → UI shows warning "GEMINI_API_KEY not configured" when gemini is selected.
- Orchestrator unreachable → Settings panel shows "Could not connect to orchestrator".
- Empty model string → validation rejects before API call.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Orchestrator MUST expose `GET /orchestrator/config/llm` returning `{provider, model, openai_key_set, openrouter_key_set, gemini_key_set}`.
- **FR-002**: Orchestrator MUST expose `PATCH /orchestrator/config/llm` accepting `{provider, model}` and updating the runtime config immediately; returns 200 on success.
- **FR-003**: The in-process LLM config state MUST be used by `openai_chat()` for every call after `PATCH` — no restart needed.
- **FR-004**: `llm.py` MUST read provider/model from the runtime config object rather than `os.environ` on every call.
- **FR-005**: The operator console MUST have a Settings panel (gear icon, top-right area) with provider dropdown and model input.
- **FR-006**: The Settings panel MUST fetch current config on open and display it.
- **FR-007**: The Settings panel MUST show a status badge (green = configured, red = missing) per provider based on whether the API key env var is set.
- **FR-008**: PATCH result MUST be surfaced as a success/error message in the console.
- **FR-009**: Orchestrator MUST expose `GET /orchestrator/config/llm/models?provider=<p>` returning available models for the given provider (with free/paid classification for OpenRouter).
- **FR-010**: The Settings panel MUST populate a model selector with dynamic models fetched from FR-009 when a provider is selected.

### Key Entities

- **LLMConfig**: `{provider: "openai" | "openrouter" | "gemini" | "echo", model: str}` — runtime mutable config object in orchestrator process.
- **LLMConfigResponse**: `{provider, model, openai_key_set: bool, openrouter_key_set: bool, gemini_key_set: bool}` — GET response schema.
- **LLMConfigUpdate**: `{provider, model}` — PATCH request body.

---

## Success Criteria *(mandatory)*

- **SC-001**: Switching from `openai` → `openrouter` in UI causes next turn to use OpenRouter — verified by orchestrator logs showing `provider=openrouter`.
- **SC-002**: Switching from `openai` → `gemini` in UI causes next turn to use Gemini — verified by orchestrator logs showing `provider=gemini`.
- **SC-003**: `GET /orchestrator/config/llm` returns 200 with correct provider/model after a `PATCH`.
- **SC-004**: Settings panel loads without errors and reflects the current orchestrator config.
- **SC-005**: `PATCH` with invalid provider returns 422.
- **SC-006**: `GET /orchestrator/config/llm/models?provider=gemini` returns a non-empty model list.
- **SC-007**: Unit tests cover: GET returns initial env config, PATCH updates config, `openai_chat` reads from runtime config not env on each call, Gemini branch is exercised.
