# Implementation Plan: Presentation Copilot (Spec 011)

**Spec**: [spec.md](spec.md)
**Status**: Implemented (plan retroactively documented 2026-05-01)
**Risk**: Low (no external dependencies; pure orchestrator extension)

---

## Technical Decisions

### TD-001 — Presentation Module in Orchestrator

The presentation feature lives in `services/orchestrator/src/orchestrator/presentation.py`. It is not a separate service — the orchestrator already owns persona management and the behavior engine integration, making it the natural home for presentation session state.

### TD-002 — YAML Script Format

Script files are parsed with `PyYAML`. The schema is validated via Pydantic:

```python
class SlideScript(BaseModel):
    slide_index: int        # 1-based
    speech_cue: str
    motion_cue: str | None = None
    notes: str | None = None

class PresentationScript(BaseModel):
    slides: list[SlideScript]
```

Parsing errors surface as `422 Unprocessable Entity` with PyYAML line-level details in the response body.

### TD-003 — Session State

`PresentationSession` is an in-memory dataclass on the `PresentationManager` singleton (one active session at a time):

```python
@dataclass
class PresentationSession:
    script: PresentationScript
    current_slide: int = 0   # 0 = not started
    persona_saved: str = ""  # persona to restore on session end
```

### TD-004 — Slide Activation Flow

`POST /presentation/slide/{n}`:
1. Look up `script.slides[n-1]` (404 if out of range)
2. Emit `PresentationCueReceived(slide_index=n, speech_cue=..., motion_cue=...)` event
3. If `motion_cue` is set → forward to behavior engine via `POST /robot/behavior/motion` (best-effort; failures logged, not raised)
4. Speech cue is read verbatim — no LLM generation; text is passed directly to TTS via the conversation-runtime

### TD-005 — Persona Switching

`POST /presentation/load` activates the `presentation` persona (stored in `shared-personas`). The previously active persona is saved and restored when `DELETE /presentation/session` is called.

### TD-006 — Degraded Mode Handling

If AURA is in DEGRADED/OFFLINE mode when a slide is activated:
- Speech cue fires (TTS is local — available offline)
- Motion cue is skipped (emits a `MotionSkipped` log warning)

---

## File Structure

```
services/orchestrator/src/orchestrator/
  presentation.py     ← PresentationManager, SlideScript, PresentationScript, PresentationSession

services/orchestrator/tests/
  test_presentation.py
```

---

## Test Strategy

### Unit Tests (`test_presentation.py`)
- Script loads within 100ms for 50-slide YAML
- Slide activation emits `PresentationCueReceived` with correct fields
- Out-of-range slide returns 404
- Motion cue forwarded to behavior engine
- Motion cue skipped in DEGRADED mode (logged, not raised)
- Session cleared on `DELETE /presentation/session`
- Persona restored after session end

---

## Complexity Tracking

No significant complexity. The trickiest part is the concurrent speech + motion cue timing requirement (both within 100ms of slide activation). This is achieved by firing both as concurrent asyncio tasks (`asyncio.gather`) rather than sequentially.

---

## Files Touched

| File | Action |
|------|--------|
| `services/orchestrator/src/orchestrator/presentation.py` | Created |
| `services/orchestrator/src/orchestrator/routes.py` | Modified — added `/presentation/*` routes |
| `services/orchestrator/tests/test_presentation.py` | Created |
