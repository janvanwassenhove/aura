---
feature: "017-voice-and-language"
status: "implemented"
owner: "aura-brain / conversation"
priority: P1
risk: High
created: "2026-09-05"
units: [U22, U36b, U36e, U36h, U45, U46, U47, U49, U54, U67, U73, U80, U81,
        U82, U83, U84, U85, U86, U87, U88, U89, U91, U92, U96, U128, U129,
        U130, U131, U132, U133, U134, U135, U140, U141, U142, U143, U144,
        U145, U146, U148, U149, U150, U153, U154, U155, U156, U163, U203,
        U209, U256, U257, U258, U260, U273, U275, U287, U288, U289, U291,
        U292]
---

# Feature Specification: Voice and Language

**Feature Branch**: `017-voice-and-language`
**Created**: 2026-09-05 (retro-specified — see [015-spec-coverage](../015-spec-coverage/spec.md))
**Status**: Implemented
**Owner**: aura-brain (`voice.py`, `voice_loop.py`, `realtime_session.py`, `realtime_voice.py`, `voice_context.py`, `wakeword.py`)
**Priority**: P1
**Risk**: **High.** This is the most-reworked surface in the product: sixty
units, several of them fixing the previous one's fix. Everything here is
audible in a room full of people the moment it is wrong.

## Background

[ADR-005](../../../docs/adr/ADR-005-voice-pipeline.md) planned one pluggable
pipeline: OpenAI Realtime by default, local Whisper + Kokoro/Piper as the
offline fallback, selected by `STT_PROVIDER` / `TTS_PROVIDER`.

**Reality has three speech paths, not two**, and the ADR does not describe them:

| Path | Module | What it is |
|---|---|---|
| Pipeline | `voice.py` → `voice_loop.py` | Wake word → STT → orchestrator (tools) → TTS. Cheaper, and the only path that can call tools. |
| Per-turn realtime | `realtime_voice.py` | One Realtime request per turn, opened after the wake word (U129). |
| Realtime session | `realtime_session.py` | A continuous session with server-side VAD — the "ChatGPT voice" architecture (U154). Fluid, no tools. |

The owner chooses in Settings (U132, U203): *pipeline runs tools and is
cheaper; realtime is fluid speech-to-speech.* That choice, and the fact that
there **are** three paths, is the single most important thing this spec records
— because four separate language bugs (U287, U289, U291, U292) were each fixed
in one path while the others kept the old behaviour, and each fix looked
complete until the next conversation.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — He answers in the language he was spoken to, and stays there (Priority: P1)

Reported as *"ik merk dat robot soms maar half opvangt van wat in nederlands
gezegd wordt, en dan naar andere taal springt zoals duits of zelfs aziatische
talen"*, and after two more attempts: *"is weer in andere talen aan het
spinnen, hoe komt dit en kunnen we dit nu voor eens en altijd juist zetten"*.

**Independent Test**: with `ASSISTANT_LANGUAGE=nl`, feed a Dutch utterance to
each of the three paths; each transcribes as Dutch, and a returned transcript
in a non-Latin script is dropped rather than answered.

**Acceptance Scenarios**:

1. **Given** a household language is known, **When** audio is transcribed,
   **Then** the language is **pinned**, not auto-detected. Resolution order
   (`voice._stt_language`): `STT_LANGUAGE` → `ASSISTANT_LANGUAGE` → the
   language of the person he can currently see (U288) → the machine locale →
   `LANGUAGE_FALLBACK`. `multi` is the explicit opt-out for households that mix
   languages inside one sentence.
2. **Given** a transcript comes back in a script the household does not use,
   **When** it is received, **Then** it is dropped rather than answered
   (`voice._wrong_script`) — half-heard Dutch became German and then Asian
   scripts, and answering that is worse than saying nothing.
3. **Given** the realtime **session** path is active, **When** it opens,
   **Then** it pins the language too, in the GA session shape
   `audio.input.transcription: {model, language}` (U144, U289). *U287 fixed the
   pipeline; the session kept guessing for two more days.*
