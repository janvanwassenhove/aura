---
feature: "006-orchestrator-foundation"
status: "in-progress"
owner: "orchestrator"
priority: P1
risk: High
created: "2026-04-25"
---

# Feature Specification: Orchestrator Foundation

**Feature Branch**: `006-orchestrator-foundation`
**Created**: 2026-04-25
**Status**: In Progress
**Owner**: orchestrator
**Priority**: P1
**Risk**: High

## User Scenarios & Testing

### User Story 1 — Intent is Routed to the Correct Tool (Priority: P1)

When a user says "What meetings do I have tomorrow?", the orchestrator recognizes this as a calendar intent, calls the Calendar tool, and returns the answer.

**Why this priority**: Tool routing is the orchestrator's primary function. Without it, AURA cannot act.

**Independent Test**: Mock the CalendarConnector; POST text turn "What meetings do I have tomorrow?"; assert `ToolCallRequested(tool_name="list_calendar_events")` event is emitted.

**Acceptance Scenarios**:

1. **Given** user text "What meetings do I have tomorrow?", **When** orchestrator processes the turn, **Then** a `ToolCallRequested` event for `list_calendar_events` is emitted.
2. **Given** user text "Send a Teams message to Alice saying I'll be late", **When** orchestrator processes the turn, **Then** an `ApprovalRequested` event is emitted before `ToolCallRequested`.
3. **Given** a tool call succeeds, **When** the tool result is received, **Then** a `ToolCallSucceeded` event is emitted and the response is passed back to the conversation runtime.
4. **Given** a tool call fails (timeout or connector error), **When** the failure occurs, **Then** a `ToolCallFailed` event is emitted and the orchestrator returns a graceful fallback response.

---

### User Story 2 — Approval Gate Blocks Sensitive Actions (Priority: P1)

Actions that write or send data (send email, post Teams message, create calendar event) require explicit user approval before the tool is called.

**Why this priority**: Safety is a first-class requirement. The approval gate must be correct before any write operations are wired up.

**Independent Test**: Set `REQUIRE_APPROVAL_FOR=send_mail,post_teams_message`; attempt to send a mail; assert `ApprovalRequested` event is emitted and the tool is NOT called until `ApprovalGranted` is received.

**Acceptance Scenarios**:

1. **Given** an action in the approval-required list, **When** the orchestrator plans to execute it, **Then** `ApprovalRequested` is emitted and execution is paused.
2. **Given** an `ApprovalGranted` event is received, **When** matching the pending approval, **Then** the tool call proceeds.
3. **Given** an `ApprovalDenied` event is received, **When** matching the pending approval, **Then** the tool call is cancelled and AURA informs the user.
4. **Given** an approval timeout (30 seconds), **When** no response is received, **Then** the action is auto-cancelled and the user is notified.
5. **Given** AURA is in HOME mode, **When** a WORK-only tool (send_mail) is requested, **Then** the request is rejected with a clear mode-mismatch error.

---

### User Story 3 — Persona Manager Applies the Correct Persona (Priority: P1)

AURA responds differently based on the active persona. Work mode is concise and formal; home mode is warm and conversational; demo mode is expressive.

**Why this priority**: Personas shape every response. The system prompt must change based on persona before any real interactions.

**Independent Test**: Switch to home persona; send a greeting; assert the system prompt in the LLM call contains the home persona instructions.

**Acceptance Scenarios**:

1. **Given** persona=work, **When** the orchestrator constructs the system prompt, **Then** the prompt contains work persona instructions and the work tool list.
2. **Given** persona=home, **When** the orchestrator constructs the system prompt, **Then** the prompt contains home persona instructions and a different (home) tool list.
3. **Given** persona changes from work to demo, **When** the next turn begins, **Then** the new persona prompt is used immediately.
4. **Given** silent_desk persona, **When** any audio input is received, **Then** AURA does not respond via voice (text-only responses).

---

### User Story 4 — Context Builder Constructs Prompt Correctly (Priority: P1)

The context builder assembles a complete LLM prompt from: system prompt (persona), tool definitions, session history, and current turn.

**Why this priority**: Correct prompt construction is critical to response quality and cost control.

