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

    <!-- U75: screen-control banner with abort -->
    <div v-if="conversationStore.screenControl" class="agent-strip agent-strip--screen" role="status">
      <LoaderCircle :size="13" class="spin" />
      <span class="agent-round">AURA controls the screen (Esc also aborts)</span>
      <span style="flex:1" />
      <button type="button" class="btn-agent btn-agent--stop" @click="conversationStore.abortScreenControl()">Abort</button>
    </div>

    <!-- U62: live agentic-loop strip — rounds, steer input, stop -->
    <div v-if="conversationStore.agentRound" class="agent-strip" role="status">
      <LoaderCircle :size="13" class="spin" />
      <span class="agent-round">
        Working — round {{ conversationStore.agentRound.round }}/{{ conversationStore.agentRound.max }}
        <template v-if="conversationStore.agentRound.tools.length">
          · {{ conversationStore.agentRound.tools.join(', ') }}
        </template>
      </span>
      <input
        v-model="steerText"
        class="agent-steer-input"
        placeholder="Steer it… (e.g. 'only today, skip next week')"
        aria-label="Steer the agent"
        @keydown.enter.prevent="sendSteer"
      />
      <button type="button" class="btn-agent" :disabled="!steerText.trim()" @click="sendSteer">Steer</button>
      <button type="button" class="btn-agent btn-agent--stop" title="Wrap up after this round" @click="conversationStore.stopAgent()">Stop</button>
    </div>

    <div v-if="recording" class="mic-status mic-status--rec">
      <span class="rec-dot" /> Listening… tap the mic to send
      <span class="vu-meter" :title="`Mic level ${Math.round(micLevel * 100)}%`">
        <span v-for="n in 12" :key="n" class="vu-bar" :class="{ 'vu-bar--on': micLevel * 12 >= n }" />
      </span>
      <span v-if="micLevel < 0.02" class="vu-hint">(no sound yet — speak up)</span>
    </div>
    <p v-else-if="robotListening" class="mic-status mic-status--rec"><span class="rec-dot" /> Richie is listening on his own mic…</p>
    <p v-else-if="transcribing" class="mic-status">Transcribing your voice…</p>
    <p v-if="micError" class="mic-error">{{ micError }}</p>
    <p v-if="teachHint" class="mic-status">🎓 {{ teachHint }}</p>
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
        :disabled="transcribing || robotListening"
        :title="recording ? 'Stop & send' : 'Talk using the laptop mic'"
        @click="toggleMic"
      >
        <LoaderCircle v-if="transcribing" :size="15" class="spin" />
        <Square v-else-if="recording" :size="13" />
        <Mic v-else :size="15" />
      </button>
      <button
        type="button"
        :class="['btn-mic', robotListening && 'btn-mic--recording']"
        :disabled="recording || transcribing || robotListening"
        title="Talk using Richie's own microphone"
        @click="listenViaRobot"
      >
        <LoaderCircle v-if="robotListening" :size="15" class="spin" />
        <Bot v-else :size="15" />
      </button>
      <button
        type="button"
        class="btn-mic"
        :disabled="conversationStore.isProcessing"
        title="Teach: send the typed text as training feedback — the agent may propose a skill (you approve)"
        aria-label="Teach the assistant"
        @click="sendTeach"
      >
        <GraduationCap :size="15" />
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
import { Bot, GraduationCap, LoaderCircle, Mic, Sparkles, Square, Wrench } from 'lucide-vue-next'
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
const micLevel = ref(0) // 0..1 live input level so you can SEE the mic hears you

// U62: agent steering + teach-mode
const steerText = ref('')

function sendSteer(): void {
  const text = steerText.value.trim()
  if (!text) return
  conversationStore.steerAgent(text)
  steerText.value = ''
}

const teachHint = ref('')

