---
feature: "011-presentation-copilot"
status: "implemented"
owner: "orchestrator"
priority: P2
risk: Medium
created: "2026-04-25"
amended: "2026-09-13"
units: [U27, U205, U206, U207, U208, U246, U263, U263b, U264, U265, U266, U267, U269, U282, U320, U334, U349, U351, U352, U360, U361, U386, U387, U388, U389, U394]
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
- **FR-007**: On stage he speaks **the scenario and nothing else**. Present mode
  declared this from the start — its behaviour reads *"speaks_first: never —
  cues only"* — and nothing enforced it, so a typed reply, a greeting when the
  camera recognised someone, a proactive line or an open Live session could all
  talk over a talk. The conversational path is closed while the mode is
  `presentation`; the scenario's own voice goes straight to the robot
  (`presentation_api._speak`) and is untouched, which a test pins so the guard
  can never silence the show it protects (U334).
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
- **FR-111**: A scenario decides **when** the overlay is on screen, never
  whether it exists: `overlay: hidden` at scenario level starts the talk clear,
  and `overlay: show` / `overlay: hide` on a beat moves it from that beat
  onwards. A scenario that says nothing leaves it shown for the whole talk —
  the behaviour of every scenario written before this field. The presenter
  still switches the overlay on in the Present panel; a scenario cannot open it
  (U352).
- **FR-112**: Hidden means **rendered clear, not closed**. Electron's overlay
  hide destroys the `BrowserWindow`, and a re-show reloads the page, re-picks
  the display and refetches the scenario — per beat, a flicker the room can
  see. The window stays and fades (350 ms; none under `prefers-reduced-motion`).
  While clear, nothing is drawn, the presenter strip included; the Present
  panel still carries every warning (U352).
- **FR-113**: The state crosses **both** channels FR-106 of
  [spec 008](../008-operator-console/spec.md) allows: `PresentationOverlayChanged`
  on the bus, so a window already open cuts at once rather than up to 1.5 s
  late; and `overlay_visible` in `/presentation/status`, so a window opened
  halfway through a talk can ask — an event only reaches a subscriber that
  existed when it was published. The event is published only on a real change.
  An absent `overlay_visible` reads as **visible**, so a console newer than its
  brain never blanks the projector (U352).
- **FR-106**: Nothing in the Present panel may throw while reading a scenario.
  Losing the presenter's work is the worst outcome available to this feature.
- **FR-107**: A beat may name a **persona** — a brain character id. That
  character's own voice and speed speak the beat, outranking the Present
  panel's Voice, and when the beat improvises its character note is **appended**
  to the system prompt (never substituted — FR-004 of spec 017). A beat with no
  persona keeps the presentation's own voice exactly as before.
- **FR-108**: Within a beat's `text`, `[persona:some_id]` hands the line to
  another character from that point and `[persona]` (or `[/persona]`) hands it
  back. A marker is **never spoken**. A malformed marker is a validation error
  at authoring time, not prose — prose gets read out loud.
- **FR-109**: A line that changes persona halfway reaches the robot as **one
  utterance**, its segments synthesized concurrently and concatenated, because
  loudness is decided per utterance (FR-019 of spec 017) and a change of
  character must not also be a change of volume
  ([ADR-012](../../../docs/adr/ADR-012-a-line-is-one-utterance-however-many-voices-it-has.md)).
  If any one segment cannot be synthesized, the line is not played at all: a
  sentence quietly missing from the middle of a talk is the harder failure to
  notice.
- **FR-110**: A persona id that matches no character still gets spoken, in the
  presentation voice, and the presentation status carries a `voice_note` saying
  which id could not be found. Distinct from `speech_error`, which means the
  room heard nothing at all (constitution XI). It appears on **both** presenter
  surfaces — the Present panel and the overlay's presenter strip — and on
  neither audience layer, stacked beside `speech_error` rather than replacing
  it: a dead speaker does not make a mis-named persona untrue (U351).

- **FR-114**: A beat may name a **`voice`** and a **`speed`** outright, and a
  **`pause`** to wait before speaking. `voice`/`speed` are the narrow form of
  FR-107's `persona` — a line that wants a different sound without a character
  behind it — and they win where both are given, including over inline
  `[persona:x]` segments: a line cannot be both "all in onyx" and "this bit in
  somebody else's voice". `pause` lines a line up with something on **screen**
  (a video, a crawl) rather than with the slide change that fired the beat, and
  a rehearsal does not sit through it. The voice is validated against the
  shipped TTS list and the speed against what the provider accepts, both naming
  the beat (U360).
- **FR-115**: An **unknown field on a beat or scenario is refused**. Pydantic
  ignores extra keys by default, so a generated scenario carried `voice:` and
  `speed:` through an entire rehearsal doing nothing — the two-voice gag they
  were written for came out in one voice, and no screen anywhere said why. A
  misspelt field now stops the load and names itself, which is the only moment
  it is still cheap. The scenario builder also carries these three fields
  through a load-and-save even though it shows no control for them: silently
  undoing a file's whole reason for existing is the same defect wearing a
  different hat (U360).

