# conversation-runtime

**Port**: 8002  
**Spec**: [005-conversation-runtime](../../.specify/specs/005-conversation-runtime/spec.md)

## Responsibilities

- Manages conversation sessions (create, resume, persist)
- Accepts text turns via REST and audio turns via WebSocket
- Routes audio to the configured STT provider (OpenAI Realtime or local Whisper)
- Calls the LLM (OpenAI GPT-4o) for intent recognition and response generation
- Routes response text to the configured TTS provider
- Emits `IntentRecognized`, `ResponseDrafted`, `TranscriptUpdated` events
- Persists turns to the memory service

## Key Interfaces

- `STTProvider` — ABC in `shared-schemas`: `transcribe()`, `stream_transcribe()`
- `TTSProvider` — ABC in `shared-schemas`: `synthesize()`, `stream_synthesize()`
- `OpenAIRealtimeSTT` / `OpenAIRealtimeTTS` — cloud path
- `LocalWhisperSTT` — offline path
- `KokoroTTS` / `PiperTTS` — offline TTS
- REST: `POST /conversation/turn`, `GET /session/{id}/transcript`
- WebSocket: `/ws/audio` — streaming audio input

## Running Locally

```bash
cd services/conversation-runtime
cp ../../infra/dev/.env.example .env
uv run uvicorn conversation_runtime.main:app --reload --port 8002
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `STT_PROVIDER` | `local_whisper` | `openai_realtime` or `local_whisper` |
| `TTS_PROVIDER` | `kokoro` | `openai`, `kokoro`, or `piper` |
| `OPENAI_API_KEY` | — | Required for `openai_realtime` |
| `LOCAL_WHISPER_MODEL` | `tiny` | Whisper model size |
| `LOCAL_TTS_BACKEND` | `kokoro` | Fallback TTS backend |
| `MAX_CONTEXT_TURNS` | `10` | Session turns to include in LLM context |

## Tests

```bash
uv run pytest tests/
uv run pytest ../../tests/contract/test_stt_provider_contract.py --provider=local_whisper
```

## Architecture Notes

- When the LLM returns a tool call, `ToolCallRequested` event is emitted and this service waits for `ToolCallSucceeded` or `ToolCallFailed`
- Session state (turns) is persisted via `POST /session/{id}/turns` on the memory service
- Missing `OPENAI_API_KEY` → text turns still work; voice turns return an error
