---
spec: "005-conversation-runtime"
status: draft
created: 2025-01-01
---

# 005 — Conversation Runtime: Implementation Plan

## Summary

Implement the conversation pipeline in `conversation-runtime`: text turns via REST, streaming audio via WebSocket, STT/TTS provider plug-in architecture, and session turn persistence via the memory service.

## Technical Context

- `STTProvider` ABC: `transcribe(audio_bytes) → str`, `stream_transcribe(audio_stream) → AsyncIterator[str]`
- `TTSProvider` ABC: `synthesize(text) → bytes`, `stream_synthesize(text) → AsyncIterator[bytes]`
- Implementations: `OpenAIRealtimeSTT`, `LocalWhisperSTT`, `OpenAIRealtimeTTS`, `KokoroTTS`, `PiperTTS`
- Text turns: `POST /conversation/turn` → transcription → LLM → response
- Audio turns: WebSocket `/ws/audio` → stream → transcription → LLM → response audio
- Session turns persisted to memory-service via `httpx.AsyncClient`

## Constitution Check

| Principle | Gate | Status |
|-----------|------|--------|
| Pluggable Voice | STT and TTS selected by env vars at startup | ✅ |
| No Sensitive Data in Logs | Audio bytes and transcriptions logged at DEBUG only with `[TRUNCATED]` suffix | ✅ |
| Events Drive State | `TranscriptUpdated`, `IntentRecognized`, `ResponseDrafted` emitted | ✅ |
| Hardware Abstraction | LLM calls go through OpenAI SDK only; no vendor lock in session logic | ✅ |

## Project Structure

```
packages/shared-schemas/src/shared_schemas/
├── voice/
│   ├── __init__.py
│   └── providers.py       # STTProvider, TTSProvider ABCs

services/conversation-runtime/src/conversation_runtime/
├── main.py                # FastAPI routes
├── session.py             # SessionManager — create, resume, persist
├── turn.py                # process_text_turn(), process_audio_turn()
├── llm.py                 # openai_chat() wrapper
├── stt/
│   ├── __init__.py
│   ├── factory.py         # get_stt_provider(env)
│   ├── openai_realtime.py # OpenAIRealtimeSTT
│   └── local_whisper.py   # LocalWhisperSTT
└── tts/
    ├── __init__.py
    ├── factory.py         # get_tts_provider(env)
    ├── openai.py          # OpenAIRealtimeTTS
    ├── kokoro.py          # KokoroTTS
    └── piper.py           # PiperTTS
```

## Implementation Steps

### Phase 1: ABCs (shared-schemas)

```python
class STTProvider(ABC):
    @abstractmethod
    async def transcribe(self, audio_bytes: bytes) -> str: ...
    @abstractmethod
    async def stream_transcribe(self, audio_stream: AsyncIterator[bytes]) -> AsyncIterator[str]: ...

class TTSProvider(ABC):
    @abstractmethod
    async def synthesize(self, text: str) -> bytes: ...
    @abstractmethod
    async def stream_synthesize(self, text: str) -> AsyncIterator[bytes]: ...
```

### Phase 2: STT Providers

- `LocalWhisperSTT` — calls `whisper.cpp` via subprocess; model loaded once at startup
- `OpenAIRealtimeSTT` — opens WebSocket to OpenAI Realtime API; streams audio in chunks

### Phase 3: TTS Providers

- `KokoroTTS` — calls `kokoro` Python package; returns WAV bytes
- `PiperTTS` — calls `piper` subprocess; returns WAV bytes
- `OpenAIRealtimeTTS` — calls OpenAI TTS endpoint via SDK

### Phase 4: Session Manager

```python
class SessionManager:
    async def create_session(self) -> str        # returns session_id
    async def get_turns(self, session_id: str) -> list[Turn]
    async def append_turn(self, session_id: str, turn: Turn) -> None
```

Persists turns via `POST http://memory-service:8005/session/{id}/turns`.

### Phase 5: REST and WebSocket Routes

- `POST /conversation/turn` — `{"text": str, "session_id": str?}` → `{"response": str, "session_id": str}`
- `GET /session/{id}/transcript` → list of turns
- `WebSocket /ws/audio` — binary frames → transcription → response audio streamed back

### Phase 6: Events

Emit in order:
1. `AudioInputStarted` (WebSocket path only)
2. `UserSpeechDetected` with `transcript` after STT
3. `TranscriptUpdated`
4. `IntentRecognized` (after LLM call)
5. `ResponseDrafted` with `response_text`

### Phase 7: Tests

1. `test_text_turn_returns_response` — mock LLM; verify response in body
2. `test_transcript_persisted` — verify memory service POST called
3. `test_stt_provider_factory` — `local_whisper` selected by default
4. Contract tests in `tests/contract/test_stt_provider_contract.py` — `transcribe(silence_bytes)` returns str

## Complexity Tracking

- Python files: ~12 files, ~450 lines
- Dependencies: `openai`, `httpx`, `piper-tts` or `kokoro` (optional at install time)