- **FR-116**: A scenario can be checked **before** the talk, from a desk:
  `python scripts/check_scenario.py <file>` runs the same validation the Present
  panel runs and prints what the talk will actually do — how many times he
  speaks, which presses are yours, which keywords are armed, which slides he
  appears on, and every beat that changes voice or waits. Exit 0 or 1, so it
  fits a pre-flight script or CI. The format itself is documented in
  [`docs/demo/scenario-format.md`](../../../docs/demo/scenario-format.md), which is
  written to be handed to whoever — or whatever — generates a scenario, and says
  plainly that an unknown field is refused rather than ignored (U361).
- **FR-117**: *Take it down* removes the overlay **now**, however many times it
  was shown before. Showing it again — pressing Show twice, or ticking *Show
  what he sees*, which re-shows it so the camera lands at once — used to let
  the old window's late `closed` event clear the reference to the new one,
  which then stayed on the beamer with nothing able to reach it. Only the
  window that is current may clear the reference, and taking it down destroys
  the window rather than asking it to close (U386).
- **FR-118**: A slide's beats run **every time the presenter arrives at it** —
  forwards, backwards or by a jump — unless a beat says `once: true`. They used
  to fire once per show, so stepping back to a slide played nothing. The same
  slide reported twice is a re-read and runs nothing: the slide watcher forgets
  its slide when a read fails, and one flaky read must not repeat a line.
  `once` is unset unless written — a keyword beat then fires once, a slide
  beat replays — because a saved scenario round-trips through `model_dump()`,
  which would otherwise write `once: true` onto every beat (U387).
- **FR-119**: The projector overlay **follows the slide**: on any slide it is
  where the last `overlay:` beat at or before that slide put it, else where the
  scenario starts it. It used to follow the history of what had fired, so a
  step back to a full-frame slide left him on it, and a jump past a hide/show
  pair or into a full-frame run put him in the wrong place (U387).
- **FR-120**: The presenter HUD describes the show that is **running**, however
  it was loaded — from the builder, from the saved list, or into a window
  reloaded mid-talk. Its beat list comes from the brain whenever a show is
  active; *Saying now* is the beat the brain reports as `last_fired`; *Next
  cue* is the first slide beat **ahead of the current slide in slide order**,
  then a hand-advanced beat still waiting, then the end — and it names the
  beat, not only its slide. Keyword beats are armed, not next (U388).
- **FR-121**: **End** stops the show and **keeps** the talk: `POST
  /presentation/end` stops watching and firing, and the brain holds the
  scenario. Status reports it as `kept`, `GET /presentation/scenario` returns it
  with `running: false`, and every window offers **Run again**, **Edit** and
  **Remove** — Run again posting the real scenario, cues and all. **Remove**
  is `DELETE /presentation/scenario`, which is what End used to be. The kept
  talk lives in memory: a restart of AURA forgets it, the saved list does not
  (U389).
- **FR-122**: A scenario can say whether he **wanders** and whether he
  **follows the presenter** — `wander:` / `follow_me:` (`on`/`off`) for the
  whole talk, and on any beat from that beat onwards. They follow the slide the
  way the overlay does (FR-119). During the talk the scenario decides; a
  scenario that says nothing keeps him from wandering and leaves follow-me to
  the owner; *End presentation* gives the owner's own settings back. The robot
  is told independently of the subtitle bus. The builder offers both, for the
  talk and per beat, and carries `once` through a save (U394).

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
| U386 | *Take it down* works after the overlay was shown twice |
| U387 | A slide is a place: its beats replay when you return, and the overlay follows it |
| U388 | The HUD describes the running show, however it was loaded |
| U389 | End keeps the talk: Run again, Edit or Remove |
| U394 | Wander and follow-me in a scenario, with a keynote and a conference talk as worked examples |
| U320 | The panel regrouped: locks as chips, status as status, the projector block given the weight it earns, a run button that names its own action, an empty state with the two doors, and help you can put away |
| U334 | Present mode enforces what it always promised: only the scenario speaks, and no open microphone answers the room |
| U361 | The scenario format written down, and a pre-flight check that says what the talk will do rather than only that the file parses |
| U360 | `voice`, `speed` and `pause` on a beat — and an unknown field refused, after two of them sat in a shipped scenario doing nothing through a rehearsal |
| U349 | A beat can be handed to another character, and one line can change character halfway — per-beat `persona`, inline `[persona:id]` markers, and one utterance however many voices are in it |
| U351 | The wrong-voice note reaches the projector's presenter strip too — the half of U349 that could not be verified while the overlay suite would not mount |
| U352 | The scenario says when the overlay is on the projector — a scenario-level start state and per-beat `show`/`hide`, rendered clear rather than closed, pushed and polled |
