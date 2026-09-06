---
feature: "011-presentation-copilot"
status: "implemented"
owner: "orchestrator"
priority: P2
risk: Medium
created: "2026-04-25"
amended: "2026-09-05"
units: [U27, U205, U206, U207, U208, U246, U263, U263b, U264, U265, U266, U267, U269, U282, U320]
---

# Feature Specification: Presentation Copilot

**Feature Branch**: `011-presentation-copilot`
**Created**: 2026-04-25
**Status**: Implemented — **see the 2026-09 amendment at the end of this
document**, which supersedes the slide-index model described below.
**Owner**: orchestrator
**Priority**: P2 (raised from P3: it is a demonstrated, used feature)
**Risk**: Medium

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

- [Constitution](../../memory/constitution.md) — Principle III (Events Drive State)
- [Spec 004 — Behavior Engine](../004-behavior-engine/spec.md)
- [Spec 006 — Orchestrator Foundation](../006-orchestrator-foundation/spec.md)

---

# Amendment — 2026-09-05: what it actually became

*Retro-specified; see [015-spec-coverage](../015-spec-coverage/spec.md) for why
this arrives late. The April text above is left intact as the record of the
original plan. Where the two disagree, this section is the truth.*

## What changed in shape

The plan assumed **the deck drives the robot**: a slide activates, a cue for
that index is spoken. Used in a real room, three of those assumptions failed.

| April plan | What it is now | Why |
|---|---|---|
| One cue per slide index | **Beats** with a trigger: `manual`, `slide:4`, or `keyword:Java` | A presenter does not talk in slide units. Half the beats fire on something said, not on a transition (U205). |
| Cues read verbatim, no LLM | Verbatim **plus** `improvise` beats that run the full agentic loop | A demo needs today's calendar, not April's. `improvise` calls `orchestrate(announce=False)`: tools run, and the presenter's robot speaks the result once itself (U208). |
| Script written as a YAML file | Built and saved **in the app** | Nobody hand-writes YAML on stage. The scenario builder is the authoring surface; YAML is still the storage format (U207). |
| Driven by console or remote | Driven by **the slideshow itself**, PowerPoint and Keynote | The presenter clicks Next in Keynote like they always do; AURA watches the deck (U263, U263b). |
| Robot speaks | Robot speaks **and appears** — a transparent, click-through overlay window on the projector | Not every room has the robot at the front, and a face on the slide is worth as much as a voice (U265, U269). |

## Additional user stories

### User Story 4 — He appears on the projector (Priority: P2)

1. **Given** the overlay is switched on, **When** it opens, **Then** it is a
   frameless, transparent, click-through window (`alwaysOnTop`,
   `'screen-saver'`) that does not steal a click from the deck (U265).
2. **Given** the overlay is open, **When** the presentation runs, **Then** it
   shows cues, warnings and subtitles, and the character animates while
   speaking (U269).
3. **Given** the overlay is on, **When** the owner switches it off, **Then** it
   closes — U266: it could be opened and not closed.
4. **Given** the camera is wanted on the projector, **When** it is enabled,
   **Then** the overlay can show what the robot actually sees.
5. **Given** a character is chosen, **When** it changes, **Then** the overlay
   follows. It is a **separate BrowserWindow with its own Pinia store**, which
   is the recurring root cause of state not crossing (U269, U276, U286, U290);
   it follows through a `storage` event (U286).

### User Story 5 — "Start presentation" starts something (Priority: P1)

Reported four times in a row — *"start presentation is not doing anything"*,
*"start presentation doet nog steeds niks"*, *"he never said anything"*.

1. **Given** a scenario, **When** Start is pressed, **Then** the run begins, or
   the panel says why it cannot. U266 found **four different causes behind one
   symptom**, which is why this is a P1 story rather than a bug note.
2. **Given** the scenario is being started, **When** the beats are read,
   **Then** the console's beat parsing cannot throw — `lib/beats.ts`
   (`toRows`, `triggerOf`, `kindOf`, `cueOf`) is used inside a `try`, and a cue
   is a **string** (`"manual"`, `"slide:4"`, `"keyword:Java"`), not an object.
   U264: an exception here wiped the scenario the presenter had just written.