function sendTeach(): void {
  const text = conversationStore.pendingText.trim()
  if (!text) {
    teachHint.value = 'Type the lesson in the input first, then press the cap — e.g. "always run tests before deploying".'
    setTimeout(() => { teachHint.value = '' }, 6000)
    return
  }
  teachHint.value = ''
  conversationStore.pendingText = ''
  conversationStore.teach(text)
}
let recorder: MediaRecorder | null = null
let chunks: Blob[] = []
let mimeType = 'audio/webm'
let audioCtx: AudioContext | null = null
let levelRaf = 0

function startLevelMeter(stream: MediaStream) {
  try {
    audioCtx = new AudioContext()
    const src = audioCtx.createMediaStreamSource(stream)
    const analyser = audioCtx.createAnalyser()
    analyser.fftSize = 512
    src.connect(analyser)
    const data = new Uint8Array(analyser.frequencyBinCount)
    const tick = () => {
      analyser.getByteTimeDomainData(data)
      let sum = 0
      for (const v of data) { const c = (v - 128) / 128; sum += c * c }
      const rms = Math.sqrt(sum / data.length)
      micLevel.value = Math.min(1, rms * 3) // scale for visibility
      levelRaf = requestAnimationFrame(tick)
    }
    tick()
  } catch { /* meter is best-effort */ }
}

function stopLevelMeter() {
  cancelAnimationFrame(levelRaf)
  micLevel.value = 0
  audioCtx?.close().catch(() => {})
  audioCtx = null
}

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
      stopLevelMeter()
      stream.getTracks().forEach(t => t.stop())
      recording.value = false
      await sendVoice(new Blob(chunks, { type: recorder?.mimeType || mimeType || 'audio/webm' }))
    }
    recorder.start()
    recording.value = true
    startLevelMeter(stream)
  } catch {
    stopLevelMeter()
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

// Talk via the ROBOT's own microphone (U45): the Pi records, the brain
// transcribes, the reply is spoken back on the robot.
const robotListening = ref(false)

async function listenViaRobot() {
  if (robotListening.value) return
  robotListening.value = true
  micError.value = ''
  try {
    const resp = await fetch(`${BRAIN_URL}/voice/listen`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ duration_s: 5 }),
    })
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}))
      micError.value = body.error ?? `Robot mic failed (${resp.status})`
    }
    // Turns render via the event stream (TranscriptUpdated + ResponseDrafted).
  } catch {
    micError.value = 'Could not reach the brain.'
  } finally {
    robotListening.value = false
  }
}

onUnmounted(() => { if (recording.value) recorder?.stop(); stopLevelMeter() })
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
.vu-meter { display: inline-flex; align-items: flex-end; gap: 2px; height: 14px; margin-left: 0.2rem; }
.vu-bar { width: 3px; height: 100%; border-radius: 1px; background: var(--border); transition: background 0.06s; }
.vu-bar--on { background: var(--ok); }
.vu-hint { color: var(--text-faint); font-size: 0.68rem; }
.spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* U62: agent-activity strip */
.agent-strip {
  display: flex; align-items: center; gap: 0.5rem;
  padding: 0.4rem 0.6rem; margin-bottom: 0.5rem;
  background: var(--surface-2); border: 1px solid var(--border-strong);
  border-radius: var(--radius-md); font-size: 0.75rem;
}
.agent-round { color: var(--text-faint); white-space: nowrap; }
.agent-steer-input {
  flex: 1; min-width: 80px; background: var(--surface);
  border: 1px solid var(--border-strong); border-radius: var(--radius-sm, 4px);
  color: var(--text); padding: 0.25rem 0.45rem; font-size: 0.75rem;
}
.btn-agent {
  border: 1px solid var(--border-strong); background: transparent; color: var(--text);
  border-radius: var(--radius-sm, 4px); padding: 0.25rem 0.55rem;
  font-size: 0.72rem; cursor: pointer;
}
.btn-agent:disabled { opacity: 0.5; cursor: default; }
.btn-agent--stop { color: var(--danger-text, #e5484d); border-color: var(--danger-text, #e5484d); }
.agent-strip--screen { border-color: var(--accent); box-shadow: 0 0 12px color-mix(in srgb, var(--accent) 35%, transparent); }
</style>
