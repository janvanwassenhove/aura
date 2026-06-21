# Implementation Plan: Operator Console (Spec 008)

**Spec**: [spec.md](spec.md)
**Status**: Implemented (plan retroactively documented 2026-05-01)
**Risk**: Low

---

## Technical Decisions

### TD-001 — Framework: Vue 3 + Vite + Pinia + TailwindCSS

As specified. All tooling confirmed working. TypeScript throughout with strict mode enabled.

### TD-002 — WebSocket via Composable

A single `useEventBusWs` composable (`src/composables/useEventBusWs.ts`) connects to the backend event bus WebSocket. It handles:
- Exponential backoff reconnect (100ms → 30s cap)
- State (`connecting` / `open` / `closed`) surfaced as a reactive ref
- Incoming events dispatched to the appropriate Pinia store via `applyEvent()`

### TD-003 — Pinia Stores

Four stores as specified:
- `robotStore` — robot mode, behavior state, speaking flag, motion log (last 10)
- `conversationStore` — turns (user + assistant), processing flag, submit action
- `eventStore` — all bus events with type-based filter; ring buffer capped at 200 events
- `approvalStore` — pending approval requests; Grant/Deny actions via REST POST

### TD-004 — Approval Panel via REST

Approval responses (`ApprovalGranted` / `ApprovalDenied`) are posted to `POST /orchestrator/approval/{request_id}` rather than emitting a bus event from the console. This avoids a round-trip through the WebSocket for a latency-sensitive action.

### TD-005 — Conversation Turn via conversation-runtime

Text turns are submitted to `POST /conversation/turn` on the conversation-runtime service (port 8002), not the orchestrator directly. The conversation-runtime handles session management and forwards to the orchestrator.

### TD-006 — Event Bus WebSocket Endpoint

Console connects to `ws://localhost:8001/ws/events` (robot-runtime broadcasts all bus events). URL is configurable via `VITE_WS_URL` env var.

---

## Component Structure

```
apps/operator-console/src/
  App.vue                       ← Root layout: header + 3-column grid
  main.ts                       ← Pinia + app mount
  components/
    RobotPanel.vue              ← Robot mode badge, behavior state, motion log
    ConversationPanel.vue       ← Transcript scroll + text input form
    EventLogPanel.vue           ← Filterable event log ring buffer
    ApprovalPanel.vue           ← Approval modal overlay
    SettingsPanel.vue           ← LLM config modal (Spec 013)
  stores/
    robotStore.ts               ← RobotState, mode, behavior, motions
    conversationStore.ts        ← Turns, submitTurn(), applyEvent()
    eventStore.ts               ← Events list, filter ref
    approvalStore.ts            ← Pending approvals, grant/deny actions
    settingsStore.ts            ← LLM config (Spec 013)
  composables/
    useEventBusWs.ts            ← WebSocket connect/reconnect/dispatch
```

---

## Test Strategy

### Unit Tests (Vitest)
- `tests/stores/robotStore.test.ts` — mode transitions, badge colours, motion log
- `tests/stores/conversationStore.test.ts` — addTurn, applyEvent, submitTurn mock fetch
- `tests/stores/eventStore.test.ts` — ring buffer capping, filter, applyEvent dispatch
- `tests/stores/approvalStore.test.ts` — applyEvent ApprovalRequested, grant/deny actions

### Manual / Integration
- WebSocket reconnect verified by stopping robot-runtime and confirming "Reconnecting…" banner
- Approval flow verified end-to-end with a tool call trigger

---

## Complexity Tracking

No unexpected complexity encountered. All components are straightforward Vue SFCs backed by Pinia stores. The WebSocket composable is the most complex piece (~60 lines) but is self-contained.

---

## Files Touched

| File | Action |
|------|--------|
| `apps/operator-console/src/App.vue` | Created |
| `apps/operator-console/src/main.ts` | Created |
| `apps/operator-console/src/components/RobotPanel.vue` | Created |
| `apps/operator-console/src/components/ConversationPanel.vue` | Created |
| `apps/operator-console/src/components/EventLogPanel.vue` | Created |
| `apps/operator-console/src/components/ApprovalPanel.vue` | Created |
| `apps/operator-console/src/stores/robotStore.ts` | Created |
| `apps/operator-console/src/stores/conversationStore.ts` | Created |
| `apps/operator-console/src/stores/eventStore.ts` | Created |
| `apps/operator-console/src/stores/approvalStore.ts` | Created |
| `apps/operator-console/src/composables/useEventBusWs.ts` | Created |
| `apps/operator-console/tests/stores/*.test.ts` | Created (4 files) |
| `apps/operator-console/package.json` | Created |
| `apps/operator-console/vite.config.ts` | Created |
| `apps/operator-console/Dockerfile` | Created |
