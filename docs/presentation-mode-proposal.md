# Presentation mode — proposal

Give a presentation **together with** the robot: it has cues where it must
speak, and topics where it *may* chime in. Show its speech as live subtitles,
show its camera, and route its voice through the laptop's speakers.

This is a proposal to react to — nothing here is built yet except the pieces
noted as "exists today". Phase 0 is a decision only you can make.

---

## What already exists (we build on this, we don't start over)

| Piece | State | Where |
|---|---|---|
| **PresentationManager** — loads a YAML script, tracks the current slide, `activate_slide(i)` speaks a cue + gesture, emits `PresentationCueReceived` | works, but **linear + verbatim only** | `orchestrator/presentation.py` |
| Script model — per slide: `speech_cue` (spoken verbatim), `motion_cue` (gesture), `notes` | works | `shared_schemas/presentation/models.py` |
| **Realtime voice** — fluid speech-to-speech, per-persona, `workshop_coach` ships on it | works (U203) | `realtime_session.py` |
| **Live transcript** — the realtime session already emits transcript deltas (`TranscriptUpdated`); the console shows the current line | works | `RobotPanel` |
| **Camera feed** in the console | works (U195/U196) | `VideoPanel` |
| Robot **audio bytes** exist in the brain *before* they're pushed to the robot | so they can be teed elsewhere | `realtime_session.py` |
| Persona **modes** (presentation/demo) govern toolsets + gesture energy | works | `characters.py` |

So the honest starting point: **AURA can already read a scripted deck aloud with
gestures.** What's missing is everything that makes it feel like a *co-presenter*
rather than a talking script.

---

## The gap — what you asked for

1. **Flexible cues**, not just "say this on slide N": per beat, one of
   - `speak` — say this line verbatim (today's behaviour)
   - `improvise` — say something fresh on a topic, within guardrails
   - `chime_in` — armed: if it hears the topic while *you* talk, it may add one remark
   - `silent` — stay quiet unless directly addressed
2. **Triggers** for each beat: manual "next", a slide change, or a keyword you say.
3. **Subtitles** of what the robot says.
4. **Camera** on screen.
5. **Audio** out of the laptop's speakers, not (only) the robot's.

---

## Slides — start from your existing PPT, or something else?

Three routes. This is **Phase 0, your call**, because it shapes everything after.

### A. Keep PowerPoint, advance beats by hand *(least effort, keep your tool)*
You run your `.pptx` exactly as today. AURA does **not** render slides; it just
advances through the beat script when you press a "next" control (a key, or a
button in the console). Beats are decoupled from the slides — you glance, you
tap, the robot does its beat.
- **Pro:** zero conversion, keep PowerPoint with all its animations, works now.
- **Con:** the robot doesn't *know* which slide you're on; you drive the sync.

*(Optional upgrade later: read the real slide number from PowerPoint via COM
automation on Windows — `SlideShowWindow.View.Slide.SlideIndex`. Fiddly and
Windows-only, so not phase 1.)*

### B. Console-owned HTML deck (reveal.js) *(full integration, leave PowerPoint)*
AURA renders the slides, so a slide change is a first-class event and subtitles
+ camera overlay live on the same screen. You'd rebuild the deck as HTML (or
convert).
- **Pro:** tightest integration; deterministic `slide:N` triggers; one screen.
- **Con:** you leave PowerPoint; conversion/rebuild effort.

### C. Export PPT → images, show in a console viewer *(reuse content + integration)*
Convert your existing `.pptx` to one image per slide (LibreOffice headless, one
command). The console shows them and owns the "next slide" event, so beats can
fire on `slide:N`.
- **Pro:** keep your PPT *content*; get integration; no live PowerPoint to babysit.
- **Con:** static slides (animations flattened); one export step per edit.

> **Recommendation:** if you want it working soon with your current deck, **A**
> (keep PPT, manual beats). If you want the robot genuinely synced to slides
> and don't mind an export step, **C**. Choose **B** only if you're happy to
> author decks in HTML from now on.

---

## The flexible-scenario model (the real new thing)

Extend the script from "slide → verbatim" to a list of **beats**:

