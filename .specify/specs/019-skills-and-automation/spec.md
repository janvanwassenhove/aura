---
feature: "019-skills-and-automation"
status: "implemented"
owner: "orchestrator"
priority: P1
risk: High
created: "2026-09-05"
units: [U40, U43, U50, U57, U58, U59, U60, U61, U62, U64, U65, U66, U70, U71,
        U74, U75, U107, U108, U110, U118, U159, U194, U195, U247, U248, U249,
        U250, U251, U253c, U259, U259b, U261, U296]
---

# Feature Specification: Skills, Automation and the Agentic Loop

**Feature Branch**: `019-skills-and-automation`
**Created**: 2026-09-05 (retro-specified — see [015-spec-coverage](../015-spec-coverage/spec.md))
**Status**: Implemented
**Owner**: orchestrator (`pipeline.py`, `skills.py`, `skill_optimizer.py`, `skill_review.py`, `hooks.py`, `laptop_tools.py`, `unblocks.py`, `approval_manager.py`)
**Priority**: P1
**Risk**: **High.** This is the part that can act on the world — run a
PowerShell command, drive the mouse, open an app, send something. Everything
here is downstream of constitution IV: *safety gates are inviolable*.

## Background

The orchestrator started as one round: intent → maybe a tool → reply. U57 made
it a **multi-round reason/act loop** the owner can steer or stop mid-flight,
and U58 added a ladder of things it may reach for. Everything since has been
about two questions:

1. **What is it allowed to do?** — answered by the mode policy, the approval
   gate, and an allow-list.
2. **What did it actually do, and did that work?** — answered by the skill
   ledger, and this is where the interesting bugs were.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — He can be taught a procedure, and it sticks (Priority: P1)

**Acceptance Scenarios**:

1. **Given** the owner describes how they want something done, **When** they
   press Teach, **Then** the turn runs framed as a lesson and he decides
   whether it should become a skill — saved through the approval-gated
   `save_skill` tool (U59, U60).
2. **Given** a skill, **When** it is saved, **Then** it carries triggers (the
   phrases that should reach it) and a scope: everyone, a persona, or one
   person (U59, U64).
3. **Given** Teach is pressed, **When** anything happens or fails, **Then** the
   owner sees it. U296: the route returned the reply and the console threw it
   away, waiting for a WebSocket event; an empty box, a busy turn or a 503 each
   produced silence that looked exactly like a broken button.
4. **Given** a new skill, **When** it is created, **Then** it starts out
   polished rather than being optimised later (U118), and the "1 skill ready to
   optimize" state cannot get stuck forever on something already optimal
   (U159).

### User Story 2 — He improves his own procedures, from evidence (Priority: P2)

**Acceptance Scenarios**:

1. **Given** a skill has been used, **When** the loop reviews it, **Then** it
   reasons over what actually happened (U107, U108).
2. **Given** a turn the **system** started — a greeting, a presentation beat —
   **When** the ledger is written, **Then** it is not recorded as a use of a
   skill. U247: four of the seven recorded "uses" of the Spotify skill on the
   owner's machine were the robot saying hello, and a learning loop fed that
   evidence rewrites a procedure from the wrong material.
3. **Given** a turn has finished, **When** the ledger line is written, **Then**
   it is written **afterwards**, carrying the outcome. It used to be written
   before the turn ran, carrying only the intention — so *"add guardrails for
   the failure cases implied by the evidence"* was asked of evidence that
   contained no failures (U247).
4. **Given** the loop finds no suitable skill, **When** it does, **Then** it
   drafts one and raises it rather than silently improvising (U250), as a
   proposal that waits for one click (U251).

### User Story 3 — He does not promise; he answers (Priority: P1)

**Acceptance Scenarios**:

1. **Given** a request he can fulfil, **When** he replies, **Then** he does the
   thing rather than announcing that he will (U248 — *a promise is not an
   answer*), and the guard recognises the promise in every language he speaks
   (U261: he promised again, in words the guard did not know).
2. **Given** something he genuinely cannot do, **When** he says so, **Then**
   the refusal is real rather than invented, and no skill hands him a
   ready-made excuse (U253c).
