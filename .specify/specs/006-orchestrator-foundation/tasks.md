---
spec: "006-orchestrator-foundation"
plan: "006-orchestrator-foundation"
status: in-progress
created: "2026-04-25"
---

# 006 — Orchestrator Foundation: Tasks

## Task Group 1: Pipeline

- [x] **T-006-01** Create `orchestrator/pipeline.py` — `orchestrate(text, session_id)` async function
  - Builds context via `ContextBuilder`
  - Calls LLM (same `LLM_PROVIDER` env var as conversation-runtime)
  - Handles tool calls: check mode, check approval, route to connector-service
  - Emits `ToolCallRequested`, `ToolCallSucceeded`, `ToolCallFailed` events
  - Returns `str` response text

- [x] **T-006-02** Add `POST /orchestrator/turn` route
  - Body: `{"text": str, "session_id": str}`
  - Returns: `{"reply": str, "session_id": str}`
  - Calls `pipeline.orchestrate()`

- [x] **T-006-03** Wire `ContextBuilder.build()` to memory-service
  - Add `MEMORY_SERVICE_URL` env var; inject `httpx.AsyncClient`
  - `build_context()` fetches last N turns from `/memory/turns/{session_id}`
  - `build_tool_list()` filters by `MODE_TOOL_MAP[persona]`

- [x] **T-006-04** Tool-to-connector routing in `IntentRouter`
  - Add `CONNECTOR_SERVICE_URL` env var
  - `route(tool_name, args)` → POST `{connector_url}/{endpoint}` via httpx
  - Tool map: `list_calendar_events_today→GET /calendar/today`, `get_unread_mail→GET /mail/unread`, etc.

## Task Group 2: Approval Gate

- [x] **T-006-05** Complete `ApprovalManager.grant()` / `deny()` (already exists, verify events are emitted)
- [x] **T-006-06** Add approval timeout auto-cancel in pipeline — catch `ApprovalTimeout`, return graceful message

## Task Group 3: Tests

- [x] **T-006-07** `tests/test_pipeline.py` — orchestrate() with `LLM_PROVIDER=echo`
  - Assert reply returned, no crash
  - Assert `ToolCallRequested` emitted when LLM requests a tool (mock tool call response)

- [x] **T-006-08** `tests/test_approval.py` — ApprovalManager unit tests
  - request → grant → resolved True
  - request → deny → `ApprovalDeniedError`
  - request → timeout → `ApprovalTimeout`

- [x] **T-006-09** `tests/test_intent_router.py` — IntentRouter mode filtering
  - Allowed tool in mode → routed
  - Disallowed tool → `PermissionError`
