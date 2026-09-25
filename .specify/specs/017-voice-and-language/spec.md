---
feature: "017-voice-and-language"
status: "implemented"
owner: "aura-brain / conversation"
priority: P1
risk: High
created: "2026-09-05"
units: [U22, U36b, U36e, U36h, U45, U46, U47, U49, U54, U67, U73, U80, U81, U82, U83, U84, U85, U86, U87, U88, U89, U91, U92, U96, U128, U129, U130, U131, U132, U133, U134, U135, U140, U141, U142, U143, U144, U145, U146, U148, U149, U150, U153, U154, U155, U156, U163, U203, U209, U256, U257, U258, U260, U273, U275, U287, U288, U289, U291, U292, U321, U322, U324, U329, U331, U333, U349, U366]
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

**Reality has four speech paths, not two**, and the ADR does not describe them:

| Path | Module | What it is |
|---|---|---|
| Pipeline | `voice.py` → `voice_loop.py` | Wake word → STT → orchestrator (tools) → TTS. Cheaper, and the only path that can call tools. |
| Per-turn realtime | `realtime_voice.py` | One Realtime request per turn, opened after the wake word (U129). |
| Realtime session | `realtime_session.py` | A continuous session with server-side VAD — the "ChatGPT voice" architecture (U154). Fluid, no tools. |
| GPT-Live session | `live_session.py` | A full-duplex Live API session (U324, [ADR-011](../../../docs/adr/ADR-011-gpt-live-is-a-fourth-path.md)). Natural speech **and** tools, through client delegation: the work comes back to AURA's own orchestrator and approval gate. Opt-in; billed per open minute. |

The owner chooses in Settings, and per character (U132, U203, U324): *the
pipeline runs tools and is the cheapest; realtime is fluid speech-to-speech but
cannot use tools; live is natural speech that hands tool work back to AURA.*
That choice, and the fact that there **are** several paths, is the single most
important thing this spec records
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

U349 adds one step above all of them, scoped to a talk: a presentation beat
may name a **persona**, and that character's voice and speed speak the beat.
It outranks the Present panel's Voice — which is the same rule as everywhere
else (a character's own voice wins over a mode's), applied at the grain of a
single beat rather than a session. A beat that names no persona is unchanged:
the Present panel's Voice still decides.

### User Story 7 — A natural voice that can still do things (Priority: P2)

**Acceptance Scenarios**:

1. **Given** the Live engine, **When** the person asks about their agenda,
   **Then** the session delegates, the orchestrator runs the tool behind the
   approval gate, and he says the result in the conversation's language.
   Measured in the U324 smoke run: a Dutch question, a delegation carrying the
   exact transcript, a Dutch paraphrase of the result.
2. **Given** he is speaking, **When** the robot's mic delivers audio, **Then**
   none of it reaches the session — unless `LIVE_BARGE_IN` (U324).
3. **Given** nobody speaks for `LIVE_SESSION_IDLE_S` and no lookup is in
   flight, **When** that passes, **Then** the session is closed on the server,
   not only on our side (U324).
4. **Given** a character set to an engine, **When** a turn arrives, **Then**
   that engine answers it, whatever the global says (U203, kept by the
   dispatch only since U324).

## Functional Requirements

