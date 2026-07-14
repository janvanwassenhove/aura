<template>
  <section class="panel flex flex-col h-full">
    <h2 class="panel-title">Conversation</h2>

    <div ref="scrollEl" class="conversation-scroll flex-1 overflow-y-auto space-y-2 mb-3">
      <div
        v-for="turn in conversationStore.turns"
        :key="turn.id"
        :class="['turn', turn.role === 'user' ? 'turn-user' : 'turn-assistant']"
      >
        <div class="turn-header">
          <span class="turn-role">{{ turn.role === 'user' ? 'You' : 'AURA' }}</span>
          <span class="turn-time">{{ fmtTime(turn.timestamp) }}</span>
        </div>
        <div class="turn-text">{{ turn.text }}</div>
        <div v-if="turn.toolCall" :class="['tool-badge', `tool-${turn.toolCall.status}`]">
          <Wrench :size="11" /> {{ turn.toolCall.name }} — {{ turn.toolCall.status }}
        </div>
      </div>
      <div v-if="conversationStore.isProcessing" class="turn turn-assistant">
        <div class="turn-text animate-pulse">AURA is thinking…</div>
      </div>
      <div v-if="conversationStore.turns.length === 0" class="getting-started">
        <h3 class="gs-title"><Sparkles :size="14" /> Talk to your robot</h3>
        <p class="gs-line">Type below and press <strong>Send</strong> — the reply appears here.</p>
        <div class="gs-suggestions">
          <button v-for="s in suggestions" :key="s" class="gs-chip" @click="trySuggestion(s)">{{ s }}</button>
        </div>
        <p class="gs-line gs-muted">
          Make the robot move with the <strong>Quick Actions</strong> on the left, watch what it
          sees in <strong>Robot Camera</strong>, and teach it your face with <strong>This is me</strong>.
        </p>
      </div>
    </div>

    <div v-if="conversationStore.lastLatency" class="latency-bar text-xs text-gray-400 mb-2">
      Last turn: {{ conversationStore.lastLatency.total_ms.toFixed(0) }}ms total
      (LLM {{ conversationStore.lastLatency.llm_ms.toFixed(0) }}ms
      + tools {{ conversationStore.lastLatency.tool_ms.toFixed(0) }}ms)
    </div>

    <p v-if="recording" class="mic-status mic-status--rec"><span class="rec-dot" /> Listening… tap the mic to send</p>
    <p v-else-if="transcribing" class="mic-status">Transcribing your voice…</p>
    <p v-if="micError" class="mic-error">{{ micError }}</p>
    <form class="input-row" @submit.prevent="submit">
      <input
        v-model="conversationStore.pendingText"
        type="text"
        placeholder="Type a message… or use the mic"
        :disabled="conversationStore.isProcessing"
        class="chat-input"
      />
      <button
        type="button"
        :class="['btn-mic', recording && 'btn-mic--recording']"
        :disabled="transcribing"
        :title="recording ? 'Stop & send' : 'Talk to the robot'"
        @click="toggleMic"
      >
        <LoaderCircle v-if="transcribing" :size="15" class="spin" />
        <Square v-else-if="recording" :size="13" />
        <Mic v-else :size="15" />
      </button>
      <button
        type="submit"
        :disabled="conversationStore.isProcessing || !conversationStore.pendingText.trim()"
        class="btn-primary"
      >
        {{ conversationStore.isProcessing ? '…' : 'Send' }}
      </button>
    </form>
  </section>
</template>

<script setup lang="ts">
import { onUnmounted, ref, watch, nextTick } from 'vue'
import { LoaderCircle, Mic, Sparkles, Square, Wrench } from 'lucide-vue-next'
import { useConversationStore } from '../stores/conversationStore'

const BRAIN_URL = import.meta.env.VITE_BRAIN_URL ?? import.meta.env.VITE_ORCHESTRATOR_URL ?? 'http://localhost:8000'

const conversationStore = useConversationStore()
const scrollEl = ref<HTMLElement | null>(null)

const suggestions = [
  'What can you do?',
  'What meetings do I have today?',
  'Tell me a fun fact',
]

async function trySuggestion(text: string) {
  conversationStore.pendingText = text
  await submit()
}

async function submit() {
  const text = conversationStore.pendingText.trim()
  if (!text) return
  conversationStore.pendingText = ''
  await conversationStore.submitTurn(text)
}

