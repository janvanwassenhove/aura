---
feature: "008-operator-console"
status: "implemented"
owner: "frontend"
priority: P1
risk: Medium
created: "2026-04-25"
amended: "2026-09-05"
units: [U28, U30, U36c, U38, U53, U63, U68, U72, U76, U77, U78, U79, U95,
        U98, U112, U113, U114, U115, U117, U119, U120, U122, U123, U124,
        U125, U187, U188, U216, U217, U222, U223, U252, U252c, U252e,
        U253b, U262]
---

# Feature Specification: Operator Console

**Feature Branch**: `008-operator-console`
**Created**: 2026-04-25
**Status**: Implemented — **see the 2026-09 amendment at the end**, which
describes the D2 design the console was rebuilt into.
**Owner**: frontend
**Priority**: P1 (raised from P2: it is the product's only surface)
**Risk**: Medium

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

- [Constitution](../../memory/constitution.md) — Principle III (Events Drive State)
- [Spec 003 — Event Bus](../003-event-bus-schemas/spec.md)
- [Spec 006 — Orchestrator](../006-orchestrator-foundation/spec.md)

---

# Amendment — 2026-09-05: the D2 console

*Retro-specified; see [015-spec-coverage](../015-spec-coverage/spec.md). The
April text is the record of the original plan and is left intact.*

## What changed in shape

The plan was an **operator's monitoring console**: panels that observe a
running system. What shipped is the product's **only surface** — the window a
household opens — and that changed the rules.

| April plan | What it is now | Why |
|---|---|---|
| Title-bar icons opening five full-screen modals | **One navigation rail**: Talk · People · Skills · Robot · Modes · Activity (+ Present), with About and Settings pinned below | Icon soup plus modals meant no two things could be seen at once, and nothing had a name (U252) |
| A passive event monitor | A place you *do* things: talk, teach a face, edit a memory, run a presentation | The owner is not an operator |
| Panels sized by the developer | A VS Code-like workspace: docked Brain panel, resizable panels, a bottom Events dock | (U76, U77) |
| One density | Three: **calm**, **standard**, **full**, and the choice follows the person he is talking to | A child and the owner do not need the same screen (U112–U115, U117) |
| Fixed theme | Light theme with a green accent as the default, both themes designed | (U193, U216) |

## Additional user stories

### User Story 4 — One surface, and the chips do not lie (Priority: P1)

1. **Given** any view, **When** it is shown, **Then** the capability chip row
   states what he may currently do, derived from the mode policy — not composed
   in the console (U252).
2. **Given** a persona list, **When** it is loaded, **Then** the console reads
   the brain's actual field names rather than guessing them. U252c: it guessed,
   and the list was empty.
3. **Given** Settings, **When** it opens, **Then** it loads. U252e/U253b: it
   loaded nothing, and screen control ignored the model the owner had chosen.
4. **Given** a status the brain owns, **When** the console shows it, **Then**
   it came from the brain. This spec's most-repeated defect class — U252c,
   U252e, U276, U278, U290, U297 — is the console showing a state the backend
   does not share.

### User Story 5 — Nothing is a dead end (Priority: P1)

1. **Given** a ✕ on a card, **When** it is pressed, **Then** something happens
   (U262 — it did not), and a typo can be corrected rather than being permanent
   (U262).
2. **Given** a long conversation, **When** the owner clears it, **Then** the
   transcript clears and the session — and his memory of it — stays (U187).
3. **Given** the brain needs restarting, **When** it does, **Then** the console
   says so unmissably rather than leaving the owner to wonder (U95, U98).
4. **Given** a robot that has gone quiet, **When** the status poll runs,
   **Then** it keeps the brain link alive rather than letting it rot (U79).

### User Story 6 — It is usable, and readable (Priority: P1)

1. **Given** the WCAG findings of the August audit, **When** the worst are
   addressed, **Then** contrast, focus states and keyboard paths meet them
   (U222, U216).
2. **Given** `prefers-reduced-motion`, **When** it is set, **Then** the graph
   and animations respect it (U217).
3. **Given** a narrow column, **When** the chat is used, **Then** the action
   buttons stay visible, sit above a full-width input, and the input grows with
   the text (U122, U123, U124).
4. **Given** any view, **When** it is scrolled, **Then** there is no horizontal
   scrollbar and no double scrollbar (U119, U120).
5. **Given** the interface, **When** it is read, **Then** it is in **one**
   language, and a destructive action uses a real confirm dialog (U223).

### User Story 7 — First run explains itself (Priority: P2)

1. **Given** a fresh install, **When** it starts, **Then** a wizard walks
   through the robot, the voice and the language, and can find the robot on the
   network (U30, U53).
2. **Given** an install that is clearly already configured, **When** the
   `SETUP_DONE` marker is missing, **Then** the wizard does **not** hijack it.

## Amended functional requirements

- **FR-101**: One navigation system. No modal may be the only route to a
  feature.
- **FR-102**: Every status, capability and knowledge state displayed is
  supplied by the brain. The console composes presentation, never truth.
- **FR-103**: Density (`calm` | `standard` | `full`) is a first-class setting
  and follows the active person.
- **FR-104**: Both light and dark themes are designed; tokens are defined once
  and never only inside a media query.
- **FR-105**: There is **no `vue-tsc`**: esbuild strips types unchecked, so a
  type error surfaces at runtime in front of the owner. Mount tests are the
  only defence, and a store or view change ships with one.
- **FR-106**: The overlay window has its own Pinia store; anything the two
  windows must agree on crosses through an explicit channel (a `storage` event
  or the brain), never by assumption.

## Traceability

| Units | What they delivered |
|---|---|
| U28 | The event pass — the console consumes the bus |
| U30, U53 | The setup wizard and in-app onboarding with robot discovery |
| U36c, U38, U78, U79 | Embodied conversation and the MJPEG stream; voice input, recognition and motion-log fixes; the avatar in the conversation; the status poll that keeps the link alive |
| U63, U68, U72, U117 | Person portrait and skill references; the brain vault with `[[wikilinks]]` and backlinks; the skills library and per-person brain; scalable facts and lean settings |
| U76, U77 | The VS Code-like workspace; the bottom Events dock and per-person sources |
| U95, U98 | "Restart brain" — the button, then the banner nobody could miss |
| U112, U113, U114, U115, U119, U120, U122, U123, U124, U125 | The design passes: brain tabs, compact robot state, a quiet event log, scrollbars, chat buttons, the auto-growing input, the Robot State redesign |
| U187, U188 | Clearing the conversation without losing the session; the laggy video fixed at its cause |
| U216, U217, U222, U223 | Missing design tokens and contrast; audit quick wins and reduced motion; the worst WCAG findings; one language and a real confirm dialog |
| U252, U252c, U252e, U253b | One surface and honest capability chips; the guessed field names; Settings that loaded nothing |
| U262 | The cross that did nothing, and the typo that was forever |
