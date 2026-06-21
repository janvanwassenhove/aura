---
feature: "011-presentation-copilot"
status: "in-progress"
owner: "orchestrator"
priority: P3
risk: Low
created: "2026-04-25"
---

# Feature Specification: Presentation Copilot

**Feature Branch**: `011-presentation-copilot`
**Created**: 2026-04-25
**Status**: In Progress
**Owner**: orchestrator
**Priority**: P3
**Risk**: Low

## User Scenarios & Testing

### User Story 1 — AURA Follows a Presentation Script (Priority: P3)

A presenter loads a slide script and AURA speaks the cues at the right time, synchronized with slide transitions.

**Why this priority**: Differentiating use case for sales demos and conference talks. P3 because it depends on a fully functional conversation and behavior stack.

**Independent Test**: Load a 3-slide script; advance to slide 2; assert AURA speaks the slide 2 cue within 500ms.

**Acceptance Scenarios**:

1. **Given** a presentation script is loaded via `POST /presentation/load`, **When** slide 2 is activated, **Then** AURA speaks the configured cue for slide 2.
2. **Given** a cue is playing, **When** a `next_slide` event is received before the cue ends, **Then** the current cue is cut off and the next cue begins.
3. **Given** a slide with no script, **When** it is activated, **Then** AURA stays silent (no error).
4. **Given** AURA is in presentation persona, **When** a question is asked between slides, **Then** AURA answers and returns to ready state for the next slide.

---

### User Story 2 — Slide Transitions Trigger Behavior Engine (Priority: P3)

Each slide transition can trigger a motion cue (e.g., nod, gesture forward) synchronized with speech.

**Independent Test**: Load script with motion cues; advance to slide 3 with a `gesture_forward` cue; assert `MotionStarted(name="gesture_forward")` is emitted.

**Acceptance Scenarios**:

1. **Given** a slide script with a `motion_cue` field, **When** the slide is activated, **Then** the motion cue is passed to the behavior engine.
2. **Given** a motion cue and speech cue on the same slide, **When** the slide activates, **Then** both start within 100ms of each other.
3. **Given** presentation mode ends (`DELETE /presentation/session`), **When** called, **Then** AURA returns to work or home persona.

---

### User Story 3 — Presentation Script Format is Human-Readable YAML (Priority: P3)

A presenter can write a YAML script file with slide numbers, speech text, and optional motion cues. AURA loads it without code changes.

**Independent Test**: Load a YAML script; call `GET /presentation/script`; assert the returned script matches the loaded file.

**Acceptance Scenarios**:

1. **Given** a valid YAML script file, **When** loaded via `POST /presentation/load`, **Then** the script is parsed without error.
2. **Given** an invalid YAML file, **When** loaded, **Then** a validation error with line-level detail is returned.
3. **Given** a script with 20 slides, **When** loaded, **Then** all 20 slides are accessible by index.

---

### Edge Cases

- What happens if the slide number is out of range? → Returns 404 with a clear message.
- What happens if AURA is in OFFLINE/DEGRADED mode during a presentation? → Presentation continues with text-only cues; motion cues are skipped.
- What happens if two `next_slide` events arrive within 200ms? → Only the second is processed; first is dropped if not yet started.

---

## Requirements

### Functional Requirements

- **FR-001**: Presentation service MUST expose: `POST /presentation/load`, `POST /presentation/slide/{n}`, `DELETE /presentation/session`, `GET /presentation/script`.
- **FR-002**: Script format MUST be YAML with fields: `slide_index`, `speech_cue`, `motion_cue?`, `notes?`.
- **FR-003**: `PresentationCueReceived` event MUST be emitted when a slide cue fires.
- **FR-004**: Slide transitions MUST trigger the behavior engine with motion cues if defined.
- **FR-005**: Presentation persona MUST be activated when a session is loaded.
- **FR-006**: Presentation session MUST be cleared when `DELETE /presentation/session` is called.

### Key Entities

- **PresentationScript**: YAML document with list of `SlideScript` items.
- **SlideScript**: `slide_index`, `speech_cue`, `motion_cue?`, `notes?`.
- **PresentationSession**: Active session with loaded script, current slide, persona=presentation.

---

## Success Criteria

### Measurable Outcomes

- **SC-001**: Script loads within 100ms for a 50-slide presentation.
- **SC-002**: Speech cue fires within 500ms of slide activation event.
- **SC-003**: Motion and speech cues start within 100ms of each other.
- **SC-004**: `pytest services/orchestrator/tests/test_presentation.py` passes 100%.

---

## Assumptions

- Presentation mode is triggered by the operator console or an external remote (not voice command).
- Speech cues are read verbatim (no LLM generation) for reliability.
- Motion cue names must exist in the gesture map; unknown names are silently skipped.
- Only one presentation session can be active at a time.

---

## References

- [Constitution](.specify/memory/constitution.md) — Principle III (Events Drive State)
- [Spec 004 — Behavior Engine](../004-behavior-engine/spec.md)
- [Spec 006 — Orchestrator Foundation](../006-orchestrator-foundation/spec.md)