3. **Given** the panel, **When** it is read before starting, **Then** it says
   what will actually happen: progress, the next cue, whether beats are manual,
   how to advance, and a banner when speech has failed (U267, U269).
4. **Given** rehearsal mode, **When** it is on, **Then** the panel says what
   that changes.
5. **Given** a scenario fails to save, **When** it does, **Then** the error is a
   sentence, not a raw Pydantic dump (U282).

### User Story 6 — The panel reads like one thing (Priority: P2)

Reported as *"improve ui/ux in present mode → presentations"*, with the
settings aside as the example.

1. **Given** the aside, **When** it is read, **Then** it is grouped — *how he
   sounds*, *what he is following*, *on the projector* — rather than one flat
   list in which a setting, a read-only status and a six-control overlay block
   all carry the same weight (U320).
2. **Given** what Present mode locks, **When** it is shown, **Then** it is a
   row of chips (mail · dev tools · screen control), not a sentence to parse.
3. **Given** the audience/presenter choice, **When** it is offered, **Then**
   both options are visible as a segmented control. A `<select>` hides one
   behind a click, and the wrong one on a beamer projects the presenter's
   private cue notes at the audience.
4. **Given** the run button, **When** nothing is loaded, **Then** it says
   *Write a scenario*, because that is what pressing it does. It said "Run
   presentation" and opened the builder — a label naming a different action
   than the one it performs, which is constitution XI applied to a button.
5. **Given** an empty Present view, **When** it is opened, **Then** the two
   ways in are offered in the body where the eye is, not only in the top-right
   corner — and the state is said **once**: the run bar is hidden rather than
   reading "No scenario loaded" directly above "No scenario yet".
6. **Given** the four-step explanation, **When** a presenter already knows it,
   **Then** it collapses to one line and stays collapsed. It had no heading, so
   it read as the page's content rather than as help, and taught the same
   presenter before every talk.
7. **Given** the overlay controls, **When** they are shown, **Then** the panel
   does **not** claim whether the overlay is up — this window cannot see the
   other one — and *Take it down* is always present regardless (U266, U320).

## Amended functional requirements

- **FR-101**: A beat has a trigger (`manual` | `slide:N` | `keyword:TEXT`) and a
  kind (verbatim speech, motion, or `improvise`). The cue is a string.
- **FR-102**: `improvise` runs the full loop with `announce=False`, so tools
  execute and nothing auto-speaks; the presentation runner speaks the result
  once.
- **FR-103**: Scenarios are authored in the app and stored as YAML.
- **FR-104**: The deck is followed by watching the running slideshow
  (PowerPoint and Keynote), not by the console pushing indexes.
- **FR-105**: The projector overlay is a separate, transparent, click-through
  window; it can be closed; and it reflects character, cues, subtitles and
  optionally the camera.
- **FR-106**: Nothing in the Present panel may throw while reading a scenario.
  Losing the presenter's work is the worst outcome available to this feature.

## Superseded

FR-002's `slide_index`/`speech_cue` script format is retained as the storage
shape for slide-triggered beats only. SC-002 (500 ms from slide activation) now
applies to `slide:N` beats; `manual` and `keyword:` beats have no such deadline.

## Traceability

| Units | What they delivered |
|---|---|
| U27 | The first version: synchronised speech and gesture, co-pilot navigation |
| U205, U206 | The beat model, the runner, the test presentation; live wiring and presenter view |
| U207, U282 | Building and saving scenarios in the app; and an error a person can read |
| U208 | `improvise` beats — live data through the pipeline, spoken once |
| U263, U263b | Following the real slideshow, Keynote included; somewhere to type the deck name |
| U264 | "Start presentation" no longer destroys the scenario |
| U265, U269 | The projector overlay: transparent, click-through, animated, with cues and subtitles |
| U266, U267 | Four "nothing happens" with four causes; a panel that says what will happen |
| U246 | Three broken things behind one missing word — including `uv sync` pruning the presentation extra |
| U320 | The panel regrouped: locks as chips, status as status, the projector block given the weight it earns, a run button that names its own action, an empty state with the two doors, and help you can put away |
