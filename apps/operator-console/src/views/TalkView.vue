<template>
  <main class="talk">
    <div class="talk-cols">
      <!-- ═══ The conversation, with presence inside it at every density ═══ -->
      <section class="talk-card convo">
        <div class="presence">
          <div class="presence-avatar" :style="{ width: avatarBox + 'px', height: avatarBox + 'px' }">
            <span v-if="!modeStore.quiet" class="presence-ripple" :style="{ background: character.hue }" />
            <span class="presence-art" v-html="character.art(calm ? 68 : 52, characterStore.act)" />
          </div>
          <div class="presence-text">
            <div class="presence-title">
              <strong :style="{ fontSize: (calm ? 20 : 16) + 'px' }">{{ prefs.assistantName }}</strong>
              <span class="state-pill" :class="stateClass">{{ stateLabel }}</span>
              <button class="char-chip" :style="{ borderColor: character.hue }"
                      title="Change his character in Robot" @click="nav.go('robot')">{{ character.tag }}</button>
            </div>
            <p class="presence-sentence" :style="{ fontSize: (calm ? 15 : 13.5) + 'px' }">{{ stateSentence }}</p>
          </div>
          <span v-if="full && (convo.lastLatency || realtimeCost)" class="turn-meta mono">
            <template v-if="convo.lastLatency">
              llm {{ Math.round(convo.lastLatency.llm_ms) }}ms<br>
              tools {{ Math.round(convo.lastLatency.tool_ms) }}ms<br>
              total {{ Math.round(convo.lastLatency.total_ms) }}ms<br>
            </template>
            <!-- U129: realtime bills audio while talking — show the meter live -->
            <template v-if="realtimeCost">
              <span :title="`${realtimeCost.turns} turns · ${realtimeCost.model}`">
                realtime ~${{ realtimeCost.estimated_usd.toFixed(4) }} ({{ realtimeCost.turns }})
              </span>
            </template>
          </span>
        </div>

        <div ref="scrollEl" role="log" class="log" :style="{ gap: (calm ? 18 : 14) + 'px', padding: calm ? '20px 22px 12px' : '14px 16px 10px' }">
          <template v-for="turn in convo.turns" :key="turn.id">
            <!-- user bubble -->
            <div v-if="turn.role === 'user'" class="turn-user">
              <div class="bubble-user" :style="bubbleSize">{{ turn.text }}</div>
              <time v-if="!calm" class="turn-time mono" :datetime="turn.timestamp" :title="fullTime(turn.timestamp)">{{ shortTime(turn.timestamp) }}</time>
            </div>
            <!-- assistant bubble, preceded by the mark -->
            <div v-else class="bot-row">
              <span class="bot-mark" v-html="character.art(24, 'idle')" />
              <div class="bot-body">
                <div class="bubble-bot" :style="bubbleSize">{{ turn.text }}</div>
                <time v-if="!calm" class="turn-time mono" :datetime="turn.timestamp" :title="fullTime(turn.timestamp)">{{ shortTime(turn.timestamp) }}</time>
                <template v-if="!calm && turn.toolCall">
                  <button
                    class="tool-badge mono" :class="{ open: openTool === turn.id }"
                    title="See exactly what he sent and got back"
                    @click="openTool = openTool === turn.id ? null : turn.id"
                  >
                    {{ turn.toolCall.name }} · {{ turn.toolCall.status }}
                    <span class="tool-chev">{{ openTool === turn.id ? '▾' : '▸' }}</span>
                  </button>
                  <div v-if="openTool === turn.id" class="tool-detail">
                    <div class="tool-detail-head">
                      <span class="mono tool-detail-label">Tool call</span>
                      <span class="mono tool-detail-meta">{{ toolMeta(turn) }}</span>
                      <span class="tool-detail-spacer" />
                      <button class="tool-copy" title="Copy the payloads" @click="copyTool(turn)">Copy</button>
                    </div>
                    <div v-for="p in toolPayloads(turn)" :key="p.label" class="tool-payload">
                      <div class="mono tool-payload-label">{{ p.label }}</div>
                      <pre class="mono tool-payload-body">{{ p.body }}</pre>
                    </div>
                    <div class="tool-detail-foot">Nothing here left this laptop except the call itself.</div>
                  </div>
                </template>
              </div>
            </div>
          </template>

          <!-- Approval, inline in the transcript: names the rule that caused it -->
          <div v-for="a in approvals.pending" :key="a.approvalId" class="bot-row">
            <span class="bot-mark" v-html="character.art(24, 'idle')" />
            <div class="approval-card">
              <div class="approval-head">
                <TriangleAlert :size="14" class="approval-icon" />
                <strong>May I {{ describeAsk(a) }}?</strong>
              </div>
              <p v-if="a.argumentsSummary" class="approval-args">{{ a.argumentsSummary }}</p>
              <p class="approval-rule">
                {{ modeStore.ruleFor(a.toolName).sentence }}
                <button class="rule-link" @click="nav.go('modes')">change this rule</button>
              </p>
              <div class="approval-actions">
                <button class="approve-btn" @click="approvals.grant(a.approvalId)">Allow once</button>
                <button class="d2-ghost-btn" @click="approvals.grant(a.approvalId, true)">Allow and remember</button>
                <button class="deny-btn" @click="approvals.deny(a.approvalId)">Deny</button>
                <span class="approval-count mono">{{ countdown(a) }}</span>
              </div>
            </div>
          </div>

          <p v-if="!convo.turns.length && !approvals.pending.length" class="log-empty">
            Say something — type below{{ calm ? '' : ', or hold Talk' }}.
          </p>
        </div>

        <!-- Identity prompt, only when the camera cannot answer.
             Misattributed memory is worse than no memory. -->
        <div v-if="needsIdentity" class="identity-bar">
          <div class="identity-text">
            <div class="identity-title">{{ identityTitle }}</div>
            <div class="identity-sub">{{ identitySub }}</div>
          </div>
          <div class="identity-choices">
            <button
              v-for="p in peopleChoices" :key="p.id"
              class="identity-choice" :title="p.hint" @click="chooseSpeaker(p.id, p.role)"
            >
              <span class="identity-avatar" :class="{ guest: p.id === 'guest' }">{{ p.initials }}</span>
              {{ p.name }}
            </button>
          </div>
        </div>

        <div class="quick-asks">
          <button
            v-for="q in quickAsks" :key="q.label"
            class="quick-ask" :title="q.hint" @click="convo.submitTurn(q.ask)"
          >{{ q.label }}</button>
          <button v-if="convo.turns.length" class="clear-btn" title="Clear the visible transcript — his memory of the session stays"
                  @click="convo.clearTurns()">Clear</button>
        </div>

        <div class="composer">
          <input
            v-model="convo.pendingText"
            class="composer-input"
            :style="{ padding: calm ? '11px 16px' : '9px 14px', fontSize: (calm ? 15 : 14) + 'px' }"
            :placeholder="calm ? `Say something to ${prefs.assistantName}…` : 'Message · ⏎ to send'"
            aria-label="Message"
            :disabled="convo.isProcessing"
            @keydown.enter.prevent="send"
          >
          <button v-if="!calm" class="round-btn" :title="teachHint" @click="teach">
            <GraduationCap :size="15" />
          </button>
          <button
            class="talk-btn" :class="{ recording }"
            :style="{ height: (calm ? 42 : 38) + 'px' }"
            :title="recording ? 'Recording — click to stop and send' : 'Talk through the laptop microphone'"
            @click="toggleMic"
          >
            <Mic :size="16" />
            {{ recording ? 'Listening…' : calm ? 'Hold to talk' : 'Talk' }}
          </button>
          <button class="send-btn" :disabled="convo.isProcessing || !convo.pendingText.trim()" @click="send">Send</button>
        </div>
        <p v-if="micError" class="mic-error">{{ micError }}</p>
      </section>

      <!-- ═══ Context: never more than three cards, hidden at Calm ═══ -->
      <aside v-if="!calm" class="context" :style="{ width: (full ? 300 : 280) + 'px' }">
        <section class="talk-card cam-card">
          <div class="cam-frame">
            <img v-if="camera.frameSrc.value" :src="camera.frameSrc.value" alt="Robot camera" class="cam-img">
            <div v-else class="cam-placeholder" />
            <span class="cam-tag" :class="{ warn: camTagWarn }">{{ camTag }}</span>
            <div v-if="full && robot.connected" class="cam-controls">
              <button class="cam-btn" title="Look left" @click="aim(-0.4)"><ChevronLeft :size="12" /></button>
              <button class="cam-btn" title="Recentre" @click="aim(0)"><Crosshair :size="12" /></button>
              <button class="cam-btn" title="Look right" @click="aim(0.4)"><ChevronRight :size="12" /></button>
            </div>
          </div>
          <div class="cam-row">
            <button class="d2-mini-toggle" :class="{ on: prefs.voiceMode === 'wake_word' }"
                    title="Mic armed for the wake word" @click="toggleWake">Mic</button>
            <button class="d2-mini-toggle" :class="{ on: robot.tracking }"
                    title="Head follows the person he sees" @click="robot.setTracking(!robot.tracking, BRAIN_URL)">Follow</button>
            <button class="d2-mini-toggle" :class="{ on: asleep }"
                    title="Motors off until woken" @click="toggleSleep">Sleep</button>
            <span class="cam-spacer" />
            <Volume2 :size="14" class="vol-icon" />
            <input v-model.number="volume" type="range" min="0" max="100" aria-label="Volume"
                   class="vol-slider" @change="setVolume">
          </div>
        </section>

        <!-- Mind: what the brain is doing, drawn from the live event stream -->
        <section class="talk-card mind-card">
          <div class="mind-head">
            <h2>Mind</h2>
            <span class="mind-spacer" />
            <span class="mind-pulse" :class="{ quiet: modeStore.quiet }" />
            <span class="mono mind-state">{{ modeStore.quiet ? 'hushed' : mindStatus === waitingLabel ? 'idle' : 'working' }}</span>
          </div>
          <MindCanvas :height="158" @status="mindStatus = $event" />
          <div class="mono mind-event">{{ mindStatus }}</div>
        </section>

        <!-- Next up: today's agenda, straight from the connector -->
        <section class="talk-card agenda-card">
          <div class="mind-head">
            <h2>Next up</h2>
            <span class="mind-spacer" />
            <span class="mono mind-state">{{ agenda.length ? `${agenda.length} today` : '' }}</span>
          </div>
          <div v-for="(a, i) in agenda" :key="i" class="agenda-row">
            <span class="mono agenda-time">{{ a.time }}</span>
            <div class="agenda-text">
              <div class="agenda-title">{{ a.title }}</div>
              <div v-if="a.sub" class="agenda-sub">{{ a.sub }}</div>
            </div>
          </div>
          <p v-if="!agenda.length" class="agenda-empty">{{ agendaNote }}</p>
        </section>

        <!-- Third card is contextual: whatever he is doing right now -->
        <section class="talk-card now-card">
          <div class="mind-head">
            <h2>{{ nowCard.title }}</h2>
            <span class="mind-spacer" />
            <span class="now-tag" :class="nowCard.tagClass">{{ nowCard.tag }}</span>
          </div>
          <div class="now-line1">{{ nowCard.line1 }}</div>
          <div class="now-line2">{{ nowCard.line2 }}</div>
          <button v-if="convo.screenControl" class="d2-danger-btn abort-btn" @click="convo.abortScreenControl()">
            Stop screen control
          </button>
        </section>
      </aside>
    </div>

    <!-- Activity strip: only at Full — the same log the Activity view shows -->
    <div v-if="full" data-activity-strip class="talk-strip">
      <ActivityLog strip />
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  ChevronLeft, ChevronRight, Crosshair, GraduationCap, Mic, TriangleAlert, Volume2,
} from 'lucide-vue-next'
import MindCanvas from '../components/canvas/MindCanvas.vue'
import ActivityLog from '../components/ActivityLog.vue'
import { BRAIN_URL } from '../lib/endpoints'
import { useApprovalStore, type PendingApproval } from '../stores/approvalStore'
import { useCharacterStore } from '../stores/characterStore'
import { useConversationStore, type ConversationTurn } from '../stores/conversationStore'
import { useCameraFeed } from '../composables/useCameraFeed'
import { useEventStore } from '../stores/eventStore'
import { useKnowledgeStore } from '../stores/knowledgeStore'
import { useModeStore } from '../stores/modeStore'
import { useNavStore } from '../stores/navStore'
import { usePrefsStore } from '../stores/prefsStore'
import { useRobotStore } from '../stores/robotStore'