watch(
  () => conversationStore.turns.length,
  async () => {
    await nextTick()
    if (scrollEl.value) scrollEl.value.scrollTop = scrollEl.value.scrollHeight
  },
)

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString()
}

// ── Voice input (U36e): record on the laptop mic, transcribe in the brain ──

const recording = ref(false)
const transcribing = ref(false)
const micError = ref('')
let recorder: MediaRecorder | null = null
let chunks: Blob[] = []
let mimeType = 'audio/webm'

function pickMimeType(): string {
  const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4']
  for (const t of candidates) {
    if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(t)) return t
  }
  return ''
}

async function toggleMic() {
  micError.value = ''
  if (recording.value) {
    recorder?.stop()
    return
  }
  if (!navigator.mediaDevices?.getUserMedia) {
    micError.value = 'No microphone API available in this window.'
    return
  }
  let stream: MediaStream
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  } catch (err: any) {
    micError.value = err?.name === 'NotAllowedError'
      ? 'Microphone permission denied — allow it in your OS settings.'
      : 'No microphone found — is one connected?'
    return
  }
  try {
    mimeType = pickMimeType()
    chunks = []
    recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream)
    recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data) }
    recorder.onstop = async () => {
      stream.getTracks().forEach(t => t.stop())
      recording.value = false
      await sendVoice(new Blob(chunks, { type: recorder?.mimeType || mimeType || 'audio/webm' }))
    }
    recorder.start()
    recording.value = true
  } catch {
    stream.getTracks().forEach(t => t.stop())
    micError.value = 'Recording is not supported in this window.'
  }
}

function extFor(mime: string): string {
  if (mime.includes('ogg')) return 'audio.ogg'
  if (mime.includes('mp4')) return 'audio.mp4'
  return 'audio.webm'
}

async function sendVoice(blob: Blob) {
  if (blob.size < 400) {
    micError.value = 'That was too short — hold the mic while you speak.'
    return
  }
  transcribing.value = true
  try {
    const form = new FormData()
    form.append('audio', blob, extFor(blob.type))
    const resp = await fetch(`${BRAIN_URL}/voice/turn`, { method: 'POST', body: form })
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}))
      micError.value = body.error ?? `Voice turn failed (${resp.status})`
    }
    // On success the turns render via the event stream (TranscriptUpdated +
    // ResponseDrafted) — no local add needed.
  } catch {
    micError.value = 'Could not reach the brain.'
  } finally {
    transcribing.value = false
  }
}

onUnmounted(() => { if (recording.value) recorder?.stop() })
</script>

<style scoped>
.getting-started {
  border: 1px dashed var(--border); border-radius: var(--radius);
  padding: 0.9rem 1rem; color: var(--text-muted); font-size: 0.82rem;
}
.gs-title { display: flex; align-items: center; gap: 0.4rem; font-weight: 600; color: var(--text); margin-bottom: 0.4rem; }
.gs-line { margin: 0.25rem 0; }
.gs-muted { color: var(--text-faint); font-size: 0.76rem; }
.gs-suggestions { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0.5rem 0; }
.gs-chip {
  background: var(--surface-3); border: 1px solid var(--border); border-radius: 999px;
  color: var(--text-muted); font-size: 0.75rem; padding: 0.25rem 0.7rem; cursor: pointer;
}
.gs-chip:hover { color: var(--text); border-color: var(--accent-border); }

.btn-mic {
  display: inline-flex; align-items: center; justify-content: center;
  width: 38px; border-radius: var(--radius);
  background: var(--surface-3); border: 1px solid var(--border);
  color: var(--text-muted); cursor: pointer;
}
.btn-mic:hover:not(:disabled) { color: var(--text); border-color: var(--accent-border); }
.btn-mic--recording { background: var(--danger-bg); border-color: var(--danger); color: var(--danger); animation: pulse 1.2s infinite; }
.mic-error { font-size: 0.72rem; color: var(--danger-text); margin: 0 0 0.3rem; }
.mic-status { font-size: 0.72rem; color: var(--text-muted); margin: 0 0 0.3rem; display: flex; align-items: center; gap: 0.35rem; }
.mic-status--rec { color: var(--danger); }
.rec-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--danger); animation: pulse 1.2s infinite; }
.spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
