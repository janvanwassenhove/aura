# Tasks: Operator Console (Spec 008)

**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)
**Status**: All tasks completed (retroactively documented 2026-05-01)

---

## Task List

### Phase 1 — Project Scaffold

- [x] **T-001** Initialise Vue 3 + Vite + TypeScript project in `apps/operator-console/`
- [x] **T-002** Add Pinia, TailwindCSS, Vitest to `package.json`
- [x] **T-003** Create `Dockerfile` (multi-stage: build → serve with `vite --host`)
- [x] **T-004** Add `operator-console` service to `infra/dev/docker-compose.yml`

### Phase 2 — WebSocket Composable

- [x] **T-005** Implement `useEventBusWs.ts` with connect/reconnect (exponential backoff) and event dispatch
- [x] **T-006** Wire composable into `App.vue` `onMounted` hook
- [x] **T-007** Surface `wsStatus` (connecting / open / closed) in header indicator

### Phase 3 — Pinia Stores

- [x] **T-008** `robotStore.ts` — reactive `mode`, `behaviorState`, `speaking`, `motionLog` (last 10); `applyEvent()`
- [x] **T-009** `conversationStore.ts` — `turns`, `isProcessing`, `submitTurn()`, `applyEvent()`
- [x] **T-010** `eventStore.ts` — ring buffer (max 200), `filter` ref, `applyEvent()`
- [x] **T-011** `approvalStore.ts` — `pending` map, `applyEvent()` for `ApprovalRequested`, `grant()` / `deny()` REST actions

### Phase 4 — Panel Components

- [x] **T-012** `RobotPanel.vue` — mode badge (colour-coded), behavior state, motion log list
- [x] **T-013** `ConversationPanel.vue` — scrollable transcript, role labels, timestamps, tool call badges
- [x] **T-014** `EventLogPanel.vue` — filtered list, type-based text filter input, auto-scroll
- [x] **T-015** `ApprovalPanel.vue` — overlay modal, action name, Grant/Deny buttons, 30s countdown

### Phase 5 — Layout & App Shell

- [x] **T-016** `App.vue` — 3-column grid layout (`RobotPanel` | `ConversationPanel` | `EventLogPanel`), header with WS indicator and gear button
- [x] **T-017** `main.ts` — mount app with Pinia

### Phase 6 — Unit Tests

- [x] **T-018** `robotStore.test.ts` — mode transitions, badge colour computed, motion log FIFO (max 10)
- [x] **T-019** `conversationStore.test.ts` — addTurn, applyEvent ResponseDrafted, submitTurn (mock fetch OK + error)
- [x] **T-020** `eventStore.test.ts` — ring buffer capping at 200, filter computed, clear()
- [x] **T-021** `approvalStore.test.ts` — applyEvent ApprovalRequested enqueues, grant() posts to API, deny() posts to API

### Phase 7 — Acceptance Criteria Verification

- [x] **T-022** SC-001: Event log updates within 500ms — verified manually with robot-runtime running
- [x] **T-023** SC-002: Approval panel appears within 500ms of event — verified end-to-end
- [x] **T-024** SC-003: Console reconnects within 30s — verified by stopping robot-runtime
- [x] **T-025** SC-004: `npm run build` succeeds with 0 TypeScript errors — verified
- [x] **T-026** SC-005: All 4 Pinia store unit tests pass — `npm test` passes

---

## Notes

- `settingsStore.ts` added as part of Spec 013 (LLM Provider Switcher); not part of this spec's task list.
- `SettingsPanel.vue` component added as part of Spec 013.
- Streaming word-by-word response (US2 AC2) not yet implemented — AURA responses arrive as complete strings; streaming is a future enhancement.
- Event log filter (US3 AC3) is implemented as a `computed` filter on the full event list; it does not filter at the WebSocket level.