const modeStore = useModeStore()
const prefs = usePrefsStore()
const convo = useConversationStore()
const approvals = useApprovalStore()
const robot = useRobotStore()
const knowledge = useKnowledgeStore()
const nav = useNavStore()
const characterStore = useCharacterStore()
const eventStore = useEventStore()
const camera = useCameraFeed()

const calm = computed(() => prefs.density === 'calm')
const full = computed(() => prefs.density === 'full')
const character = computed(() => characterStore.current)
const avatarBox = computed(() => (calm.value ? 76 : 58))
const bubbleSize = computed(() => ({
  padding: calm.value ? '11px 17px' : '9px 15px',
  fontSize: (calm.value ? 16 : 14.5) + 'px',
}))

// ── Presence ───────────────────────────────────────────────────────────────
const stateLabel = computed(() =>
  modeStore.quiet ? 'hushed' : modeStore.mode === 'present' ? 'on stage' : robot.isSpeaking ? 'speaking' : 'listening')
const stateClass = computed(() =>
  modeStore.quiet ? 'hushed' : modeStore.mode === 'present' ? 'stage' : 'ok')
const stateSentence = computed(() => {
  if (modeStore.quiet) return 'Awake but hushed — he answers when asked and never speaks first.'
  if (modeStore.mode === 'present') return 'On stage. He speaks only on your cues and will not touch mail, files or the desktop.'
  if (!robot.connected) return 'The robot is offline — everything still works here, text only.'
  return prefs.voiceMode === 'wake_word'
    ? `Listening for “${prefs.wakeWord}…”.`
    : 'The wake word is off — use the Talk button, or switch it on in Settings › Voice.'
})

