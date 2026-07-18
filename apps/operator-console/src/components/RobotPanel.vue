<template>
  <section class="panel">
    <h2 class="panel-title">Robot State</h2>

    <!-- U114: one compact status strip — badge only when something is wrong -->
    <div class="status-strip">
      <span :class="['strip-dot', robotStore.statusBadgeClass]" :title="`Mode: ${robotStore.mode}`" />
      <span class="strip-text">{{ robotStore.behaviorState }}</span>
      <span :class="['indicator', robotStore.isSpeaking ? 'indicator-active' : 'indicator-idle']">
        <Volume2 v-if="robotStore.isSpeaking" :size="13" />
        <VolumeX v-else :size="13" />
      </span>
      <span v-if="robotStore.lastRecognized" class="strip-text strip-text--faint" :title="robotStore.lastRecognized.known ? `${Math.round(robotStore.lastRecognized.confidence * 100)}% confident` : 'Unknown face'">
        <Eye :size="12" /> {{ robotStore.lastRecognized.known ? robotStore.lastRecognized.display_name : 'unknown' }}
      </span>
    </div>
    <div v-if="robotStore.isSpeaking && robotStore.currentTranscript" class="transcript-box">
      {{ robotStore.currentTranscript }}
    </div>

    <!-- U125: labelled toggle tiles — even 4-up grid, self-explanatory -->
    <div class="toggle-grid">
      <button :class="['toggle-cell', !asleep && 'toggle-cell--on']"
              :title="asleep ? 'Asleep — click to wake up' : 'Awake — click for sleep mode (take no action)'"
              @click="toggleSleep">
        <Moon v-if="asleep" :size="16" /><Power v-else :size="16" />
        <span class="toggle-lbl">{{ asleep ? 'Asleep' : 'Awake' }}</span>
      </button>
      <button :class="['toggle-cell', micOn && 'toggle-cell--on']"
              :title="micOn ? 'Listening for “Richie …” — click to stop' : 'Microphone off — click to listen'"
              @click="toggleMicListening">
        <Mic v-if="micOn" :size="16" /><MicOff v-else :size="16" />
        <span class="toggle-lbl">Mic</span>
      </button>
      <button :class="['toggle-cell', tracking && 'toggle-cell--on']"
              :title="tracking ? 'Following faces — click to stop' : 'Click to follow the nearest face'"
              @click="toggleTracking">
        <Eye :size="16" />
        <span class="toggle-lbl">Follow</span>
      </button>
      <button :class="['toggle-cell', proactiveOn && 'toggle-cell--on']"
              :title="proactiveOn ? 'Proactive: speaks up for reminders & daily briefing' : 'Proactive off — only speaks when addressed'"
              @click="toggleProactive">
        <Bell :size="16" />
        <span class="toggle-lbl">Notify</span>
      </button>
    </div>
    <!-- U125: briefing time gets its own labelled row instead of crowding the toggles -->
    <div v-if="proactiveOn" class="briefing-row">
      <Bell :size="13" /> <span>Daily briefing at</span>
      <input v-model="briefingTime" type="time" class="briefing-input" aria-label="Daily briefing time" @change="saveBriefingTime" />
    </div>

    <div class="ctl-row">
      <span class="ctl-label">
        <VolumeX v-if="volume === 0" :size="14" />
        <Volume1 v-else-if="volume < 0.5" :size="14" />
        <Volume2 v-else :size="14" />
        Volume
      </span>
      <input
        v-model.number="volume"
        type="range" min="0" max="1" step="0.05"
        class="volume-slider"
        @change="applyVolume"
      />
      <span class="volume-pct">{{ Math.round(volume * 100) }}%</span>
    </div>

    <!-- U85/U125: character persona — label on its own line, full-width select -->
    <div class="persona-block">
      <span class="ctl-label"><Bot :size="14" /> Persona</span>
      <div class="persona-row">
        <select v-model="activeCharacter" class="persona-select" @change="applyCharacter">
          <option value="">Default (no character)</option>
          <option v-for="c in characters" :key="c.id" :value="c.id">{{ c.display_name }}</option>
        </select>
        <button class="persona-edit" :disabled="!activeCharacter" title="Edit this persona" @click="editingPersona = !editingPersona">
          <Pencil :size="13" />
        </button>
      </div>
    </div>
    <div v-if="editingPersona && currentCharacter" class="persona-editor">
      <label class="pe-label">Character</label>
      <textarea v-model="currentCharacter.character_prompt" rows="2" class="pe-input" />
      <div class="pe-row">
        <label class="pe-label">Verbosity
          <select v-model="currentCharacter.verbosity" class="pe-mini">
            <option>brief</option><option>normal</option><option>detailed</option>
          </select>
        </label>
        <label class="pe-label">Humor
          <select v-model="currentCharacter.humor_level" class="pe-mini">
            <option>none</option><option>low</option><option>medium</option><option>high</option>
          </select>
        </label>
      </div>
      <div class="pe-row">
        <label class="pe-label">Voice
          <select v-model="currentCharacter.voice_id" class="pe-mini">
            <option v-for="v in VOICES" :key="v" :value="v">{{ v }}</option>
          </select>
        </label>
        <label class="pe-label">Interrupt
          <select v-model="currentCharacter.interruptibility" class="pe-mini">
            <option value="wake_word">wake word</option><option value="vad">any voice</option><option value="off">off</option>
          </select>
        </label>
      </div>
      <label class="pe-label">Learned traits (how it has grown)</label>
      <textarea v-model="currentCharacter.learned_traits" rows="2" class="pe-input"
                placeholder="e.g. remembers Jan likes skate punk; keeps mornings extra upbeat" />
      <div class="pe-actions">
        <button class="pe-save" :disabled="savingPersona" @click="savePersona">
          {{ savingPersona ? 'Saving…' : 'Save persona' }}
        </button>
        <span v-if="personaSaved" class="pe-ok">Saved</span>
      </div>
      <p class="pe-hint">Tip: while talking, use the 🎓 button — the assistant proposes new traits you can add here.</p>
    </div>

    <!-- U114: all 12 action buttons live in ONE collapsible section so the
         camera below stays above the fold. -->
    <div class="mt-3">
      <button class="section-toggle" :aria-expanded="actionsOpen" @click="actionsOpen = !actionsOpen">
        <ChevronRight :size="13" :class="['chev', actionsOpen && 'chev--open']" /> Actions
      </button>
      <template v-if="actionsOpen">
      <div class="qa-grid">
        <button class="qa-btn" :disabled="acting" title="Wake up (enables motors after sleep)" @click="act('wake_up')">
          <Power :size="13" /> Wake up
        </button>
        <button class="qa-btn" :disabled="acting" title="Go to sleep" @click="act('sleep')">
          <Moon :size="13" /> Sleep
        </button>
        <button class="qa-btn" :disabled="acting" title="Wave the antennas" @click="act('wave')">
          <Hand :size="13" /> Wave
        </button>
        <button class="qa-btn" :disabled="acting" title="Nod the head" @click="act('nod')">
          <MoveVertical :size="13" /> Nod
        </button>
        <button class="qa-btn" :disabled="acting" title="Lively gesture" @click="act('gesture')">
          <Sparkles :size="13" /> Gesture
        </button>
        <button class="qa-btn" :disabled="acting" title="Take a bow" @click="act('bow')">
          <ChevronsDown :size="13" /> Bow
        </button>
        <button class="qa-btn" :disabled="acting" title="Glance around the room" @click="act('look_around')">
          <Eye :size="13" /> Look around
        </button>
        <button class="qa-btn" :disabled="acting" title="Shake head" @click="act('shake')">
          <MoveHorizontal :size="13" /> Shake
        </button>
      </div>

      <h3 class="section-label mt-3">Speak &amp; Move</h3>
      <div class="qa-grid">
        <button class="qa-btn" :disabled="acting" title="Wave + say hi" @click="perform('hi')">
          <Hand :size="13" /> Say hi
        </button>
        <button class="qa-btn" :disabled="acting" title="Bow + introduce itself" @click="perform('intro')">
          <Bot :size="13" /> Introduce
        </button>
        <button class="qa-btn" :disabled="acting" title="Gesture + tell a joke" @click="perform('joke')">
          <Laugh :size="13" /> Joke
        </button>
        <button class="qa-btn" :disabled="acting" title="Nod + compliment" @click="perform('compliment')">
          <ThumbsUp :size="13" /> Compliment
        </button>
      </div>
      </template>
      <p v-if="actError" class="qa-error">{{ actError }}</p>
    </div>

    <!-- U114: motion log collapsed by default — a debug surface, not a headline -->
    <div class="mt-3 motion-section">
      <button class="section-toggle" :aria-expanded="motionOpen" @click="motionOpen = !motionOpen">
        <ChevronRight :size="13" :class="['chev', motionOpen && 'chev--open']" />
        Motion log<span v-if="robotStore.motionLog.length" class="section-count">{{ robotStore.motionLog.length }}</span>
      </button>
      <ul v-if="motionOpen" class="motion-log-scroll">
        <li v-for="entry in robotStore.motionLog" :key="entry.id" class="motion-row">
          <span :class="['motion-dot', `mdot-${entry.status}`]" />
          <span class="motion-row-name">{{ entry.name }}</span>
          <span class="motion-row-time">{{ fmtTime(entry.timestamp) }}</span>
        </li>
        <li v-if="robotStore.motionLog.length === 0" class="motion-empty">No motions yet</li>
      </ul>
    </div>

    <!-- U117: app logs moved here from Settings — same collapsed treatment -->
    <div class="mt-3 motion-section">
      <button class="section-toggle" :aria-expanded="logsOpen" @click="toggleLogs">
        <ChevronRight :size="13" :class="['chev', logsOpen && 'chev--open']" /> App logs
      </button>
      <template v-if="logsOpen">
        <div class="logs-bar">
          <select v-model="logLevel" class="briefing-input" aria-label="Filter log level" @change="fetchAppLogs">
            <option value="">All</option><option value="INFO">Info</option>
            <option value="WARNING">Warning</option><option value="ERROR">Error</option>
          </select>
          <button class="qa-btn qa-btn--slim" :disabled="logsLoading" @click="fetchAppLogs">
            <RefreshCw :size="12" :class="logsLoading ? 'spin' : ''" /> Refresh
          </button>
        </div>
        <ul class="motion-log-scroll app-log-scroll" role="log">
          <li v-for="(r, i) in logRecords" :key="i" :class="['app-log-row', `app-log--${r.level.toLowerCase()}`]" :title="r.message">
            <span class="app-log-level">{{ r.level[0] }}</span>
            <span class="app-log-msg">{{ r.message }}</span>
          </li>
          <li v-if="!logRecords.length" class="motion-empty">No log records</li>
        </ul>
      </template>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  Bell, Bot, ChevronRight, ChevronsDown, Eye, Hand, Laugh, Moon, MoveHorizontal, MoveVertical,
  Mic, MicOff, Pencil, Power, RefreshCw, Sparkles, ThumbsUp, Volume1, Volume2, VolumeX,
} from 'lucide-vue-next'
import { useRobotStore } from '../stores/robotStore'