**Independent Test**: Build context for a session with 5 turns and persona=work; assert prompt includes system prompt, last 5 turns, and all work-mode tool definitions.

**Acceptance Scenarios**:

1. **Given** a session with 10 turns, **When** context is built with `max_turns=5`, **Then** only the last 5 turns appear in the prompt.
2. **Given** persona=work, **When** context is built, **Then** the work tool list (M365 tools) is included and home-only tools are excluded.
3. **Given** memory service has relevant todos and reminders, **When** context is built, **Then** a memory digest is included in the system context.

---

### Edge Cases

- What happens when the LLM returns multiple tool calls? → Execute in sequence; emit separate `ToolCallRequested` events; collect all results before final response.
- What happens when the tool list exceeds the LLM context window? → Tool descriptions are summarized; full definitions available on demand.
- What happens when a connector is unavailable? → `ToolCallFailed` is emitted; orchestrator generates a "service unavailable" response.
- What happens when approval is pending and a new turn arrives? → New turn is queued; existing approval is cancelled and user is notified of the interruption.

---

## Requirements

### Functional Requirements

- **FR-001**: `Orchestrator` MUST expose `POST /orchestrate` accepting a turn and returning a response.
- **FR-002**: `IntentRouter` MUST map intents to tools using a configurable intent-to-tool mapping.
- **FR-003**: `ApprovalManager` MUST gate all tools listed in `shared-policies.APPROVAL_REQUIRED`.
- **FR-004**: `ApprovalManager` MUST auto-cancel pending approvals after a configurable timeout (default: 30s).
- **FR-005**: `PersonaManager` MUST return the correct system prompt and tool list for each of the 5 personas.
- **FR-006**: `ContextBuilder` MUST include: system prompt, tool definitions, session history (last N turns), memory digest.
- **FR-007**: `ContextBuilder` MUST enforce `max_context_turns` (default: 10) to limit token usage.
- **FR-008**: Orchestrator MUST emit `ToolCallRequested`, `ToolCallSucceeded`, `ToolCallFailed`, `ApprovalRequested`, `ApprovalGranted`, `ApprovalDenied` events.
- **FR-009**: Mode-based access control MUST prevent work-mode tools from running in home mode and vice versa.
- **FR-010**: Orchestrator MUST NOT import Reachy SDK types or call `robot-runtime` directly.

### Key Entities

- **Orchestrator**: Top-level service coordinating intent routing, approval, and response generation.
- **IntentRouter**: Maps recognized intents to connector tools.
- **ApprovalManager**: Approval gate with pending state and timeout.
- **PersonaManager**: Returns per-persona system prompts and tool lists.
- **ContextBuilder**: Assembles the LLM prompt from all context sources.
- **Policy**: From `shared-policies` — defines which tools require approval and which are mode-restricted.

---

## Success Criteria

### Measurable Outcomes

- **SC-001**: Calendar intent routing test passes with mocked connector.
- **SC-002**: All 5 approval scenarios (request, grant, deny, timeout, mode-mismatch) pass.
- **SC-003**: All 5 persona system prompts are tested and distinct.
- **SC-004**: Context building with `max_turns=5` produces a prompt under 4096 tokens for typical sessions.
- **SC-005**: Orchestrator processes a text turn end-to-end in < 200ms excluding LLM latency.

---

## Assumptions

- The LLM is OpenAI GPT-4o (or compatible) in the initial implementation.
- Tool definitions are Pydantic models that auto-generate OpenAI function-call schemas.
- The approval UI is the operator console; automated tests use a mock approver that auto-grants/denies.
- `shared-policies` defines the static approval-required list; dynamic policies are out of scope.

---

## References

- [Constitution](.specify/memory/constitution.md) — Principle IV (Safety Gates), Principle VII (Simplicity)
- [ADR-002](docs/adr/ADR-002-event-model.md)
- [ADR-006](docs/adr/ADR-006-m365-connector.md)
- [Spec 005 — Conversation Runtime](../005-conversation-runtime/spec.md)
- [Spec 010 — Connector Skeletons](../010-connector-skeletons/spec.md)