// ── Transcript ─────────────────────────────────────────────────────────────
const scrollEl = ref<HTMLElement | null>(null)
watch(() => convo.turns.length, async () => {
  await nextTick()
  if (scrollEl.value) scrollEl.value.scrollTop = scrollEl.value.scrollHeight
})

const openTool = ref<string | null>(null)

function toolEvents(turn: ConversationTurn) {
  const name = turn.toolCall?.name
  return eventStore.events.filter(e => e.payload.tool_name === name)
}
function toolMeta(turn: ConversationTurn): string {
  const name = turn.toolCall?.name ?? ''
  const rule = modeStore.ruleFor(name)
  const ms = convo.lastLatency ? `${Math.round(convo.lastLatency.tool_ms)}ms · ` : ''
  return `${name} · ${ms}${rule.group ? `${rule.group.state} in ${modeStore.mode}` : 'baseline rule'}`
}
function toolPayloads(turn: ConversationTurn): { label: string; body: string }[] {
  const out: { label: string; body: string }[] = []
  const evts = toolEvents(turn)
  const req = evts.find(e => e.event_type === 'ApprovalRequested')
  if (req?.payload.arguments_summary) {
    out.push({ label: 'Sent', body: String(req.payload.arguments_summary) })
  }
  const done = evts.find(e => e.event_type === 'ToolCallSucceeded')
  if (done?.payload.result_summary) {
    out.push({ label: 'Returned', body: String(done.payload.result_summary) })
  }
  const failed = evts.find(e => e.event_type === 'ToolCallFailed')
  if (failed?.payload.error_code) {
    out.push({ label: 'Failed', body: String(failed.payload.error_code) })
  }
  if (!out.length) out.push({ label: 'Returned', body: '(the result has scrolled out of the event buffer)' })
  return out
}
async function copyTool(turn: ConversationTurn): Promise<void> {
  const text = toolPayloads(turn).map(p => `${p.label}:\n${p.body}`).join('\n\n')
  try { await navigator.clipboard.writeText(text) } catch { /* clipboard blocked */ }
}