const BRAIN_URL = import.meta.env.VITE_BRAIN_URL ?? import.meta.env.VITE_ORCHESTRATOR_URL ?? 'http://localhost:8000'

const robotStore = useRobotStore()
const acting = ref(false)
const actError = ref('')
const volume = ref(0.8)
// U114: collapse the button farm + motion log so the camera stays in view.
const actionsOpen = ref(false)
const motionOpen = ref(false)

// U117: app logs (moved here from Settings) — local ring buffer.
const logsOpen = ref(false)
const logsLoading = ref(false)
const logLevel = ref('')
const logRecords = ref<{ ts: string; level: string; message: string }[]>([])
async function fetchAppLogs(): Promise<void> {
  logsLoading.value = true
  try {
    const resp = await fetch(`${BRAIN_URL}/logs/recent?limit=100&level=${logLevel.value}`)
    logRecords.value = ((await resp.json()).records ?? []).reverse() // newest first
  } catch { logRecords.value = [] } finally { logsLoading.value = false }
}
async function toggleLogs(): Promise<void> {
  logsOpen.value = !logsOpen.value
  if (logsOpen.value) await fetchAppLogs()
}

const tracking = ref(true) // adapter enables head tracking on connect

// U99: microphone (wake-word listening) on/off — sets VOICE_MODE via prefs.
const micOn = ref(true)
const asleep = ref(false)