- **FR-001**: Four speech paths exist and are selectable — globally and per
  character, and the turn goes to the engine `_engine()` names. (Until U324 it
  did not: `_realtime_turn` read only the global `VOICE_ENGINE`, so U203's
  per-character engine held in the resolver's tests and nowhere else.) Any
  change to language, wake behaviour or instruction text must be applied to
  **all four** or explicitly scoped to one, in the same unit.
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
- **FR-010**: A model is offered for a role only if it can fill it, and the
  Settings guard uses the **same** classifier as the offer. `gpt-live-*` and
  `*-realtime-translate` are offered for no role: measured, neither holds a
  voice or chat turn on the endpoints AURA uses (U321, ADR-011). The guard
  used to keep its own weaker copy of the classifier, which is how
  `gpt-live-1` was accepted as a Conversation model.
- **FR-011**: The pipeline never sends a realtime-only transcriber to
  `/v1/audio/transcriptions` (404 for `gpt-live-transcribe`); it uses the
  default and says so once. The realtime session has its own
  `REALTIME_STT_MODEL`, falling back to `STT_MODEL` (U321).
- **FR-012**: A new voice model is verified against **all three** session
  shapes, with the current model as a control, before it is pinned or made a
  default. `gpt-live-1` looked like the natural successor and serves none of
  them.
- **FR-013**: The OpenAI SDK is `>= 3.13` — the first with a Live API client —
  and `aura-brain` declares it directly rather than inheriting it, because a
  dependency that only arrives transitively is the shape of the `uv sync`
  pruning trap. A contract test pins every SDK resource the four speech paths
  and the orchestrator call, so a future major bump cannot remove one quietly
  (U322).
- **FR-021**: **Stop means now.** The panic stop cuts the current audio, drops
  every segment already queued for the speaker, and ends the session without
  waiting out the speaker tail. The tail exists so the mic teardown cannot clip
  the end of a reply (U157); after Stop there is no reply left to protect, and
  waiting it out *is* the "he keeps talking" the button exists to end. Both
  session engines behave identically, or the button means nothing in whichever
  one happens to be running (U333).
- **FR-022**: **Hushed means no open microphone.** While Quiet is on, a turn is
  never handed to a session that listens without a wake word. Measured in
  Present mode with a film playing: he answered the television's dialogue, line
  after line, under a header promising "he answers when asked and never speaks
  first" — because an open session makes whatever is loudest the one asking.
  Answering is untouched: the wake word gates every turn, which is what Quiet
  always meant (U333, U256).
- **FR-022b**: **And it keeps being true while he is already talking.** Quiet
  and Present end an OPEN session too, on the same one-second tick that
  notices Stop — a session holds the microphone for up to ten minutes, so a
  gate that only guards the start of a turn changes the header and nothing
  else. All three reasons end a conversation through one door and say which
  one they were; a session that ended deliberately is never retried through
  the pipeline, which would answer out loud the very question that was just
  silenced. The rule lives in one module (`aura_brain/hush.py`) because it was
  written in one place and needed in three, and a test fails when something
  that holds a microphone open does not ask it. A policy that cannot be read
  still never silences him: mute-by-accident is the fault nobody can diagnose
  (U366).
- **FR-020**: The Conversation engine setting says **where it applies** and
  **when it cannot**. It governs one path — a spoken turn the robot hears
  itself, after the wake word or inside the follow-up window; typed messages,
  the console's Talk button (which posts to `/voice/turn` and always runs the
  pipeline) and greetings use the conversation model whatever it says. With
  hands-free voice off it cannot be reached at all, and the row says so rather
  than looking effective. While Live is chosen, the realtime voice-model row
  says it is unused, because GPT-Live brings its own (U331, constitution XI).
- **FR-019**: Every speech path leaves the speaker at the same loudness. The
  whole-utterance path peak-normalises quiet TTS to 0.95 before the app volume;
  the streamed path gets there with **one gain per utterance**, decided on its
  first segment and never raised afterwards (raising it mid-sentence is the
  pumping U153 avoided; a louder later segment pulls it down, which is what
  prevents clipping). Measured: streamed replies peak at 0.35, so the speaker
  received 0.28 where the other path delivers 0.76 — about 9 dB quieter, and
  with `VOICE_ENGINE=realtime` that is **every** reply (U329).
- **FR-023**: A spoken line that changes persona halfway (spec 011 FR-108) is
  synthesized once per voice and reaches the robot as **one** utterance —
  concatenated in the brain, not sent as separate `speak` calls. FR-019 decides
  loudness per utterance, so separate calls would normalise each voice on its
  own and turn a change of character into a change of volume. Every segment
  comes from one provider at one sample rate (PCM s16le mono @ 24 kHz), which
  is what makes the join a byte concatenation; a second TTS provider would
  invalidate this and must revisit
  [ADR-012](../../../docs/adr/ADR-012-a-line-is-one-utterance-however-many-voices-it-has.md),
  not patch around it (U349).