// ── Approvals ──────────────────────────────────────────────────────────────
function describeAsk(a: PendingApproval): string {
  const friendly: Record<string, string> = {
    send_mail: 'send this email', post_teams_message: 'post this Teams message',
    run_powershell: 'run this command', write_file: 'write this file',
    use_computer: 'take over the screen', launch_app: 'open this app',
    open_browser_url: 'open this page', save_skill: 'save this skill',
    create_calendar_event: 'add this to your calendar', delete_calendar_event: 'delete this event',
    create_task: 'create this task', delete_task: 'delete this task',
    request_capability: 'be unblocked', git_prepare: 'prepare this commit',
  }
  return friendly[a.toolName] ?? `run ${a.toolName}`
}
const nowTick = ref(Date.now())
let tickTimer: ReturnType<typeof setInterval> | undefined
onMounted(() => { tickTimer = setInterval(() => { nowTick.value = Date.now(); approvals.expireOld() }, 1000) })
onUnmounted(() => clearInterval(tickTimer))

// U129: live realtime spend — that engine bills audio while talking, so the
// meter polls while the view is open and shows only when realtime is active.
const realtimeCost = ref<{ engine: string; model: string; turns: number; estimated_usd: number } | null>(null)
let costTimer: ReturnType<typeof setInterval> | undefined
async function fetchRealtimeCost(): Promise<void> {
  try {
    const r = await fetch(`${BRAIN_URL}/voice/realtime-cost`)
    const body = r.ok ? await r.json() : null
    realtimeCost.value = body?.engine === 'realtime' ? body : null
  } catch { realtimeCost.value = null }
}
onMounted(() => { fetchRealtimeCost(); costTimer = setInterval(fetchRealtimeCost, 10_000) })
onUnmounted(() => clearInterval(costTimer))
function countdown(a: PendingApproval): string {
  const left = Math.max(0, Math.round((new Date(a.timeoutAt).getTime() - nowTick.value) / 1000))
  return `${left}s`
}

// ── Identity ───────────────────────────────────────────────────────────────
const needsIdentity = computed(() => knowledge.speaker === null && knowledge.people.length > 0)
const unknownFace = computed(() => robot.lastRecognized !== null && !robot.lastRecognized.known)
const identityTitle = computed(() => unknownFace.value ? 'Who is this?' : 'Who is typing?')
const identitySub = computed(() => unknownFace.value
  ? 'He sees a face he does not recognise. Until you say, he answers generically and saves nothing.'
  : 'No one is in view. Pick a person to use their memory — or stay a guest.')
const peopleChoices = computed(() => [
  ...knowledge.people.map(p => ({
    id: p.person_id, name: p.display_name, role: p.role,
    initials: p.display_name.slice(0, 2).toUpperCase(),
    hint: `Answer as ${p.display_name}`,
  })),
  { id: 'guest', name: 'Guest', role: 'guest', initials: 'G', hint: 'Answer generically — nothing is written to memory' },
])
function chooseSpeaker(id: string, role: string): void {
  knowledge.setSpeaker(id, 'manual')
  prefs.followPerson(role)
}

// ── Quick asks ─────────────────────────────────────────────────────────────
const quickAsks = computed(() => calm.value
  ? [
    { label: 'Brief me', ask: 'Give me my briefing', hint: 'The morning briefing, out loud' },
    { label: 'Play music', ask: 'Play some music', hint: 'Resume what was last playing' },
  ]
  : [
    { label: 'Brief me', ask: 'Give me my briefing', hint: 'Weather, calendar, top mail and todos' },
    { label: 'What did I miss?', ask: 'What did I miss while I was away?', hint: 'Mail and Teams since you left' },
    { label: 'Today’s agenda', ask: 'What is on my calendar today?', hint: 'Your meetings, with what needs attention' },
  ])