// U110: proactive speech (reminders + daily briefing).
const proactiveOn = ref(true)
const briefingTime = ref('')
async function fetchProactive() {
  try {
    const r = await fetch(`${BRAIN_URL}/robot/proactive`)
    const j = await r.json()
    proactiveOn.value = j.enabled === true
    briefingTime.value = j.briefing_time ?? ''
  } catch {}
}
async function toggleProactive() {
  proactiveOn.value = !proactiveOn.value
  try {
    await fetch(`${BRAIN_URL}/robot/proactive`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: proactiveOn.value }),
    })
  } catch { proactiveOn.value = !proactiveOn.value }
}
async function saveBriefingTime() {
  try {
    await fetch(`${BRAIN_URL}/robot/proactive`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ briefing_time: briefingTime.value }),
    })
  } catch {}
}
async function fetchSleep() {
  try { const r = await fetch(`${BRAIN_URL}/robot/sleep`); asleep.value = (await r.json()).asleep === true } catch {}
}
async function toggleSleep() {
  const to = !asleep.value
  asleep.value = to
  try {
    await fetch(`${BRAIN_URL}/robot/${to ? 'sleep' : 'wake'}`, { method: 'POST' })
    micOn.value = !to  // sleep turns the mic off; wake turns it on
  } catch { asleep.value = !to }
}
async function fetchMic() {
  try {
    const r = await fetch(`${BRAIN_URL}/setup/prefs`)
    micOn.value = ((await r.json()).voice_mode ?? 'off') === 'wake_word'
  } catch { /* keep */ }
}
async function toggleMicListening() {
  micOn.value = !micOn.value
  try {
    await fetch(`${BRAIN_URL}/setup/prefs`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ voice_mode: micOn.value ? 'wake_word' : 'off' }),
    })
  } catch { micOn.value = !micOn.value } // revert on failure
}

