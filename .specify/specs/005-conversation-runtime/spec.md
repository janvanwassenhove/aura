---
feature: "005-conversation-runtime"
status: "in-progress"
owner: "conversation-runtime"
priority: P1
risk: Medium
created: "2026-04-25"
---

# Feature Specification: Conversation Runtime

**Feature Branch**: `005-conversation-runtime`
**Created**: 2026-04-25
**Status**: In Progress
**Owner**: conversation-runtime
**Priority**: P1
**Risk**: Medium

## User Scenarios & Testing

### User Story 1 — Text Turn Completes End-to-End (Priority: P1)

A developer can send a text message via the operator console REST API and receive a text response from the LLM, with the turn visible in the session transcript.

**Why this priority**: The text path is the simplest integration test and must work before audio is added. Validates the full pipeline without audio hardware or cloud voice APIs.

**Independent Test**: `POST /conversation/turn` with `{"text": "What meetings do I have today?"}` returns 200 with `{"response_text": "...", "session_id": "..."}` within 5 seconds.

**Acceptance Scenarios**:

1. **Given** the conversation-runtime is running, **When** a text turn is submitted via REST, **Then** a session is created (or resumed), the text is passed to the LLM, and the response is returned.
2. **Given** an active session, **When** a follow-up turn is submitted with the same `session_id`, **Then** the context from the previous turn is included in the LLM prompt.
3. **Given** any turn, **When** it completes, **Then** `IntentRecognized` and `ResponseDrafted` events are emitted on the bus.
4. **Given** a turn with an error from the LLM, **When** the error occurs, **Then** a fallback response is returned and `ToolCallFailed` event is emitted.

---

### User Story 2 — Voice Turn via OpenAI Realtime (Priority: P1)

When `STT_PROVIDER=openai_realtime`, AURA uses the OpenAI Realtime WebSocket API for low-latency speech-to-text and synthesizes responses via the same session.

**Why this priority**: This is the primary voice path. Medium risk because it depends on cloud API availability.

**Independent Test**: Set `STT_PROVIDER=openai_realtime`, call `capture_audio()` with 2 seconds of silence, assert no crash and `UserSpeechDetected` event is emitted (or not, for silence).

**Acceptance Scenarios**:

1. **Given** `STT_PROVIDER=openai_realtime` and a valid `OPENAI_API_KEY`, **When** audio input is provided, **Then** the Realtime API session is established and transcription begins.
2. **Given** a voice turn in progress, **When** the user stops speaking, **Then** the transcript is finalized within 500ms and passed to the LLM.
3. **Given** an interruption during AURA's speech, **When** user speech is detected, **Then** the current TTS output is stopped and a new turn begins.
4. **Given** the Realtime API is unavailable, **When** a voice turn is attempted, **Then** the system falls back to local Whisper (if configured) or returns an error with clear message.

---

### User Story 3 — Voice Turn via Local Whisper (Priority: P1)

When `STT_PROVIDER=local_whisper`, AURA uses the local Whisper model for speech-to-text without any cloud dependency.

**Why this priority**: Offline capability is a core product requirement. Developers must be able to test voice flows without cloud access.

**Independent Test**: Set `STT_PROVIDER=local_whisper LOCAL_WHISPER_MODEL=tiny`, record 2 seconds of audio, assert `UserSpeechDetected` event is emitted within 2000ms.

**Acceptance Scenarios**:

1. **Given** `STT_PROVIDER=local_whisper` and a local Whisper model, **When** audio input is provided, **Then** transcription is produced locally.
2. **Given** local Whisper running with `tiny` model, **When** 2s of speech is transcribed, **Then** result is available within 2 seconds.
3. **Given** local Whisper, **When** `TTS_PROVIDER=kokoro`, **Then** synthesized speech is generated locally without network calls.
4. **Given** local Whisper, **When** `TTS_PROVIDER=piper`, **Then** synthesized speech is generated locally with Piper TTS.

---

### User Story 4 — Session Transcript Is Persisted (Priority: P2)