4. **Given** a persona or character prompt is applied, **When** instructions are
   built, **Then** the language rule is **still there**. U291: a persona
   replaced the whole instruction string and deleted the only rule that kept
   him in one language. `voice_context.build_instructions()` now always appends
   it, and a test pins that.
5. **Given** two people are recognised at once, **When** they speak, **Then**
   the listening language is only narrowed to a person's language if the room
   agrees on one; otherwise the household default stands (U288).

### User Story 2 — He does not fill silence with sentences (Priority: P1)

Reported as *"hij blijft continue praten, zonder duidelijke reden... in nl zegt
hij en herhaalt hij: één momentje ik haal transcriptie op"* — about twenty
times in a row.

**Why this is its own story**: I caused it. U291's instruction described
transcript machinery to a model that *hears*, and handed it a ready-made
apology to fall back on. Two rules now live in code and in tests:

**Acceptance Scenarios**:

1. **Given** instructions are built for any speech path, **When** they are
   built, **Then** they never describe machinery the model cannot reach
   (transcripts, tools it does not have, retrieval it does not perform).
2. **Given** instructions are built, **When** they are built, **Then** they
   never contain a sentence he can say verbatim as a stall. The rule is the
   opposite: *never announce, narrate or promise what you are about to do, and
   never apologise for taking time — say the answer instead.*
3. **Given** he did not catch something, **When** that happens, **Then** he
   asks once, briefly, rather than looping.

### User Story 3 — He wakes on his name and not on the television (Priority: P1)

**Acceptance Scenarios**:

1. **Given** the wake word, **When** it is spoken, **Then** detection runs
   **locally** (openWakeWord, ONNX on the CPU) so waking costs no network hop
   and no transcription (U128). If the model is unavailable, the loop silently
   falls back to transcribe-then-fuzzy-match — `build_detector` returns `None`
   and never raises into the loop.
2. **Given** background speech, television or music, **When** it is heard,
   **Then** he does not answer it (U49, U69, U135, U256).
3. **Given** he is speaking, **When** his own voice reaches the microphone,
   **Then** he does not treat it as input (U67, U92, U148 self-hearing guard,
   U258 — *he woke himself up by saying his own name*).
4. **Given** Quiet mode, **When** somebody arrives, **Then** he does not greet
   (U256).
5. **Given** the microphone's automatic gain, **When** the room is silent,
   **Then** room tone is not amplified into speech (U163) and the VAD gate is
   set for a quiet microphone rather than a studio (U86).

### User Story 4 — The reply is heard, complete and at a usable volume (Priority: P1)

**Acceptance Scenarios**:

1. **Given** a spoken reply, **When** it plays, **Then** it is not cut off after
   the first word (U80, U81 buffer underrun), not chopped (U83, via GStreamer
   `playbin`), and does not hang mid-speech (U155, U156 gapless `appsrc`).
2. **Given** the robot's speaker, **When** it connects, **Then** ALSA volume is
   forced to maximum, because the default was inaudible across a room (U82).
3. **Given** realtime audio, **When** it arrives, **Then** playback starts on
   the first segment rather than after the whole buffer (U153).
4. **Given** the owner interrupts, **When** they speak the wake word, **Then**
   he stops (barge-in, U54, U73 — barge-in requires the wake word so a cough
   does not cut him off).
5. **Given** the laptop rather than the robot should speak, **When** configured,
   **Then** audio comes out of the laptop speakers (U209).

### User Story 5 — When the expensive path is unavailable, it says so (Priority: P1)

**Acceptance Scenarios**:

1. **Given** Realtime hangs, **When** it does, **Then** a timeout and a circuit
   breaker fall back to the pipeline rather than leaving a silent robot (U133).
2. **Given** the account has no Realtime access, **When** the owner asks *"do I
   need to do something for Realtime?"*, **Then** a self-check answers it
   (U142), and the breaker trips with the real reason rather than silence
   (U141).
3. **Given** the Realtime model name has gone stale, **When** a session opens,
   **Then** candidate models are tried and the working one is detected (U143).
