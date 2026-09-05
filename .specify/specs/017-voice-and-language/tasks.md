---
feature: "017-voice-and-language"
---

# Tasks: Voice and Language

Retro-specified; all done. Grouped so a requirement can be traced to the unit
that satisfied it.

## Phase 1: Hearing and speaking at all

- [x] T001 [U22] Realtime API voice transport state machine
- [x] T002 [U36b, U36e, U45, U46] The robot speaks; volume; its own microphone
- [x] T003 [U80, U81, U82, U83] Speech cut off, chopped, inaudible — buffer, GStreamer playbin, ALSA
- [x] T004 [U155, U156] Gapless `appsrc` playback; AEC groundwork with an honest verdict

## Phase 2: Being addressed

- [x] T005 [U47, U85, U87, U96] Hands-free wake word, fuzzy match, bare wake as command
- [x] T006 [U128] Local on-device wake word, fallback returns None
- [x] T007 [U54, U73] Streamed TTS and barge-in, gated on the wake word
- [x] T008 [U67, U88, U91, U92, U148, U258] Self-hearing, the spoken label, prompt echo, phantom turns, waking himself
- [x] T009 [U49, U69, U135, U256, U257, U275] Hallucinated wakes, lyrics, Quiet mode, "hallo", and the wake he heard but ignored
- [x] T010 [U86, U163] VAD gate for a quiet mic; AGC no longer inflating room tone
- [x] T011 [U84, U149, U150, U154] Conversation state machine; endpointing conservative, then off by default; continuous session

## Phase 3: Realtime, honestly

- [x] T012 [U129, U132] Wake-gated realtime turn; cost meter; engine toggle in Settings
- [x] T013 [U133, U134] Timeout + circuit breaker; the gating bug that meant it never triggered
- [x] T014 [U140, U141, U142, U143] Instrumentation; the no-audio finding; the access self-check; model detection
- [x] T015 [U144, U146, U153] GA API migration; right answer and right labels; play on the first segment
- [x] T016 [U203, U209] Voice with tools by default; laptop speakers

## Phase 4: One language, and staying in it

- [x] T017 [U36h, U130, U131] Switchable language and configurable call name
- [x] T018 [U287] Pin the STT language; drop foreign scripts (pipeline)
- [x] T019 [U288] The person he can see outranks the household default; two people fall back
- [x] T020 [U289] The same pinning in the realtime **session** path
- [x] T021 [U291] The language rule is appended unconditionally, persona-proof
- [x] T022 [U292] No machinery in the instructions, and no sentence to stall with
- [x] T023 [U260, U273] Greeted then deaf; name which "Voice" setting wins