// ── Composer ───────────────────────────────────────────────────────────────
function send(): void {
  const text = convo.pendingText.trim()
  if (text) convo.submitTurn(text)
}
// U256: when a turn happened. Time only for today — the date on every line is
// noise in a conversation you are having right now — and a date as soon as it
// is older, because "14:32" on yesterday's message is worse than no time.
function shortTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const hhmm = d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
  const today = new Date()
  const sameDay = d.getFullYear() === today.getFullYear()
    && d.getMonth() === today.getMonth() && d.getDate() === today.getDate()
  if (sameDay) return hhmm
  return `${d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })} ${hhmm}`
}
function fullTime(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleString()
}

const teachHint = 'Teach — turn this message into a lesson you approve'
function teach(): void {
  const text = convo.pendingText.trim()
  if (!text) return
  convo.pendingText = ''
  convo.teach(text)
}

// Laptop mic (U36e): record, send to /voice/turn, replies arrive as events.
const recording = ref(false)
const micError = ref('')
let recorder: MediaRecorder | null = null
let chunks: Blob[] = []
async function toggleMic(): Promise<void> {
  if (recording.value) { recorder?.stop(); return }
  micError.value = ''
  if (!navigator.mediaDevices?.getUserMedia) {
    micError.value = 'No microphone API available in this window.'
    return
  }
  let stream: MediaStream
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  } catch (err: unknown) {
    micError.value = (err as { name?: string })?.name === 'NotAllowedError'
      ? 'Microphone permission denied — allow it in your OS settings.'
      : 'No microphone found — is one connected?'
    return
  }
  try {
    chunks = []
    recorder = new MediaRecorder(stream)
    recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data) }
    recorder.onstop = async () => {
      stream.getTracks().forEach(t => t.stop())
      recording.value = false
      const blob = new Blob(chunks, { type: recorder?.mimeType || 'audio/webm' })
      if (blob.size < 400) { micError.value = 'That was too short — hold the mic while you speak.'; return }
      const form = new FormData()
      form.append('audio', blob, 'audio.webm')
      try {
        const resp = await fetch(`${BRAIN_URL}/voice/turn`, { method: 'POST', body: form })
        if (!resp.ok) {
          const body = await resp.json().catch(() => ({}))
          micError.value = body.error ?? `Voice turn failed (${resp.status})`
        }
      } catch { micError.value = 'Could not reach the brain.' }
    }
    recorder.start()
    recording.value = true
  } catch {
    stream.getTracks().forEach(t => t.stop())
    micError.value = 'Recording is not supported in this window.'
  }
}

// ── Context cards ──────────────────────────────────────────────────────────
const camTag = computed(() => {
  const r = robot.lastRecognized
  if (!robot.connected) return 'robot offline'
  if (r?.known && r.display_name) return `${r.display_name} · ${Math.round(r.confidence * 100)}%`
  if (r && !r.known) return 'unknown face'
  return 'no one in view'
})
const camTagWarn = computed(() => {
  const r = robot.lastRecognized
  return !!r && !r.known
})
async function aim(direction: number): Promise<void> {
  try {
    await fetch(`${BRAIN_URL}/robot/aim`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(direction === 0 ? { recenter: true } : { yaw: direction }),
    })
  } catch { /* robot offline */ }
}
function toggleWake(): void {
  prefs.save({ voice_mode: prefs.voiceMode === 'wake_word' ? 'off' : 'wake_word' })
}
const asleep = ref(false)
async function toggleSleep(): Promise<void> {
  const target = !asleep.value
  try {
    const resp = await fetch(`${BRAIN_URL}/robot/${target ? 'sleep' : 'wake'}`, { method: 'POST' })
    if (resp.ok) asleep.value = target
  } catch { /* robot offline */ }
}
const volume = ref(80)
async function setVolume(): Promise<void> {
  try {
    await fetch(`${BRAIN_URL}/robot/volume`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ volume: volume.value / 100 }),
    })
  } catch { /* robot offline */ }
}

const waitingLabel = 'Waiting for something to happen'
const mindStatus = ref(waitingLabel)

// Agenda: today's calendar through the connector. An empty answer is shown as
// what it is — not silently hidden.
const agenda = ref<{ time: string; title: string; sub: string }[]>([])
const agendaNote = ref('Loading…')
async function fetchAgenda(): Promise<void> {
  try {
    const r = await fetch(`${BRAIN_URL}/connector/calendar/today`)
    if (!r.ok) { agendaNote.value = 'Calendar unavailable — connect it in Settings › Connections.'; return }
    const data = await r.json()
    const text: string = data.result ?? ''
    // The connector answers in prose lines ("09:30 Standup …"); parse what fits.
    const rows = text.split('\n').map(l => l.trim()).filter(Boolean)
      .map(l => {
        const m = l.match(/^[-•]?\s*(\d{1,2}:\d{2})\s*[–-]?\s*(.+)$/)
        return m ? { time: m[1], title: m[2], sub: '' } : null
      })
      .filter((x): x is { time: string; title: string; sub: string } => !!x)
    agenda.value = rows.slice(0, 4)
    agendaNote.value = rows.length ? '' : (text.slice(0, 90) || 'Nothing on the calendar today.')
  } catch { agendaNote.value = 'Calendar unavailable.' }
}
let agendaTimer: ReturnType<typeof setInterval> | undefined
onMounted(() => { fetchAgenda(); agendaTimer = setInterval(fetchAgenda, 120_000) })
onUnmounted(() => clearInterval(agendaTimer))