- **FR-014**: GPT-Live opens with **client** delegation. Delegated work goes to
  the orchestrator's agentic loop with `announce=False`, so tools and the
  approval gate behave exactly as on the typed path; the result returns with
  `session.commentary.append`, clipped at a sentence to what one append carries
  (500 tokens). A failed lookup is reported as a fact through
  `session.thinking.append` — never an invented result, never a sentence to
  say (U292's rule) (U324).
- **FR-015**: Live output audio is gated on loudness (`LIVE_SILENCE_RMS`, 150)
  with a hangover (`LIVE_VOICE_HANGOVER_S`, 0.6 s). The model streams output
  continuously and 74–81 % of it is digital silence; played, or counted as
  speech, it would keep the half-duplex gate shut. A pause longer than the
  hangover ends an utterance — there is no end-of-response event — which
  publishes the reply and feeds the echo guard (U324).
- **FR-016**: Without echo cancellation the session is told
  `session.input_audio.mute` while he speaks plus `SELF_HEARING_COOLDOWN_S`,
  and `unmute` after. `LIVE_BARGE_IN=true` keeps listening and is for a robot
  with AEC only (U324).
- **FR-017**: A Live session hears the wake-window audio first (Live has no
  text input); closes after `LIVE_SESSION_IDLE_S` (45 s — a lookup in flight
  is not idleness), after `LIVE_SESSION_MAX_S`, or on the owner's Stop; and
  closing sends `session.close` and waits for `session.closed`, because
  billing stops on the server's word. When who is in the room changes, only the
  new room note is appended — Live's instructions append, they do not
  replace. `/voice/realtime-cost` reports Live's open time separately and says
  the orchestrator's own model calls are not in it (U324).
- **FR-018**: A failing Live session answers through the pipeline; two in a
  row disable Live until restart, and the log says so. A character's voice is
  passed to Live only if Live was measured to accept it (`marin`, `cedar`,
  `coral`, `verse`, `ash`, `sage`, `alloy`; `nova` was refused), otherwise
  `marin`; `LIVE_VOICE` overrides. `/voice/live-probe` and Settings' *Test
  Live access* open a session for a moment and close it (U324).

## Out of scope

- Which language a *person* is met in — that is stored per person in
  [018-knowledge-people-and-judgment](../018-knowledge-people-and-judgment/spec.md);
  this spec only consumes it.
- Tool calling and the agentic loop — see
  [019-skills-and-automation](../019-skills-and-automation/spec.md). Note that
  the realtime session path cannot call tools; that is why the pipeline exists.
  GPT-Live can, by delegating to the same loop (U324).

## Known divergence from ADR-005

ADR-005 describes a two-provider pluggable pipeline selected by
`STT_PROVIDER` / `TTS_PROVIDER`. It does not describe the speech paths, the
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
| U321 | `gpt-live-1` measured and not pinned (ADR-011); the classifier and the Settings guard stop offering and accepting models that serve neither endpoint; the pipeline guarded against a realtime-only transcriber; `REALTIME_STT_MODEL` |
| U322 | OpenAI SDK 2.33 → 3.13 (a major bump), declared by aura-brain itself, with a contract test for every resource AURA uses |
| U324 | GPT-Live as an opt-in fourth engine (`live_session.py`): delegation to the orchestrator, silence gate, mic mute, idle close, meter, probe, measured voices; the dispatch finally follows the per-character engine (U203) |
| U329 | Streamed speech was ~9 dB quieter than spoken speech: one loudness gain per utterance on the segment path, measured against a real reply |
| U331 | The engine row says which path it governs, warns when hands-free voice makes it unreachable, and marks the realtime voice model unused under Live |
| U333 | Stop drops queued audio and skips the speaker tail in both session engines; Quiet keeps the wake word in charge instead of letting the room talk |
| U366 | Quiet and Present end a conversation that is already running, within a tick, and a silenced turn is never re-asked out loud by the pipeline |
| U349 | A presentation beat carries its own character, and one line can change character halfway: per-beat voice and speed above the mode voice, and several voices joined into one utterance so the hand-over is not also a volume step (ADR-012) |