// U85: character persona selection + editing + growth
interface Character { id: string; display_name: string; character_prompt: string
  verbosity: string; humor_level: string; voice_id: string
  interruptibility: string; learned_traits: string }
const VOICES = ['', 'alloy', 'ash', 'ballad', 'coral', 'echo', 'fable', 'onyx', 'nova', 'sage', 'shimmer', 'verse']
const characters = ref<Character[]>([])
const activeCharacter = ref('')
const editingPersona = ref(false)
const savingPersona = ref(false)
const personaSaved = ref(false)
const currentCharacter = ref<Character | null>(null)

async function fetchCharacters() {
  try {
    const r = await fetch(`${BRAIN_URL}/setup/characters`)
    const data = await r.json()
    characters.value = data.characters ?? []
    activeCharacter.value = data.active ?? ''
    syncCurrent()
  } catch { characters.value = [] }
}
function syncCurrent() {
  currentCharacter.value = characters.value.find(c => c.id === activeCharacter.value) ?? null
}
async function applyCharacter() {
  editingPersona.value = false
  syncCurrent()
  await fetch(`${BRAIN_URL}/setup/prefs`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ character: activeCharacter.value }),
  }).catch(() => {})
}
async function savePersona() {
  if (!currentCharacter.value) return
  savingPersona.value = true
  personaSaved.value = false
  try {
    const c = currentCharacter.value
    const r = await fetch(`${BRAIN_URL}/setup/characters/${c.id}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        character_prompt: c.character_prompt, verbosity: c.verbosity,
        humor_level: c.humor_level, voice_id: c.voice_id,
        interruptibility: c.interruptibility, learned_traits: c.learned_traits,
      }),
    })
    personaSaved.value = r.ok
    await fetchCharacters()
  } finally { savingPersona.value = false }
}

async function toggleTracking() {
  tracking.value = !tracking.value
  try {
    await fetch(`${BRAIN_URL}/robot/tracking`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: tracking.value }),
    })
  } catch {
    tracking.value = !tracking.value // revert on failure
  }
}

// Speak & Move combos (U36g): text + gesture in one action.
const PERFORMANCES: Record<string, { text: string[]; motion: string }> = {
  hi: { text: ['Hi there! Great to see you.'], motion: 'wave' },
  intro: {
    text: ['Hello! I am AURA, your robot assistant. I can chat, manage your calendar and tasks, recognize faces, and help you code.'],
    motion: 'bow',
  },
  joke: {
    text: [
      'Why did the robot go on holiday? It needed to recharge its batteries!',
      'I would tell you a UDP joke… but you might not get it.',
      'My favorite music? Heavy metal, obviously.',
    ],
    motion: 'gesture',
  },
  compliment: {
    text: ['You are doing great today — keep it up!'], motion: 'nod',
  },
}

async function perform(kind: string) {
  const p = PERFORMANCES[kind]
  if (!p) return
  acting.value = true
  actError.value = ''
  try {
    const text = p.text[Math.floor(Math.random() * p.text.length)]
    const resp = await fetch(`${BRAIN_URL}/robot/say`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, motion_id: p.motion }),
    })
    if (!resp.ok) actError.value = 'Robot unreachable — is it switched on?'
  } catch {
    actError.value = 'Robot unreachable — is it switched on?'
  } finally {
    acting.value = false
  }
}

async function applyVolume() {
  try {
    await fetch(`${BRAIN_URL}/robot/volume`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ volume: volume.value }),
    })
  } catch { /* robot offline — slider stays local */ }
}

onMounted(() => { fetchCharacters(); fetchMic(); fetchSleep(); fetchProactive() })
onMounted(async () => {
  try {
    const resp = await fetch(`${BRAIN_URL}/robot/volume`)
    if (resp.ok) volume.value = (await resp.json()).volume ?? 0.8
  } catch { /* keep default */ }
})

async function act(motionId: string) {
  acting.value = true
  actError.value = ''
  try {
    const resp = await fetch(`${BRAIN_URL}/robot/motion`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ motion_id: motionId, speed: 1.0, amplitude: 0.6 }),
    })
    if (!resp.ok) actError.value = 'Robot unreachable — is it switched on?'
  } catch {
    actError.value = 'Robot unreachable — is it switched on?'
  } finally {
    acting.value = false
  }
}

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString()
}
</script>

<style scoped>
.qa-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; }
.qa-btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 0.35rem;
  background: var(--surface-3); border: 1px solid var(--border); border-radius: var(--radius-sm);
  color: var(--text-muted); font-size: 0.78rem; padding: 0.45rem 0.5rem; cursor: pointer;
}
.qa-btn:hover:not(:disabled) { color: var(--text); border-color: var(--accent-border); }
.qa-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.qa-error { font-size: 0.72rem; color: var(--danger-text); margin-top: 0.3rem; }

.volume-label { display: inline-flex; align-items: center; gap: 0.3rem; }
.briefing-input {
  background: var(--surface-2); border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm); color: var(--text); padding: 0.15rem 0.4rem;
  font-size: 0.78rem; font-family: inherit;
}

/* U114: compact status strip */
.status-strip {
  display: flex; align-items: center; gap: 0.5rem;
  padding: 0.3rem 0; font-size: 0.8rem;
}
.strip-dot { width: 9px; height: 9px; border-radius: 50%; background: var(--text-faint); flex-shrink: 0; }
.strip-dot.badge-green { background: var(--ok-text, #2f9e6e); }
.strip-dot.badge-blue { background: #5cb8e4; }
.strip-dot.badge-purple { background: #9d7be0; }
.strip-dot.badge-red { background: var(--danger-text, #e5484d); }
/* badge-gray (unknown/disconnected) keeps the faint default — no alarm for "unknown" */
.strip-text { color: var(--text); }
.strip-text--faint { color: var(--text-faint); display: inline-flex; align-items: center; gap: 0.25rem; margin-left: auto; }

/* U125: labelled toggle tiles */
.toggle-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.4rem; margin: 0.5rem 0 0.4rem; }
.toggle-cell {
  display: flex; flex-direction: column; align-items: center; gap: 0.25rem;
  padding: 0.45rem 0.2rem; min-width: 0;
  background: var(--surface-2); border: 1px solid var(--border-strong);
  border-radius: var(--radius-md); color: var(--text-faint); cursor: pointer;
}
.toggle-cell:hover { border-color: var(--accent-border, var(--accent)); }
.toggle-cell--on { color: var(--accent); border-color: var(--accent); background: color-mix(in srgb, var(--accent) 10%, transparent); }
.toggle-lbl { font-size: 0.62rem; letter-spacing: 0.02em; }
.briefing-row {
  display: flex; align-items: center; gap: 0.4rem; margin-bottom: 0.5rem;
  font-size: 0.75rem; color: var(--text-faint);
}
.briefing-row .briefing-input { margin-left: auto; }

/* U125: control rows that never clip the value / edit affordance */
.ctl-row { display: flex; align-items: center; gap: 0.5rem; margin-top: 0.3rem; }
.ctl-label { display: inline-flex; align-items: center; gap: 0.3rem; flex-shrink: 0; font-size: 0.82rem; color: var(--text); }
.persona-block { margin-top: 0.9rem; display: flex; flex-direction: column; gap: 0.35rem; }
.persona-row { display: flex; align-items: center; gap: 0.4rem; min-width: 0; }

/* U114: collapsible sections */
.section-toggle {
  display: inline-flex; align-items: center; gap: 0.3rem; background: none;
  border: none; padding: 0.2rem 0; cursor: pointer; color: var(--text-faint);
  font-size: 0.72rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;
}
.section-toggle:hover { color: var(--text); }
.chev { transition: transform 0.15s; }
.chev--open { transform: rotate(90deg); }
.section-count {
  font-size: 0.62rem; padding: 0 0.35rem; border-radius: 999px; margin-left: 0.25rem;
  background: var(--surface-2); border: 1px solid var(--border); text-transform: none;
}

/* U117: app logs */
.logs-bar { display: flex; gap: 0.4rem; align-items: center; margin: 0.3rem 0; }
.qa-btn--slim { padding: 0.2rem 0.5rem; font-size: 0.7rem; }
.spin { animation: spin 0.9s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.app-log-scroll { max-height: 180px; }
.app-log-row {
  display: flex; gap: 0.4rem; align-items: baseline; font-size: 0.68rem;
  font-family: ui-monospace, monospace; padding: 0.1rem 0;
  border-bottom: 1px solid var(--border); overflow: hidden;
}
.app-log-msg { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.app-log-level { flex-shrink: 0; font-weight: 700; color: var(--text-faint); }
.app-log--warning .app-log-level { color: #e6a23c; }
.app-log--error .app-log-level { color: var(--danger-text, #e5484d); }

.toggle {
  width: 34px; height: 18px; border-radius: 999px; border: 1px solid var(--border);
  background: var(--surface-3); cursor: pointer; position: relative; padding: 0;
}
.toggle-knob {
  position: absolute; top: 1px; left: 2px; width: 14px; height: 14px;
  border-radius: 50%; background: var(--text-faint); transition: all 0.15s;
}
.toggle--on { background: var(--accent); border-color: var(--accent); }
.toggle--on .toggle-knob { left: 16px; background: #fff; }

.motion-section { min-height: 0; }
.motion-log-scroll {
  list-style: none; padding: 0; margin: 0;
  max-height: 132px; overflow-y: auto;
}
.motion-row {
  display: flex; align-items: center; gap: 0.5rem;
  padding: 0.22rem 0; font-size: 0.8rem; line-height: 1.2;
}
.motion-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.mdot-started { background: var(--warn); }
.mdot-completed { background: var(--ok); }
.mdot-failed { background: var(--danger); }
.motion-row-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.motion-row-time { color: var(--text-faint); font-variant-numeric: tabular-nums; }
.motion-empty { color: var(--text-faint); font-size: 0.8rem; padding: 0.2rem 0; }
/* U125: slider shrinks, the % never clips */
.volume-slider { flex: 1 1 0; min-width: 0; accent-color: var(--accent); }
.volume-pct { font-size: 0.72rem; color: var(--text-faint); min-width: 2.2rem; flex-shrink: 0; text-align: right; }

/* U85/U125: persona selector + editor */
.persona-select { flex: 1 1 0; min-width: 0; background: var(--surface-2); border: 1px solid var(--border-strong); border-radius: var(--radius-md); color: var(--text); padding: 0.3rem 0.4rem; font-size: 0.8rem; }
.persona-edit { flex-shrink: 0; background: none; border: 1px solid var(--border-strong); border-radius: var(--radius-md); color: var(--text-faint); cursor: pointer; padding: 0.3rem 0.4rem; }
.persona-edit:disabled { opacity: 0.4; cursor: default; }
.persona-editor { margin-top: 0.5rem; padding: 0.6rem; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--surface-2); display: flex; flex-direction: column; gap: 0.4rem; }
.pe-label { font-size: 0.72rem; color: var(--text-faint); display: flex; flex-direction: column; gap: 0.2rem; flex: 1; }
.pe-input { background: var(--surface); border: 1px solid var(--border-strong); border-radius: var(--radius-sm, 4px); color: var(--text); padding: 0.35rem; font-size: 0.78rem; resize: vertical; width: 100%; }
.pe-mini { background: var(--surface); border: 1px solid var(--border-strong); border-radius: var(--radius-sm, 4px); color: var(--text); padding: 0.25rem; font-size: 0.75rem; }
.pe-row { display: flex; gap: 0.5rem; }
.pe-actions { display: flex; align-items: center; gap: 0.5rem; }
.pe-save { background: var(--accent); color: var(--accent-contrast, #fff); border: none; border-radius: var(--radius-md); padding: 0.35rem 0.7rem; font-size: 0.78rem; cursor: pointer; }
.pe-save:disabled { opacity: 0.5; }
.pe-ok { color: var(--ok-text, #2f9e6e); font-size: 0.75rem; }
.pe-hint { font-size: 0.68rem; color: var(--text-faint); margin: 0; }
</style>