// The contextual "now" card: derived from what he is actually doing.
const nowCard = computed(() => {
  if (convo.screenControl) {
    return { title: 'Screen control', tag: 'live', tagClass: 'warn', line1: 'He is driving the desktop', line2: 'Watch the screen — stop below if it goes wrong' }
  }
  if (convo.agentRound) {
    return { title: 'Working', tag: `round ${convo.agentRound.round}/${convo.agentRound.max}`, tagClass: 'info', line1: convo.agentRound.tools.join(', ') || 'thinking…', line2: 'The agentic loop is running' }
  }
  if (robot.isSpeaking) {
    return { title: 'Speaking', tag: 'live', tagClass: 'ok', line1: robot.currentTranscript || '…', line2: 'Cut him off with Stop, top right' }
  }
  const lastMotion = robot.motionLog[0]
  if (lastMotion) {
    return { title: 'Body', tag: lastMotion.status, tagClass: lastMotion.status === 'failed' ? 'warn' : 'ok', line1: lastMotion.name, line2: `last motion · ${new Date(lastMotion.timestamp).toLocaleTimeString()}` }
  }
  return { title: 'Idle', tag: robot.connected ? 'ready' : 'offline', tagClass: robot.connected ? 'ok' : 'warn', line1: robot.connected ? 'Nothing running' : 'Robot offline', line2: robot.connected ? 'He is watching and listening' : 'Text conversation still works' }
})
</script>

<style scoped>
.talk { flex: 1; min-width: 0; display: flex; flex-direction: column; min-height: 0; }
.talk-cols { flex: 1 1 auto; min-height: 0; display: flex; gap: 12px; padding: 12px; }
.talk-card { background: var(--surface); border: 1px solid var(--line); border-radius: 14px; }
.mono { font-family: var(--font-mono); }

.convo { flex: 1; min-width: 280px; min-height: 0; overflow: hidden; display: flex; flex-direction: column; }