4. **Given** realtime is in use, **When** it is, **Then** a cost meter is
   visible (U129, U132).

### User Story 6 — One "Voice" setting, and it is clear which one wins (Priority: P2)

Reported as *"the default voice in settings, whats difference between the one
selected in robot? how are they used?"* — three screens offered a "Voice" and
none said which one applied (U273). Settings holds the default; the character
carries its own; a person may be met in a specific one (U274). The order is
stated on screen.

## Functional Requirements

- **FR-001**: Three speech paths exist and are selectable. Any change to
  language, wake behaviour or instruction text must be applied to **all three**
  or explicitly scoped to one, in the same unit.
- **FR-002**: The transcription language is resolved by
  `voice._stt_language()` in the documented order and pinned; `multi` opts out.
- **FR-003**: A transcript whose script does not match the household's
  languages is discarded, not answered.
- **FR-004**: `voice_context.build_instructions()` always appends the language
  and delivery rule, regardless of persona or character prompt.
- **FR-005**: Instructions never describe machinery the model cannot reach, and
  never supply a sentence usable as a stall.
- **FR-006**: Wake-word detection is local, with a network fallback that cannot
  raise into the loop.
- **FR-007**: Self-hearing, background media and unaddressed speech do not
  produce turns.
- **FR-008**: A failing Realtime path degrades to the pipeline and reports why.
- **FR-009**: Verification runs with the API keys **unset** — three tests
  silently depended on a key present in a developer shell and hid a red build
  for six hours (U283).

## Out of scope

- Which language a *person* is met in — that is stored per person in
  [018-knowledge-people-and-judgment](../018-knowledge-people-and-judgment/spec.md);
  this spec only consumes it.
- Tool calling and the agentic loop — see
  [019-skills-and-automation](../019-skills-and-automation/spec.md). Note that
  the realtime session path cannot call tools; that is why the pipeline exists.

## Known divergence from ADR-005

ADR-005 describes a two-provider pluggable pipeline selected by
`STT_PROVIDER` / `TTS_PROVIDER`. It does not describe the three paths, the
local wake word, the circuit breaker, or the language pinning. **This spec is
the current truth**; the ADR is superseded in those respects and is amended in
the same series as this backfill.

## Traceability

| Units | What they delivered |
|---|---|
| U22, U36b, U36e, U45, U46 | The first voice transport; the robot speaks; volume; talking through the robot's own microphone |
| U47, U85, U87, U96, U128 | Hands-free wake word, fuzzy matching, bare wake as a command, then local on-device detection |
| U36h, U130, U131 | Switchable language (EN/NL/FR/DE) and a configurable call name |
| U54, U73, U153 | Streamed TTS, barge-in gated on the wake word, playback on the first segment |
| U80, U81, U82, U83, U155, U156 | Speech that was cut off, chopped, inaudible, or hung mid-sentence |
| U84, U148, U149, U150, U154 | The conversation state machine; VAD endpointing on, then conservative, then off by default; the continuous-session architecture |
| U86, U163 | A VAD gate set for a quiet microphone; AGC no longer amplifying room tone into speech |
| U67, U88, U91, U92, U145, U258 | Self-conversation, the spoken "Richie:" label, STT prompt echo, phantom transcripts, and waking himself with his own name |
| U129, U132, U133, U134, U140, U141, U142, U143, U144, U146 | Realtime: wake-gated turns, cost meter, timeout and breaker, the gating bug, instrumentation, the access self-check, model detection, the GA migration, correct labels |
| U135, U145 | The foreign-language allowlist — and the fix that broke STT entirely |
| U49, U69, U256, U257, U275 | Wake-word hallucinations, lyrics becoming conversation, greeting in Quiet mode, "hallo" is not a language, and "hey Richie" heard perfectly but ignored |
| U203, U209, U273 | Voice with tools by default; laptop speakers; naming which "Voice" setting wins |
| U260, U287, U288, U289, U291, U292 | Greeted and then deaf; language pinned in the pipeline, then per room, then in the session; the persona that deleted the rule; the stall sentence I handed him |