```yaml
title: "AURA at the demo"
beats:
  - id: intro
    trigger: manual                 # manual | slide:3 | keyword:"vertel eens"
    mode: speak
    text: "Hallo allemaal, ik ben AURA."
    gesture: wave

  - id: why-different
    trigger: slide:4
    mode: improvise                 # realtime, fresh line on a topic
    topic: "waarom een robot-assistent anders is dan een chatbot"
    guardrails: "Max 3 zinnen. Geen prijzen noemen."

  - id: jan-talks-privacy
    trigger: keyword:"privacy"
    mode: chime_in                  # armed while YOU talk; may add one remark
    topic: "dat alle data lokaal en versleuteld blijft"
    once: true

  - id: qa
    trigger: manual
    mode: silent                    # only speaks when addressed by wake word
```

- `speak` and `improvise` run when their trigger fires.
- `chime_in` *arms* a topic; while you present, if the keyword is heard, the
  robot may interject once.
- `silent` hands the floor back to you.

`improvise`/`chime_in` use the **realtime** engine (fluid) — but remember
(U203) realtime has **no tool access**. A beat that needs a lookup (calendar,
Spotify, live data) must be a `pipeline` beat instead. The model can carry an
`engine:` override per beat for exactly that.

---

## Integration surfaces

| Want | How | Size |
|---|---|---|
| **Subtitles** | The realtime transcript deltas already flow as `TranscriptUpdated`. Add a full-screen **presenter view** in the console with the live line, large. | small |
| **Camera** | Reuse `VideoPanel` as a thumbnail in presenter view. | small |
| **Audio → laptop speakers** | The realtime audio bytes are already in the brain before they reach the robot. Tee them to the console over the existing socket; the console plays them with WebAudio. Robot can stay muted or play too. | medium |
| **Presenter control** | A console **presenter mode**: big subtitle, current beat, a "next beat" button, camera thumbnail, and skip/panic. | medium |

---

## Phased plan

- **Phase 0 — decide the slide strategy** (A / B / C above). *Your call; blocks the rest.*
- **Phase 1 — beats + manual cues.** Extend the script model to beats
  (`speak`/`improvise`/`silent`, `trigger: manual`); presenter view with big
  subtitles + a "next beat" button; robot runs each beat through the
  presentation persona (realtime). **No slide integration yet — you advance by
  hand.** This is the smallest thing that already *feels* like co-presenting.
- **Phase 2 — subtitles + camera + audio routing.** Live subtitle overlay,
  camera thumbnail, robot voice out of the laptop speakers.
- **Phase 3 — slide sync.** Whichever route you picked: `slide:N` triggers from
  a console-owned deck (B/C) or PowerPoint COM events (A-upgrade).
- **Phase 4 — `chime_in` / keyword triggers.** Armed topics where the robot may
  interject when it hears a keyword. **Riskiest** — depends on reliable STT
  while *you* are talking, and the same echo-cancellation limits that keep
  barge-in off apply here.

---

## Preparing a presentation

1. **Slides:** keep your `.pptx` (route A) or export it to images (route C).
2. **Beat script:** write a small YAML next to it — for each moment decide
   speak / improvise / chime_in / silent, the text or topic, a gesture, and the
   trigger.
3. **Dry-run** in presenter view; tune timing, cut beats that drag, mark which
   topics the robot may interrupt on.

---

## Honest constraints

- **`chime_in` is the hard part.** It needs the robot to hear you clearly while
  you speak; AEC is not yet stable enough for reliable full-duplex, so treat
  phase 4 as experimental.
- **Realtime can't use tools** (U203). Great for talking, useless for a beat
  that needs live data — use a `pipeline` beat there and accept it's a touch
  slower.
- **Audio routing adds latency** versus the robot's own speaker. Measure it
  before relying on laptop playback for anything time-critical.
- **Cost:** realtime bills per turn (the `~$` meter in Robot State). A long
  presentation on realtime is not free — budget for it.

---

## What I need from you to start Phase 1

1. Slide strategy: **A (keep PPT, manual beats)**, **B (HTML deck)**, or **C
   (export PPT to images)**?
2. Is a "next beat" button in the console enough to drive it at first, or do you
   want spoken keyword triggers from day one?
3. Do you have an existing `.pptx` you want to reuse as the first test?
