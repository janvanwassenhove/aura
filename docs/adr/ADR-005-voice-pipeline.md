# ADR-005: Voice Pipeline Design

**Status**: Accepted  
**Date**: 2026-04-25  
**Deciders**: AURA Platform Team

---

## Context

AURA needs speech-to-text (STT) and text-to-speech (TTS) capabilities. The key tensions are:
- **Latency**: Cloud APIs (OpenAI Realtime) offer lower latency (~300ms); local models add 800ms+
- **Offline capability**: Cloud APIs require internet; local models work offline
- **Quality**: Cloud TTS is more natural; local TTS (Kokoro/Piper) has improved significantly
- **Cost**: Cloud API calls accumulate; local models are compute-cost only
- **Development convenience**: Local models work in all environments without API keys

We need to support both paths without duplicating voice logic across the codebase.

---

## Decision

**Default STT**: OpenAI Realtime API (WebSocket, `STT_PROVIDER=openai_realtime`)  
**Default TTS**: OpenAI Realtime API (streaming audio, `TTS_PROVIDER=openai`)  
**Fallback STT**: Local Whisper (`STT_PROVIDER=local_whisper`)  
**Fallback TTS**: Kokoro or Piper (`TTS_PROVIDER=kokoro` | `TTS_PROVIDER=piper`)  
**Selection**: Environment variables — no code changes required to switch providers  
**Abstraction**: `STTProvider` and `TTSProvider` ABCs in `packages/shared-schemas`  

---

## Provider Comparison

| Dimension | OpenAI Realtime | Local Whisper+Kokoro |
|-----------|-----------------|----------------------|
| First-word latency | ~300ms | ~800ms+ |
| Requires internet | Yes | No |
| Requires API key | Yes | No |
| Interruption support | Native | Requires VAD |
| Word-level timing | Yes | Requires alignment |
| Cost | Per-token | Compute only |
| Best for | Production demos | Development, offline |

---

## STTProvider and TTSProvider ABCs

```python
class STTProvider(ABC):
    async def transcribe(self, audio_bytes: bytes) -> str: ...
    async def stream_transcribe(self, audio_stream: AsyncIterator[bytes]) -> AsyncIterator[str]: ...

class TTSProvider(ABC):
    async def synthesize(self, text: str) -> bytes: ...
    async def stream_synthesize(self, text: str) -> AsyncIterator[bytes]: ...
```

---

## Rationale

### OpenAI Realtime as Default
- WebSocket-based with sub-300ms first-word latency
- Handles interruption detection natively
- Single session for both STT and TTS — reduces round trips
- Streaming audio reduces perceived latency further
- Most appropriate for a deployed embodied assistant

### Local Whisper as Development Default
- Works without internet or API keys
- `tiny` model runs on CPU in <2s for 2s audio; `small` model is more accurate
- `openai-whisper` pip package is easy to install
- Enables CI testing without secrets

### Kokoro and Piper as TTS Fallbacks
- Both generate natural-sounding speech locally
- Kokoro: higher quality, more voices
- Piper: extremely fast, lower resource usage
- Both produce WAV/PCM output that can be passed to `play_audio()` on the robot adapter

### Pluggable via Environment Variables
- Avoids if/else branching in the conversation runtime
- Contributors can test locally with `STT_PROVIDER=local_whisper` without credentials
- Production deployment switches to `openai_realtime` via `.env` only

### Interruption Handling
- OpenAI Realtime: native; server detects user speech during AURA output
- Local: Voice Activity Detection (VAD) using `webrtcvad` monitors microphone while playing audio
- Both providers must support `interrupt()` method (added to `STTProvider` ABC)

---

## Consequences

### Positive
- All voice flows testable locally without API keys
- Clear upgrade path: start with local Whisper in dev, switch to Realtime for prod
- Interruption is supported by both providers
- Provider-specific latency profiles are documented for product decisions

### Negative
- Two provider implementations to maintain
- Local Whisper model download at startup adds cold-start time
- Testing interruption with local VAD requires audio hardware or a simulated audio stream

### Neutral
- OpenAI Realtime API pricing applies in production; cost monitoring should be set up separately
- Kokoro and Piper require separate pip dependencies (not bundled)

---

## Alternatives Considered

| Option | Reason Rejected |
|--------|----------------|
| OpenAI Realtime only | No offline capability; dev requires API key |
| Local Whisper only | Unacceptable latency for production demos |
| ElevenLabs TTS | Additional API dependency; higher cost; not self-hostable |
| Coqui TTS | Project archived; less maintained than Kokoro/Piper |
| Azure Cognitive Services | Adds MSAL complexity for another provider; not needed |
| Deepgram | Another cloud dependency; similar tradeoffs to OpenAI Realtime |
