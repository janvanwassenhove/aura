---
spec: "005-conversation-runtime"
plan: "005-conversation-runtime"
status: in-progress
created: "2026-04-25"
---

# 005 — Conversation Runtime: Tasks

## Task Group 1: LLM Integration

- [x] **T-005-01** Create `conversation_runtime/llm.py` — `openai_chat(messages, tools)` async wrapper
  - Reads `LLM_PROVIDER` env var (`openai` | `echo`)
  - `echo` mode returns `[echo] {last_user_message}` — no API key needed
  - `openai` mode calls `AsyncOpenAI.chat.completions.create`
  - Never logs message content; logs only token counts at DEBUG

- [x] **T-005-02** Wire `POST /conversation/turn` to LLM
  - Replace echo stub with `llm.openai_chat()`
  - Emit `IntentRecognized` + `ResponseDrafted` events after reply
  - Persist user turn + assistant turn to memory-service via `httpx.AsyncClient`

- [x] **T-005-03** Wire `WS /conversation/audio/{session_id}` to LLM
  - Replace echo stub with STT → `llm.openai_chat()` → TTS
  - Stream TTS bytes back over WebSocket

## Task Group 2: Session Persistence

- [x] **T-005-04** Add `MEMORY_SERVICE_URL` env var to `conversation_runtime/main.py`
  - Default: `http://memory-service:8005`
  - Inject `httpx.AsyncClient` into routes via `routes.init(..., memory_url=...)`

- [x] **T-005-05** Persist turns to memory-service after each text/audio turn
  - POST user turn: `{"session_id": ..., "role": "user", "content": text}`
  - POST assistant turn: `{"session_id": ..., "role": "assistant", "content": reply}`

## Task Group 3: Tests

- [x] **T-005-06** `tests/test_text_turn.py` — text turn end-to-end with `LLM_PROVIDER=echo` ✓
  - POST `/conversation/turn {"text": "hello", "session_id": "test"}` → 200 `{"reply": "[echo] hello"}`

- [x] **T-005-07** `tests/test_session.py` ✓ — 5 tests pass (create, unique IDs, end session, graceful 404, turn count)
  - Need: Create session, touch, end; assert counts