Each session's transcript (user turns + AURA responses) is persisted to the memory service and retrievable by session ID.

**Why this priority**: Enables conversation history and context for multi-turn interactions.

**Independent Test**: Complete 3 turns; call `GET /session/{session_id}/transcript`; assert 6 entries (3 user + 3 AURA).

**Acceptance Scenarios**:

1. **Given** a completed turn, **When** `GET /session/{session_id}/transcript` is called, **Then** the user and AURA messages appear in order.
2. **Given** a session older than 24 hours, **When** it is loaded, **Then** historical turns are included in the LLM context window (up to the configured limit).

---

### Edge Cases

- What happens when the LLM returns a tool call? → `ToolCallRequested` event is emitted; conversation-runtime waits for `ToolCallSucceeded` or `ToolCallFailed` before generating the final response.
- What happens when audio input is silence? → `UserSpeechDetected` is NOT emitted; the session returns to idle.
- What happens if `OPENAI_API_KEY` is missing and `STT_PROVIDER=openai_realtime`? → Service starts but voice turns return a clear error; text turns still work.

---

## Requirements

### Functional Requirements

- **FR-001**: `conversation-runtime` MUST expose `POST /conversation/turn` accepting `{text, session_id?}`.
- **FR-002**: `conversation-runtime` MUST expose `GET /session/{session_id}/transcript`.
- **FR-003**: `STTProvider` ABC MUST be defined in `shared-schemas` with methods `transcribe(audio_bytes) -> str` and `stream_transcribe(audio_stream) -> AsyncIterator[str]`.
- **FR-004**: `TTSProvider` ABC MUST be defined in `shared-schemas` with methods `synthesize(text) -> bytes` and `stream_synthesize(text) -> AsyncIterator[bytes]`.
- **FR-005**: `OpenAIRealtimeSTT` and `OpenAIRealtimeTTS` MUST implement their respective ABCs.
- **FR-006**: `LocalWhisperSTT` MUST implement `STTProvider` using the `openai-whisper` package.
- **FR-007**: `KokoroTTS` and `PiperTTS` MUST implement `TTSProvider`.
- **FR-008**: Provider selection MUST be via `STT_PROVIDER` and `TTS_PROVIDER` environment variables.
- **FR-009**: `IntentRecognized` and `ResponseDrafted` events MUST be emitted for every turn.
- **FR-010**: Conversation context MUST include the last N turns (configurable, default: 10).

### Key Entities

- **Session**: `session_id`, `persona`, `turns`, `created_at`, `updated_at`.
- **Turn**: `role` (user|assistant), `text`, `audio_bytes?`, `timestamp`.
- **STTProvider**: ABC for speech-to-text.
- **TTSProvider**: ABC for text-to-speech.

---

## Success Criteria

### Measurable Outcomes

- **SC-001**: Text turn end-to-end latency < 5 seconds (LLM call included).
- **SC-002**: OpenAI Realtime voice turn first word latency < 500ms (cloud, good conditions).
- **SC-003**: Local Whisper tiny model transcription latency < 2 seconds for 2s audio.
- **SC-004**: `pytest services/conversation-runtime/tests/` passes 100%.
- **SC-005**: `STTProvider` and `TTSProvider` contract tests pass for all 4 implementations.

---

## Assumptions

- LLM provider is OpenAI (or OpenAI-compatible API) in the initial implementation.
- A valid `OPENAI_API_KEY` is required for cloud voice and LLM calls; local path works without it.
- Whisper model files are downloaded at service startup if not present.
- The conversation runtime does not make tool calls itself — it emits `ToolCallRequested` events and waits.

---

## References

- [Constitution](.specify/memory/constitution.md) — Principle V (Voice Pipeline is Pluggable)
- [ADR-005](docs/adr/ADR-005-voice-pipeline.md)
- [Spec 003 — Event Bus](../003-event-bus-schemas/spec.md)
- [Spec 006 — Orchestrator](../006-orchestrator-foundation/spec.md)
