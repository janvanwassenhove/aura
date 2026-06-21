---
feature: "008-operator-console"
status: "in-progress"
owner: "frontend"
priority: P2
risk: Low
created: "2026-04-25"
---

# Feature Specification: Operator Console

**Feature Branch**: `008-operator-console`
**Created**: 2026-04-25
**Status**: In Progress
**Owner**: frontend
**Priority**: P2
**Risk**: Low

## User Scenarios & Testing

### User Story 1 — Robot Status Panel Shows Live State (Priority: P2)

The operator console shows the current robot mode, behavior state, and uptime in real time, updating without page refresh.

**Why this priority**: Essential for the developer inner loop and for demos. Visual state feedback is required for all other features to be testable without reading logs.

**Independent Test**: Start FakeRobot; open console; trigger a motion; assert the motion log panel shows the event within 500ms.

**Acceptance Scenarios**:

1. **Given** the console is open and connected, **When** robot mode changes to DEGRADED, **Then** the state badge updates within 500ms.
2. **Given** a motion is executing, **When** viewed in the console, **Then** the current motion name is visible in the robot panel.
3. **Given** AURA is speaking, **When** viewed in the console, **Then** the speaking indicator is active and the transcript text is visible.

---

### User Story 2 — Conversation Panel Shows Transcript (Priority: P2)

All conversation turns (user and AURA) are displayed in a scrollable transcript panel with timestamps.

**Independent Test**: Send 3 text turns via the console input; assert all 6 entries (3 user + 3 AURA) appear in the transcript panel.

**Acceptance Scenarios**:

1. **Given** a completed turn, **When** viewed in the console, **Then** both the user message and AURA response are visible with role labels and timestamps.
2. **Given** a streaming response, **When** AURA is generating text, **Then** the text streams into the panel word-by-word.
3. **Given** a tool call occurred, **When** viewed in the console, **Then** the tool name and status (approved/denied/succeeded/failed) are visible inline.

---

### User Story 3 — Event Log Shows System Events (Priority: P2)

A scrollable event log panel shows all bus events with type, timestamp, and key payload fields.

**Independent Test**: Emit 10 events; assert all 10 appear in the event log panel in order.

**Acceptance Scenarios**:

1. **Given** an event is published on the bus, **When** viewed in the event log, **Then** the event type, session_id, and timestamp are displayed.
2. **Given** a high event rate, **When** events arrive faster than 10/second, **Then** the log buffers and displays them without freezing.
3. **Given** the filter input, **When** a user types "Robot", **Then** only events with "Robot" in the type are shown.

---

### User Story 4 — Approval Requests Are Actionable (Priority: P2)

When AURA requests approval for a sensitive action, an approval panel appears in the console for the operator to grant or deny.

**Independent Test**: Trigger a `POST /teams/message` action; assert the approval panel appears with action details and Grant/Deny buttons.

**Acceptance Scenarios**:

1. **Given** an `ApprovalRequested` event is received, **When** viewed in the console, **Then** a modal or panel shows the action name, description, and Grant/Deny buttons.
2. **Given** the Grant button is clicked, **When** the action is approved, **Then** `ApprovalGranted` event is sent to the backend.
3. **Given** the Deny button is clicked, **When** the action is denied, **Then** `ApprovalDenied` event is sent and the panel closes.
4. **Given** the approval times out (30 seconds), **When** the timeout occurs, **Then** the approval panel closes automatically.

---

### User Story 5 — Text Input Allows Simulated Conversations (Priority: P2)

A developer can type text in the console and submit it as a conversation turn, receiving AURA's response in the transcript.

**Independent Test**: Type "Hello AURA" in the text input; press Submit; assert AURA response appears in the transcript within 5 seconds.

**Acceptance Scenarios**:

1. **Given** a developer types text and presses Submit, **When** the turn is submitted, **Then** the text appears as a user turn and AURA's response appears after processing.
2. **Given** a text turn is in progress, **When** the Submit button is pressed again, **Then** the button is disabled until the current turn completes.

---

### Edge Cases

- What happens when the WebSocket disconnects? → Console shows a "Reconnecting..." banner; event log pauses.
- What happens when events arrive out of order? → Events are sorted by timestamp before display.

---

## Requirements

### Functional Requirements

- **FR-001**: Console MUST connect to the backend via WebSocket on startup.
- **FR-002**: Robot state panel MUST display: mode, behavior state, speaking indicator, motion log (last 10).
- **FR-003**: Conversation panel MUST display all turns in order with role, text, and timestamp.
- **FR-004**: Event log MUST display all bus events; support type-based text filtering.
- **FR-005**: Approval panel MUST appear on `ApprovalRequested` events and support Grant/Deny actions.
- **FR-006**: Text input MUST submit turns to `POST /conversation/turn` and display results.
- **FR-007**: Console MUST reconnect automatically on WebSocket disconnect (exponential backoff, max 30s).
- **FR-008**: Console MUST be buildable with `npm run build` and serveable as static files.

### Technology

- Vue 3 + Vite + TypeScript + Pinia + TailwindCSS
- WebSocket composable for real-time events
- Pinia stores: `robotStore`, `conversationStore`, `eventStore`, `approvalStore`

---

## Success Criteria

### Measurable Outcomes

- **SC-001**: Event log updates within 500ms of event emission.
- **SC-002**: Approval panel appears within 500ms of `ApprovalRequested` event.
- **SC-003**: Console reconnects automatically within 30 seconds of WebSocket drop.
- **SC-004**: `npm run build` succeeds with 0 TypeScript errors.
- **SC-005**: All 4 Pinia stores have unit tests covering state transitions.

---

## Assumptions

- The console is for operators/developers; it does not need authentication in the initial version.
- The console communicates with `robot-runtime` and `orchestrator` services directly via WebSocket and REST.
- Mobile/responsive design is not required for the initial version.

---

## References

- [Constitution](.specify/memory/constitution.md) — Principle III (Events Drive State)
- [Spec 003 — Event Bus](../003-event-bus-schemas/spec.md)
- [Spec 006 — Orchestrator](../006-orchestrator-foundation/spec.md)