.presence {
  display: flex; align-items: center; gap: 12px; padding: 12px 16px 10px;
  border-bottom: 1px solid var(--line); flex-shrink: 0;
}
.presence-avatar { position: relative; flex-shrink: 0; display: flex; align-items: center; justify-content: center; }
.presence-ripple { position: absolute; inset: 0; border-radius: 50%; animation: ripple 3.4s ease-out infinite; }
.presence-art { position: relative; display: flex; }
.presence-text { flex: 1; min-width: 0; }
.presence-title { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.presence-title strong { font-weight: 700; letter-spacing: -0.01em; }
.state-pill {
  font-size: 11px; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase;
  padding: 2px 10px; border-radius: 999px;
}
.state-pill.ok { background: var(--ok-wash); color: var(--ok); }
.state-pill.stage { background: var(--present-wash); color: var(--present); }
.state-pill.hushed { background: var(--sunken); color: var(--ink-3); }
.char-chip {
  display: inline-flex; align-items: center; gap: 6px; font-size: 10.5px; font-weight: 700;
  letter-spacing: 0.04em; text-transform: uppercase; padding: 2px 10px; border-radius: 999px;
  background: var(--surface-2); border: 1px solid var(--line-strong); color: var(--ink-2);
  cursor: pointer; font-family: inherit;
}
.presence-sentence { margin: 3px 0 0; color: var(--ink-2); max-width: 72ch; }
.turn-meta { font-size: 10.5px; color: var(--ink-3); flex-shrink: 0; text-align: right; line-height: 1.5; }

.log { flex: 1 1 auto; min-height: 100px; overflow-y: auto; display: flex; flex-direction: column; }
.log-empty { font-size: 13px; color: var(--ink-3); }
.turn-user { display: flex; flex-direction: column; align-items: flex-end; gap: 3px; }
.turn-time {
  font-size: 10px; color: var(--ink-3); letter-spacing: 0.02em;
  font-variant-numeric: tabular-nums;
}
.bot-body .turn-time { display: block; margin-top: 3px; }
.bubble-user {
  align-self: flex-end; max-width: 78%;
  background: var(--accent); color: var(--on-accent);
  border-radius: 16px 16px 5px 16px; line-height: 1.45; white-space: pre-wrap;
}
.bot-row { align-self: flex-start; max-width: 84%; display: flex; gap: 9px; }
.bot-mark { display: flex; flex-shrink: 0; margin-top: 3px; }
.bot-body { min-width: 0; }
.bubble-bot {
  background: var(--surface-2); border: 1px solid var(--line);
  border-radius: 5px 16px 16px 16px; line-height: 1.45; white-space: pre-wrap;
}

.tool-badge {
  margin-top: 5px; display: inline-flex; align-items: center; gap: 5px;
  font-size: 10.5px; color: var(--ok); background: var(--ok-wash);
  border: 1px solid transparent; border-radius: 5px; padding: 2px 8px;
  cursor: pointer; font-family: var(--font-mono);
}
.tool-badge.open { border-color: var(--ok); }
.tool-chev { opacity: 0.7; }
.tool-detail {
  margin-top: 6px; border: 1px solid var(--line); border-radius: 10px;
  background: var(--sunken); overflow: hidden; max-width: 520px;
}
.tool-detail-head { display: flex; align-items: center; gap: 9px; padding: 7px 12px; border-bottom: 1px solid var(--line); }
.tool-detail-label {
  font-size: 10.5px; font-weight: 700; letter-spacing: 0.08em;
  text-transform: uppercase; color: var(--ink-3);
}
.tool-detail-meta { font-size: 10.5px; color: var(--ink-3); }
.tool-detail-spacer { flex: 1; }
.tool-copy { background: none; border: none; color: var(--ink-3); cursor: pointer; padding: 0; font-size: 11px; font-family: inherit; }
.tool-copy:hover { color: var(--accent); }
.tool-payload { padding: 9px 12px; border-bottom: 1px solid var(--line); }
.tool-payload-label {
  font-size: 10px; font-weight: 700; letter-spacing: 0.08em;
  text-transform: uppercase; color: var(--ink-3); margin-bottom: 4px;
}
.tool-payload-body { margin: 0; font-size: 11px; line-height: 1.55; color: var(--ink-2); white-space: pre-wrap; word-break: break-word; }
.tool-detail-foot { padding: 7px 12px; font-size: 11.5px; color: var(--ink-3); }

.approval-card {
  background: var(--warn-wash); border: 1.5px solid var(--warn);
  border-radius: 5px 16px 16px 16px; padding: 12px 16px; min-width: 0;
}
.approval-head { display: flex; align-items: center; gap: 7px; margin-bottom: 5px; font-size: 13.5px; }
.approval-icon { color: var(--warn); }
.approval-args { margin: 0 0 9px; font-size: 14px; line-height: 1.45; color: var(--ink-2); word-break: break-word; }
.approval-rule { margin: 0 0 10px; font-size: 12.5px; color: var(--ink-3); }
.rule-link {
  background: none; border: none; padding: 0; color: var(--accent);
  font-family: inherit; font-size: 12.5px; font-weight: 600; cursor: pointer; text-decoration: underline;
}
.approval-actions { display: flex; gap: 7px; flex-wrap: wrap; align-items: center; }
.approve-btn {
  padding: 7px 15px; border-radius: 9px; background: var(--ok); color: #fff;
  border: none; font-size: 13px; font-weight: 700; cursor: pointer; font-family: inherit;
}
.deny-btn {
  padding: 7px 15px; border-radius: 9px; background: transparent; color: var(--ink-2);
  border: 1.5px solid var(--line-strong); font-size: 13px; font-weight: 700;
  cursor: pointer; font-family: inherit;
}
.deny-btn:hover { border-color: var(--danger); color: var(--danger); }
.approval-count { font-size: 11px; color: var(--warn); }

.identity-bar {
  display: flex; align-items: center; gap: 11px; flex-wrap: wrap;
  margin: 0 16px 10px; padding: 11px 14px;
  border: 1.5px solid var(--warn); border-radius: 12px; background: var(--warn-wash);
}
.identity-text { flex: 1; min-width: 170px; }
.identity-title { font-size: 13px; font-weight: 700; }
.identity-sub { font-size: 12px; color: var(--ink-2); margin-top: 2px; }
.identity-choices { display: flex; gap: 6px; flex-wrap: wrap; }
.identity-choice {
  display: inline-flex; align-items: center; gap: 6px; padding: 5px 12px 5px 5px;
  border-radius: 999px; background: var(--surface); border: 1.5px solid var(--line-strong);
  color: var(--ink); font-size: 12.5px; font-weight: 600; cursor: pointer; font-family: inherit;
}
.identity-avatar {
  width: 22px; height: 22px; border-radius: 50%; flex-shrink: 0;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 9.5px; font-weight: 700; background: var(--accent); color: var(--on-accent);
}
.identity-avatar.guest { background: var(--sunken); color: var(--ink-3); }

.quick-asks { display: flex; gap: 6px; flex-wrap: wrap; padding: 0 16px 9px; }
.quick-ask {
  padding: 5px 12px; border-radius: 999px; background: var(--accent-wash);
  border: 1px solid var(--accent); color: var(--accent);
  font-size: 12px; font-weight: 600; cursor: pointer; font-family: inherit;
}
.clear-btn {
  margin-left: auto; padding: 5px 12px; border-radius: 999px; background: transparent;
  border: 1px solid var(--line); color: var(--ink-3);
  font-size: 12px; cursor: pointer; font-family: inherit;
}

.composer {
  display: flex; gap: 8px; align-items: center; padding: 11px 16px 14px;
  border-top: 1px solid var(--line); flex-shrink: 0;
}
.composer-input {
  flex: 1; min-width: 0; background: var(--surface-2);
  border: 1.5px solid var(--line); border-radius: 999px;
  color: var(--ink); outline: none; font-family: inherit;
}
.composer-input:focus { border-color: var(--accent); }
.round-btn {
  display: inline-flex; align-items: center; justify-content: center;
  width: 38px; height: 38px; border-radius: 50%;
  background: var(--surface-2); border: 1.5px solid var(--line);
  color: var(--ink-2); cursor: pointer; flex-shrink: 0;
}
.talk-btn {
  display: inline-flex; align-items: center; gap: 7px; padding: 0 16px;
  border-radius: 999px; background: var(--accent); color: var(--on-accent);
  border: none; font-size: 13.5px; font-weight: 700; cursor: pointer;
  font-family: inherit; flex-shrink: 0;
}
.talk-btn.recording { background: var(--danger); animation: pulse 1.4s ease-in-out infinite; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }
.send-btn {
  padding: 0 16px; height: 38px; border-radius: 999px; background: var(--surface-2);
  border: 1.5px solid var(--line-strong); color: var(--ink);
  font-size: 13px; font-weight: 700; cursor: pointer; font-family: inherit; flex-shrink: 0;
}
.send-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.mic-error { margin: 0 16px 10px; font-size: 12px; color: var(--danger); }

.context { flex-shrink: 0; display: flex; flex-direction: column; gap: 12px; min-height: 0; overflow-y: auto; }
.cam-card { overflow: hidden; flex-shrink: 0; }
.cam-frame { position: relative; aspect-ratio: 16 / 10; background: linear-gradient(160deg, #2b3a30 0%, #1a231d 58%, #121a15 100%); }
.cam-img { width: 100%; height: 100%; object-fit: cover; display: block; }
.cam-placeholder { position: absolute; inset: 0; }
.cam-tag {
  position: absolute; left: 9px; bottom: 9px; display: inline-flex; align-items: center; gap: 6px;
  color: #fff; font-size: 11.5px; padding: 3px 10px; border-radius: 999px;
  background: rgba(8, 16, 11, 0.5);
}
.cam-tag.warn { background: var(--warn); }
.cam-controls { position: absolute; right: 8px; bottom: 8px; display: flex; gap: 4px; }
.cam-btn {
  display: inline-flex; align-items: center; justify-content: center;
  width: 24px; height: 24px; border-radius: 6px;
  background: rgba(8, 16, 11, 0.5); border: 1px solid rgba(255, 255, 255, 0.25);
  color: #fff; cursor: pointer;
}
.cam-row { padding: 11px 14px; display: flex; align-items: center; gap: 8px; }
.cam-spacer { flex: 1; }
.vol-icon { color: var(--ink-3); flex-shrink: 0; }
.vol-slider { flex: 1 1 auto; min-width: 40px; accent-color: var(--accent); }

.mind-card, .agenda-card, .now-card { padding: 13px 15px; flex-shrink: 0; }
.mind-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.mind-head h2 { margin: 0; font-size: 13px; font-weight: 700; }
.mind-spacer { flex: 1; }
.mind-pulse { width: 7px; height: 7px; border-radius: 50%; background: var(--accent); animation: ripple 1.6s ease-out infinite; }
.mind-pulse.quiet { background: var(--ink-3); animation: none; }
.mind-state { font-size: 10.5px; color: var(--ink-3); }
.mind-event {
  font-size: 10.5px; color: var(--ink-3); margin-top: 6px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

.agenda-row { display: flex; align-items: flex-start; gap: 9px; padding: 6px 0; border-bottom: 1px solid var(--line); }
.agenda-time { font-size: 11.5px; color: var(--ink-3); width: 36px; flex-shrink: 0; padding-top: 1px; }
.agenda-text { flex: 1; min-width: 0; line-height: 1.3; }
.agenda-title { font-size: 13px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.agenda-sub { font-size: 11.5px; color: var(--ink-3); }
.agenda-empty { font-size: 12px; color: var(--ink-3); margin: 0; }

.now-tag {
  display: inline-flex; align-items: center; font-size: 10.5px; font-weight: 700;
  border-radius: 999px; padding: 2px 8px;
}
.now-tag.ok { color: var(--ok); background: var(--ok-wash); }
.now-tag.warn { color: var(--warn); background: var(--warn-wash); }
.now-tag.info { color: var(--info); background: var(--info-wash); }
.now-line1 { font-size: 13.5px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.now-line2 { font-size: 11.5px; color: var(--ink-3); }
.abort-btn { margin-top: 9px; }

.talk-strip {
  flex: 0 1 150px; min-height: 0; overflow: hidden;
  border-top: 1px solid var(--line); background: var(--surface);
  display: flex; flex-direction: column;
}
/* Short windows: the log strip is the first thing to go — the conversation is not. */
@media (max-height: 700px) { [data-activity-strip] { display: none !important; } }
</style>
