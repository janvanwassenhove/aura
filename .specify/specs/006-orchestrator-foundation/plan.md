---
spec: "006-orchestrator-foundation"
status: draft
created: 2025-01-01
---

# 006 — Orchestrator Foundation: Implementation Plan

## Summary

Implement the orchestrator service: intent routing, approval gate, persona management, and context building. This is the central coordinator — all tool calls flow through it.

## Technical Context

- `IntentRouter` — maps LLM tool calls to connector-service endpoints
- `ApprovalManager` — gates sensitive actions; auto-cancels after 30 seconds; emits events
- `PersonaManager` — returns active persona config and system prompt
- `ContextBuilder` — assembles full LLM prompt from system prompt + memory digest + session turns + tool schemas
- Mode-based access control: checked before `IntentRouter` routes
- Policies imported from `shared-policies`

## Constitution Check

| Principle | Gate | Status |
|-----------|------|--------|
| Safety Gates | `ApprovalManager` called for every APPROVAL_REQUIRED tool | ✅ |
| Spec-First | Approval flow fully designed before any code | ✅ |
| No Sensitive Data in Logs | Tool arguments never logged; only `tool_name` is logged | ✅ |
| Hardware Abstraction | Orchestrator never imports Reachy SDK types | ✅ |

## Project Structure

```
services/orchestrator/src/orchestrator/
├── main.py                # FastAPI routes
├── router.py              # IntentRouter — maps tool names to connector endpoints
├── approval.py            # ApprovalManager — pending dict, timeout tasks
├── persona.py             # PersonaManager — active persona config
├── context.py             # ContextBuilder — assembles full LLM prompt dict
└── pipeline.py            # orchestrate(request) — main flow
```

## Implementation Steps

### Phase 1: IntentRouter

```python
class IntentRouter:
    def route(self, tool_name: str, tool_args: dict) -> str:
        """Returns the connector-service URL to POST to."""
```

Tool-to-endpoint map (hardcoded in Phase 1; config-driven later):
- `list_calendar_events_today` → `GET /calendar/today`
- `get_unread_mail` → `GET /mail/unread`
- `post_teams_message` → `POST /teams/message`
- `send_mail` → `POST /mail/send`
- `list_tasks` → `GET /tasks`
- `create_task` → `POST /tasks`

### Phase 2: ApprovalManager

```python
class ApprovalManager:
    async def request_approval(self, tool_name: str, session_id: str) -> bool:
        """Emits ApprovalRequested, waits for grant/deny or timeout. Returns True if granted."""
    async def grant(self, approval_id: UUID) -> None
    async def deny(self, approval_id: UUID) -> None
```

- Pending approvals stored in `dict[UUID, asyncio.Future]`
- `asyncio.create_task` for 30-second timeout that resolves future with `False`
- `grant()` resolves future with `True`; `deny()` resolves with `False`
- Emit `ApprovalGranted` or `ApprovalDenied` after resolution

### Phase 3: ContextBuilder

```python
class ContextBuilder:
    async def build(self, session_id: str, persona: Persona) -> dict:
        """Returns OpenAI chat messages list + tools list."""
```

Steps:
1. Get session turns from memory-service
2. Get todos + reminders from memory-service → render with `render_memory_digest()`
3. Get persona system prompt from `PersonaManager`
4. Filter tool schemas by `MODE_TOOL_MAP[persona]`
5. Return `{"messages": [...], "tools": [...]}`

### Phase 4: Main Pipeline

```python
async def orchestrate(text: str, session_id: str) -> str:
    context = await context_builder.build(session_id, active_persona)
    messages = context["messages"] + [{"role": "user", "content": text}]
    response = await openai.chat.completions.create(messages=messages, tools=context["tools"])
    if response has tool_call:
        tool_name = response.tool_call.name
        if tool_name not in MODE_TOOL_MAP[active_persona]:
            return "I can't do that in the current mode."
        if tool_name in APPROVAL_REQUIRED:
            granted = await approval_manager.request_approval(tool_name, session_id)
            if not granted:
                return "Approval denied or timed out."
        result = await intent_router.call(tool_name, tool_call.args)
        # append tool result, make second LLM call for final response
    return final_text
```

### Phase 5: REST Routes

- `POST /orchestrate` — `{"text": str, "session_id": str?}` → `{"response": str, "session_id": str}`
- `POST /approval/{id}/grant`
- `POST /approval/{id}/deny`
- `WebSocket /ws/events` — connected to event bus broadcaster

### Phase 6: Tests

1. `test_approval_gate_blocks_sensitive_tool` — tool in APPROVAL_REQUIRED → ApprovalRequested emitted
2. `test_approval_granted_allows_tool_call` — grant() → tool called
3. `test_approval_timeout_cancels_call` — no response for 30s → ApprovalDenied emitted, call blocked
4. `test_mode_access_control` — home persona cannot call `send_mail`
5. `test_orchestrate_text_turn` — end-to-end with mock LLM

## Complexity Tracking

- Python files: ~8 files, ~500 lines
- This is the highest complexity service (spec marked High risk)