3. **Given** a capability he needs but does not have, **When** he needs it,
   **Then** he can **ask to be unblocked** — `request_capability` is always
   available, and granting it takes effect immediately rather than after a
   restart (U249).

### User Story 4 — Acting on the laptop is gated, visible and stoppable (Priority: P1)

**Acceptance Scenarios**:

1. **Given** a tool that touches the outside world, **When** it is called,
   **Then** the approval gate stops and asks, per `shared-policies`
   (constitution IV). "Always allow" is remembered per action (U48).
2. **Given** screen control, **When** it runs, **Then** an overlay shows that
   it is happening and offers an abort (U75), and it can be stopped mid-flight
   (U62).
3. **Given** an app launch, **When** it is requested, **Then** it comes from an
   allow-list (U40).
4. **Given** computer use, **When** it drives the screen, **Then** it works
   against real scaling and a real display, and can track what it is doing via
   the screen (U70) — the first version was gated (U50) and did not survive
   contact with a real monitor.
5. **Given** the automation ladder, **When** a task needs it, **Then** the
   cheapest rung is used first: a direct tool, then PowerShell or file access,
   then git preparation, then the screen (U58, U43, U194, U195).

### User Story 5 — He can look things up (Priority: P2)

1. **Given** a question about the world, **When** it is asked, **Then** he can
   search and read a page (U259) — `web_search` and `read_url` are always
   available, like `request_capability`.
2. **Given** a search model that no longer exists, **When** he searches,
   **Then** he works out which one still does rather than failing (U259b).

### User Story 6 — He can start something himself (Priority: P3)

1. **Given** a reminder or a daily briefing, **When** its time comes, **Then**
   he speaks unprompted (U110) — and Quiet mode still silences him
   ([017](../017-voice-and-language/spec.md), U256).

## Functional Requirements

- **FR-001**: The loop is multi-round, steerable and stoppable, and its rounds
  are visible in the console while they run (U57, U62).
- **FR-002**: Every tool that touches the outside world passes the approval
  gate. Offline-queued sensitive actions never auto-execute on reconnect
  (constitution IV).
- **FR-003**: `request_capability`, `web_search`, `read_url` and
  `look_up_person` are always available regardless of mode
  (`shared_policies.rules._ALWAYS`) — asking to be unblocked must not itself
  need unblocking.
- **FR-004**: A skill has triggers and a scope, and is stored in `SKILLS_DIR`.
- **FR-005**: The skill ledger records **outcomes**, written after the turn,
  and only for turns a person actually started (`from_user`).
- **FR-006**: A tool schema is built with `_fn()` in `tool_schemas.py`. A
  hand-written dict broke two unrelated tests that walk the schema list (U294).
- **FR-007**: Screen control announces itself and can be aborted.

## Out of scope

- Which connector a tool reaches — see
  [010-connector-skeletons](../010-connector-skeletons/spec.md).
- The presentation runner, which uses the same loop with `announce=False` —
  see [011-presentation-copilot](../011-presentation-copilot/spec.md).

## Traceability

| Units | What they delivered |
|---|---|
| U57, U58, U62 | The agentic loop; the automation ladder; live rounds, steering, stop and teach in the console |
| U59, U60, U64, U65, U66, U71 | Skills with triggers and scope; teach-mode; person-scoped skills; the starter skill |
| U61 | Declarative hooks and scoped subagents |
| U107, U108, U118, U159 | The self-optimising loop; proactive suggestions; polished at creation; the stuck "ready to optimize" |
| U247 | The ledger recorded intentions, never outcomes — and counted the robot's greetings as skill uses |
| U248, U261, U253c | A promise is not an answer; the guard that only knew one language; the invented refusal |
| U249, U250, U251 | Asking to be unblocked; raising and drafting a skill; a proposal that waits for one click |
| U40, U43, U50, U70, U74, U75, U194, U195 | The allow-listed launcher; desktop media control; gated computer use, then computer use that actually works; the overlay and abort; desktop skills |
| U259, U259b | Looking things up, and surviving a search model that disappeared |
| U110 | Voice reminders and the daily briefing |
| U296 | Teach that always leaves a visible trace |
