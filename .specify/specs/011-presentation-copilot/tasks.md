# Tasks: Presentation Copilot (Spec 011)

**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)
**Status**: All tasks completed (retroactively documented 2026-05-01)

---

## Task List

### Phase 1 — Pydantic Models

- [x] **T-001** Define `SlideScript` Pydantic model (`slide_index`, `speech_cue`, `motion_cue?`, `notes?`)
- [x] **T-002** Define `PresentationScript` Pydantic model (`slides: list[SlideScript]`)
- [x] **T-003** Add `PresentationCueReceived` event to `shared-schemas`

### Phase 2 — PresentationManager

- [x] **T-004** Implement `PresentationManager` with `session: PresentationSession | None`
- [x] **T-005** Implement `load_script(yaml_content: str)` — parse YAML, validate with Pydantic, activate `presentation` persona, save current persona
- [x] **T-006** Implement `activate_slide(n: int)` — look up slide (404 if out of range), emit `PresentationCueReceived`, fire speech + motion concurrently
- [x] **T-007** Implement `end_session()` — clear session, restore saved persona
- [x] **T-008** Implement DEGRADED mode guard in `activate_slide` — skip motion cue, log warning; proceed with speech

### Phase 3 — Routes

- [x] **T-009** `POST /presentation/load` — accept YAML body (Content-Type: text/yaml), call `load_script()`, 200 on success / 422 on parse error
- [x] **T-010** `POST /presentation/slide/{n}` — call `activate_slide(n)`, 200 on success / 404 if out of range
- [x] **T-011** `DELETE /presentation/session` — call `end_session()`, 204
- [x] **T-012** `GET /presentation/script` — return current loaded script as JSON, 404 if no session

### Phase 4 — Unit Tests

- [x] **T-013** Script load (valid YAML) — parsed, persona switched, 200 returned
- [x] **T-014** Script load (invalid YAML) — 422 with parse error detail
- [x] **T-015** Slide activation — `PresentationCueReceived` emitted with correct fields
- [x] **T-016** Slide activation — motion cue forwarded to behavior engine (mock assert)
- [x] **T-017** Slide out of range — 404
- [x] **T-018** DEGRADED mode — motion skipped, speech proceeds, warning logged
- [x] **T-019** Session end — persona restored, session cleared (GET /presentation/script returns 404)
- [x] **T-020** 50-slide load performance — assert < 100ms

### Phase 5 — Acceptance Criteria Verification

- [x] **T-021** SC-001: Script loads < 100ms for 50 slides — timing test passes
- [x] **T-022** SC-002: Speech cue fires within 500ms of slide activation — verified in integration test
- [x] **T-023** SC-003: Motion and speech within 100ms of each other — concurrent `asyncio.gather` confirmed
- [x] **T-024** SC-004: `pytest services/orchestrator/tests/test_presentation.py` passes 100%

---

## Notes

- Only one presentation session can be active at a time; loading a new script while a session is active replaces the previous session silently.
- Motion cue names that don't exist in the gesture map are silently skipped (logged at WARNING).
- Speech cues are passed verbatim to TTS — no LLM summarisation or expansion.

---

## Amendment 2026-09-05 — what actually shipped

Retro-specified; all done. See the amendment section in `spec.md`.

- [x] T101 [U27] Synchronised speech and gesture; co-pilot navigation
- [x] T102 [U205] The beat model (trigger + kind), the runner, a test presentation
- [x] T103 [U206] Live wiring and the presenter view
- [x] T104 [U207] Author and save scenarios in the app; YAML stays the storage format
- [x] T105 [U208] `improvise` beats — `orchestrate(announce=False)`, spoken once by the runner
- [x] T106 [U263, U263b] Follow the running slideshow (PowerPoint, Keynote); a field for the deck name
- [x] T107 [U264] Starting a presentation can never destroy the scenario
- [x] T108 [U265] The projector overlay — transparent, click-through, always on top
- [x] T109 [U269] The overlay knows about the show: cues, warnings, subtitles, animation
- [x] T110 [U266] Four causes behind one "nothing happens", including an overlay that would not close
- [x] T111 [U267] The panel says what will actually happen — progress, next cue, advance hint, rehearsal
- [x] T112 [U282] A save error a person can read
- [x] T113 [U246] `uv sync` pruned the presentation extra — pinned, with the other two causes
