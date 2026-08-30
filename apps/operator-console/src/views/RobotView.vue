<template>
  <main class="d2-main robot">
    <div class="robot-grid">
      <!-- ═══ Camera + body state ═══ -->
      <section class="d2-card cam-sec">
        <div class="cam-frame">
          <img v-if="camera.frameSrc.value" :src="camera.frameSrc.value" alt="Robot camera" class="cam-img">
          <div v-else class="cam-empty" />
          <!-- U161: aim the head by dragging on the picture — the ball sits
               where you last pointed, so the control reads like "look there".
               U162: only in Manual; in Follow the pad is not rendered at all,
               so aiming and face-tracking can never fight over the head. -->
          <div
            v-if="manualMode"
            ref="padEl"
            class="aim-pad"
            title="Drag to aim the head — double-click to centre"
            @pointerdown="startAim"
            @pointermove="moveAim"
            @pointerup="endAim"
            @pointercancel="endAim"
            @dblclick="centreAim"
          >
            <div class="aim-cross aim-cross--h" />
            <div class="aim-cross aim-cross--v" />
            <div class="aim-ball" :style="ballStyle" />
          </div>
          <span class="cam-tag">{{ camTag }}</span>
          <!-- U162: one explicit switch — he follows you, or you aim. Never both. -->
          <div class="head-mode" role="group" aria-label="Head control mode">
            <button :class="['head-mode-btn', !manualMode && 'on']" :disabled="switching" :title="followTitle" @click="setHeadMode(false)">
              <Eye :size="12" /> Follow
              <span v-if="!manualMode" :class="['face-dot', robot.faceVisible && 'on']" />
            </button>
            <button :class="['head-mode-btn', manualMode && 'on']" :disabled="switching"
                    title="You aim the head and torso — follow-me is off" @click="setHeadMode(true)">
              <Move :size="12" /> Manual
            </button>
          </div>
        </div>
        <div class="cam-body">
          <div class="toggle-row">
            <button class="d2-mini-toggle" :class="{ on: !asleep }" title="Awake — motors live" @click="toggleSleep">Awake</button>
            <button class="d2-mini-toggle" :class="{ on: prefs.voiceMode === 'wake_word' }" title="Mic armed for the wake word" @click="toggleWakeWord">Mic</button>
            <button class="d2-mini-toggle" :class="{ on: robot.tracking }" title="Head follows the person he sees" @click="robot.setTracking(!robot.tracking, BRAIN_URL)">Follow</button>
            <button class="d2-mini-toggle" :class="{ on: proactiveOn }" title="Speaks up unprompted for reminders" @click="toggleProactive">Proactive</button>
          </div>
          <!-- Torso: a separate axis from the head, so it gets its own control -->
          <div v-if="manualMode" class="slider-row">
            <span class="row-label">Torso</span>
            <input v-model.number="bodyYaw" type="range" min="-1" max="1" step="0.02" aria-label="Torso yaw"
                   class="vol" @input="sendAim" @dblclick="centreTorso">
            <button class="d2-ghost-btn" title="Centre the torso" @click="centreTorso">⌖</button>
          </div>
          <div class="slider-row">
            <span class="row-label">Volume</span>
            <input v-model.number="volumePct" type="range" min="0" max="100" aria-label="Speaker volume" class="vol" @change="applyVolume">
            <span class="mono row-val">{{ volumePct }}%</span>
          </div>
          <div v-if="proactiveOn" class="slider-row">
            <span class="row-label">Briefing</span>
            <input v-model="briefingTime" type="time" aria-label="Morning briefing time" class="d2-field time-field" @change="saveBriefing">
            <span class="row-note">when he speaks up unprompted</span>
          </div>
          <div class="slider-row">
            <span class="row-label">Persona</span>
            <select v-model="activePersona" class="d2-field persona-select" aria-label="Persona" @change="applyPersona">
              <option v-for="c in brainCharacters" :key="c.id" :value="c.id">{{ c.display_name }}</option>
            </select>
            <button class="d2-ghost-btn" title="Edit this persona" @click="editorOpen = !editorOpen">Edit</button>
          </div>
        </div>
      </section>

      <!-- ═══ Ask him to… (with the motion log at Full) ═══ -->
      <section class="d2-card ask-sec">
        <h3 class="d2-h3">Ask him to…</h3>
        <div v-for="g in actionGroups" :key="g.title" class="ask-group">
          <div class="ask-group-title">{{ g.title }}</div>
          <div class="ask-chips">
            <button
              v-for="a in g.items" :key="a.label" class="ask-chip"
              :disabled="acting" :title="`Run “${a.label}” now`" @click="runAction(a)"
            >{{ a.label }}</button>
          </div>
        </div>
        <p v-if="actError" class="act-error">{{ actError }}</p>
        <div v-if="full && robot.motionLog.length" class="motion-sec">
          <h3 class="d2-h3">Recent motion</h3>
          <div v-for="m in robot.motionLog" :key="m.id" class="motion-row">
            <span class="motion-dot" :class="m.status" />
            <span class="motion-name">{{ m.name }}</span>
            <span class="mono motion-time">{{ fmtTime(m.timestamp) }}</span>
          </div>
        </div>
      </section>

      <!-- ═══ Persona editor: the fields that make a character sound like itself ═══ -->
      <section v-if="editorOpen && editingCharacter" class="d2-card persona-editor">
        <div class="pe-head">
          <h3>{{ editingCharacter.display_name }}</h3>
          <span class="mono pe-meta">voice &amp; behaviour</span>
          <span class="spacer" />
          <button class="pe-x" title="Close without saving" @click="editorOpen = false">✕</button>
        </div>
        <div class="pe-fields">
          <label class="pe-field">
            <span>Voice</span>
            <!-- U273: this is the voice that actually gets used almost every
                 time — every built-in character ships with one — so it says so
                 rather than letting the Settings default look like the answer. -->
            <select v-model="editingCharacter.voice_id" class="d2-field"
                    title="This wins over the mode voice and the default in Settings. Leave it blank to fall back to those."
                    aria-label="Voice">
              <option v-for="v in TTS_VOICES" :key="v" :value="v">{{ v }}</option>
            </select>
          </label>
          <label class="pe-field">
            <span>Verbosity</span>
            <select v-model="editingCharacter.verbosity" class="d2-field" aria-label="Verbosity">
              <option value="brief">brief</option>
              <option value="normal">normal</option>
              <option value="detailed">explain the reasoning</option>
            </select>
          </label>
          <label class="pe-field">
            <span>Humour</span>
            <select v-model="editingCharacter.humor_level" class="d2-field" aria-label="Humour">
              <option value="none">none</option>
              <option value="low">dry, occasional</option>
              <option value="medium">playful</option>
              <option value="high">full comedian</option>
            </select>
          </label>
          <label class="pe-field">
            <span>Interruptibility</span>
            <select v-model="editingCharacter.interruptibility" class="d2-field" aria-label="Interruptibility">
              <option value="wake_word">wake word cuts him off</option>
              <option value="vad">any voice cuts him off</option>
              <option value="off">never — he finishes his sentence</option>
            </select>
          </label>
          <label class="pe-field">
            <span>Engine</span>
            <select v-model="editingCharacter.voice_engine" class="d2-field" aria-label="Conversation engine">
              <option value="">default</option>
              <option value="pipeline">pipeline — tools, cheaper</option>
              <option value="realtime">realtime — fluid speech</option>
            </select>
          </label>
        </div>
        <label class="pe-prompt">
          <span>How he should sound</span>
          <textarea v-model="editingCharacter.character_prompt" rows="4" aria-label="Persona instructions" class="pe-prompt-area" />
        </label>
        <label class="pe-prompt">
          <span>Learned traits <em>added by teach-mode, yours to prune</em></span>
          <textarea v-model="editingCharacter.learned_traits" rows="2" aria-label="Learned traits" class="pe-prompt-area" />
        </label>
        <div class="pe-foot">
          <button class="d2-ghost-btn" @click="hearSample">Hear a sample</button>
          <span class="spacer" />
          <button class="d2-primary-btn" :disabled="savingPersona" @click="savePersona">{{ savingPersona ? 'Saving…' : 'Save persona' }}</button>
        </div>
        <p v-if="personaSaved" class="pe-saved">Saved.</p>
      </section>

      <!-- ═══ Characters: personality + look + motion, as one choice ═══ -->
      <section class="d2-card char-sec">
        <div class="char-head">
          <h3 class="d2-h3">Character</h3>
          <span class="char-note">One pick sets his look, how he moves on screen, and which voice line he opens with.</span>
        </div>
        <p class="char-sub">Original archetypes — they nod at the robots you are thinking of without being them.</p>

        <div class="char-preview">
          <div class="char-art-box">
            <span class="char-ripple" :style="{ background: preview.hue }" />
            <span class="char-art" v-html="preview.art(74, characterStore.demoAct ?? characterStore.act)" />
          </div>
          <div class="char-preview-text">
            <div class="char-preview-title">
              <strong>{{ preview.tag }}</strong>
              <span class="selected-chip" :style="{ borderColor: preview.hue }">selected</span>
            </div>
            <p class="char-tagline">{{ preview.tagline }}</p>
            <p class="char-sample" :style="{ borderLeftColor: preview.hue }">{{ preview.sample }}</p>
            <div class="char-traits">
              <span v-for="t in preview.traits.split(' · ')" :key="t" class="trait-chip">{{ t }}</span>
              <span class="trait-chip trait-chip--move mono" :title="preview.move.why">move: {{ preview.move.id }}</span>
            </div>
          </div>
          <div class="char-preview-actions">
            <button class="d2-ghost-btn" title="Hear a sample line — watch how he speaks" @click="demoSpeak">▶ Hear him</button>
            <button class="d2-ghost-btn" :title="`His signature move: ${preview.move.id} — ${preview.move.why}`" @click="demoMove">Try a move</button>
          </div>
        </div>

        <div class="char-grid">
          <button
            v-for="(c, id) in CHARACTERS" :key="id"
            class="char-card" :class="{ active: id === characterStore.selected }"
            :title="`${c.tag} — ${c.tagline} ${c.hint}`" @click="characterStore.select(id as string)"
          >
            <span class="char-avatar" v-html="c.art(30)" />
            <span class="char-card-text">
              <span class="char-card-name">{{ c.tag }}</span>
              <span class="char-card-traits">{{ c.traits }}</span>
            </span>
          </button>
        </div>
      </section>

      <!-- ═══ Connection — last, with the honest error copy ═══ -->
      <section v-if="full" class="d2-card conn-sec">
        <h3 class="d2-h3">Connection</h3>
        <div v-if="offlineReason" class="conn-offline" role="alert">
          <TriangleAlert :size="15" class="conn-warn-icon" />
          <span>{{ offlineReason }}</span>
        </div>
        <div class="conn-facts">
          <div class="conn-fact">
            <div class="conn-k">Address</div>
            <div class="conn-v mono">{{ robotAddr || '—' }}</div>
          </div>
          <div class="conn-fact">
            <div class="conn-k">State</div>
            <div class="conn-v" :style="{ color: robot.connected ? 'var(--ok)' : 'var(--warn)' }">
              {{ robot.connected ? 'connected' : 'offline' }}
            </div>
          </div>
          <div class="conn-fact">
            <div class="conn-k">Mode</div>
            <div class="conn-v">{{ robot.mode }}</div>
          </div>
          <div class="conn-fact">
            <div class="conn-k">Following</div>
            <div class="conn-v">{{ robot.tracking ? (robot.faceVisible ? 'a face' : 'nothing to follow') : 'off' }}</div>
          </div>
          <!-- U270: three states, three sentences — a number when one was
               measured, "no battery" for the wired version, and the honest
               "the firmware does not report it" for the wireless one, which
               is what it says today. Never an invented 100%. -->
          <div class="conn-fact">
            <div class="conn-k">Power</div>
            <div class="conn-v" :class="{ low: robot.batteryPct != null && robot.batteryPct <= 20 }">
              {{ robot.batteryLine }}
            </div>
          </div>
        </div>
        <div class="conn-edit">
          <input v-model="robotAddr" class="d2-field mono conn-addr" placeholder="http://192.168.1.42:8001 · or reachy.local"
                 aria-label="Robot address" @keydown.enter="saveAddr">
          <button class="d2-ghost-btn" :disabled="savingAddr" @click="saveAddr">{{ savingAddr ? 'Testing…' : 'Use this address' }}</button>
          <button class="d2-ghost-btn" :disabled="scanning" @click="scan">{{ scanning ? 'Scanning…' : 'Scan my network' }}</button>
        </div>
        <div v-if="discovered.length" class="conn-found">
          <button v-for="d in discovered" :key="d.url" class="conn-hit mono" @click="robotAddr = d.url; saveAddr()">{{ d.url }}</button>
        </div>
        <p v-if="addrResult" class="conn-result" role="status">{{ addrResult }}</p>
      </section>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { Eye, Move, TriangleAlert } from 'lucide-vue-next'
import { CHARACTERS } from '../lib/characters'
import { BRAIN_URL } from '../lib/endpoints'
import { useCameraFeed } from '../composables/useCameraFeed'
import { useCharacterStore } from '../stores/characterStore'
import { useKnowledgeStore } from '../stores/knowledgeStore'
import { usePrefsStore } from '../stores/prefsStore'
import { useRobotStore } from '../stores/robotStore'

const robot = useRobotStore()
const prefs = usePrefsStore()
const knowledge = useKnowledgeStore()
const characterStore = useCharacterStore()
const camera = useCameraFeed()

const full = computed(() => prefs.density === 'full')
const preview = computed(() => characterStore.current)

const TTS_VOICES = ['alloy', 'ash', 'ballad', 'coral', 'echo', 'fable', 'onyx', 'nova', 'sage', 'shimmer', 'verse']

const camTag = computed(() => {
  const r = robot.lastRecognized
  if (!robot.connected) return 'robot offline'
  if (r?.known && r.display_name) return `${r.display_name} · ${Math.round(r.confidence * 100)}%`
  if (r && !r.known) return 'unknown face'
  return 'no one in view'
})

// ── U161/U162: manual aim — head via the pad on the picture, torso via its
// own slider, gated behind an explicit Follow/Manual switch ─────────────────
const padEl = ref<HTMLElement | null>(null)
const aimX = ref(0)          // -1..1, left → right   (head yaw)
const aimY = ref(0)          // -1..1, up   → down    (head pitch)
const bodyYaw = ref(0)       // -1..1                 (torso yaw)
const dragging = ref(false)
const switching = ref(false)

// Manual is simply "follow-me is off" — deriving it from the shared store is
// what keeps the Follow mini-toggle and this switch from ever disagreeing.
const manualMode = computed(() => !robot.tracking)

const followTitle = computed(() => {
  if (manualMode.value) return 'The robot follows the nearest face'
  return robot.faceVisible
    ? 'Following — a face is in view'
    : 'Following, but no face in view right now (it will look around to find one)'
})

async function setHeadMode(manual: boolean): Promise<void> {
  if (switching.value || manual === manualMode.value) return
  switching.value = true
  try {
    if (await robot.setTracking(!manual, BRAIN_URL) && manual) {
      // Start from where the head actually is (centre) rather than wherever
      // the ball was left last time, which would yank the head on first drag.
      aimX.value = 0
      aimY.value = 0
    }
  } finally { switching.value = false }
}

const ballStyle = computed(() => ({
  left: `${((aimX.value + 1) / 2) * 100}%`,
  top: `${((aimY.value + 1) / 2) * 100}%`,
}))

// The robot moves far slower than pointermove fires; sending every event would
// queue hundreds of poses and the head would keep moving long after you let
// go. At most one request in flight, always with the LATEST position.
let inFlight = false
let pendingSend = false
async function sendAim(): Promise<void> {
  // The guard lives here too, not just in the template, so a stale drag can't
  // slip a pose through after the mode flipped back to Follow.
  if (!manualMode.value) return
  if (inFlight) { pendingSend = true; return }
  inFlight = true
  try {
    const resp = await fetch(`${BRAIN_URL}/robot/aim`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ yaw: aimX.value, pitch: aimY.value, body_yaw: bodyYaw.value }),
    }).catch(() => null)
    if (resp?.ok) {
      const r = await resp.json().catch(() => ({}))
      if (r.tracking_paused) robot.tracking = false
    }
  } finally {
    inFlight = false
    if (pendingSend) { pendingSend = false; void sendAim() }
  }
}

function pointToAim(ev: PointerEvent): void {
  const el = padEl.value
  if (!el) return
  const r = el.getBoundingClientRect()
  aimX.value = Math.max(-1, Math.min(1, ((ev.clientX - r.left) / r.width) * 2 - 1))
  aimY.value = Math.max(-1, Math.min(1, ((ev.clientY - r.top) / r.height) * 2 - 1))
}
function startAim(ev: PointerEvent): void {
  dragging.value = true
  ;(ev.currentTarget as HTMLElement).setPointerCapture?.(ev.pointerId)
  pointToAim(ev)
  void sendAim()
}
function moveAim(ev: PointerEvent): void {
  if (!dragging.value) return
  pointToAim(ev)
  void sendAim()
}
function endAim(): void { dragging.value = false }
function centreAim(): void { aimX.value = 0; aimY.value = 0; void sendAim() }
function centreTorso(): void { bodyYaw.value = 0; void sendAim() }

// ── Body toggles ───────────────────────────────────────────────────────────
const asleep = ref(false)
async function fetchSleep(): Promise<void> {
  try { const r = await fetch(`${BRAIN_URL}/robot/sleep`); asleep.value = (await r.json()).asleep === true } catch { /* offline */ }
}
async function toggleSleep(): Promise<void> {
  const target = !asleep.value
  try {
    const r = await fetch(`${BRAIN_URL}/robot/${target ? 'sleep' : 'wake'}`, { method: 'POST' })
    if (r.ok) asleep.value = target
  } catch { /* offline */ }
}
function toggleWakeWord(): void {
  prefs.save({ voice_mode: prefs.voiceMode === 'wake_word' ? 'off' : 'wake_word' })
}
const proactiveOn = ref(false)
const briefingTime = ref('')
async function fetchProactive(): Promise<void> {
  try {
    const r = await fetch(`${BRAIN_URL}/robot/proactive`)
    const j = await r.json()
    proactiveOn.value = j.enabled === true
    briefingTime.value = j.briefing_time ?? ''
  } catch { /* offline */ }
}
async function toggleProactive(): Promise<void> {
  proactiveOn.value = !proactiveOn.value
  try {
    await fetch(`${BRAIN_URL}/robot/proactive`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: proactiveOn.value }),
    })
  } catch { proactiveOn.value = !proactiveOn.value }
}
async function saveBriefing(): Promise<void> {
  try {
    await fetch(`${BRAIN_URL}/robot/proactive`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ briefing_time: briefingTime.value }),
    })
  } catch { /* offline */ }
}
const volumePct = ref(80)
async function fetchVolume(): Promise<void> {
  try {
    const r = await fetch(`${BRAIN_URL}/robot/volume`)
    if (r.ok) volumePct.value = Math.round(((await r.json()).volume ?? 0.8) * 100)
  } catch { /* keep default */ }
}
async function applyVolume(): Promise<void> {
  try {
    await fetch(`${BRAIN_URL}/robot/volume`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ volume: volumePct.value / 100 }),
    })
  } catch { /* offline — slider stays local */ }
}

// ── Persona (the brain's characters) ───────────────────────────────────────
interface BrainCharacter {
  // Field names and vocab are the brain's (/setup/characters): display_name,
  // and verbosity/humor_level are WORDS (brief/normal/detailed, none..high),
  // not numbers — the first D2 pass guessed both and rendered blank selects.
  id: string; display_name: string; character_prompt: string; verbosity: string
  humor_level: string; voice_id: string; interruptibility: string
  learned_traits: string; voice_engine?: string
}
const brainCharacters = ref<BrainCharacter[]>([])
const activePersona = ref('')
const editorOpen = ref(false)
const savingPersona = ref(false)
const personaSaved = ref(false)
const editingCharacter = computed(() =>
  brainCharacters.value.find(c => c.id === activePersona.value) ?? null)

async function fetchPersonas(): Promise<void> {
  try {
    const r = await fetch(`${BRAIN_URL}/setup/characters`)
    const data = await r.json()
    brainCharacters.value = data.characters ?? []
    activePersona.value = data.active ?? brainCharacters.value[0]?.id ?? ''
  } catch { brainCharacters.value = [] }
}
async function applyPersona(): Promise<void> {
  await fetch(`${BRAIN_URL}/setup/prefs`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ character: activePersona.value }),
  }).catch(() => {})
}
async function savePersona(): Promise<void> {
  const c = editingCharacter.value
  if (!c) return
  savingPersona.value = true
  personaSaved.value = false
  try {
    const r = await fetch(`${BRAIN_URL}/setup/characters/${c.id}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        character_prompt: c.character_prompt, verbosity: c.verbosity,
        humor_level: c.humor_level, voice_id: c.voice_id,
        interruptibility: c.interruptibility, learned_traits: c.learned_traits,
        voice_engine: c.voice_engine ?? '',
      }),
    })
    personaSaved.value = r.ok
    await fetchPersonas()
  } finally { savingPersona.value = false }
}
async function hearSample(): Promise<void> {
  await fetch(`${BRAIN_URL}/robot/say`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: 'Hello! This is how I sound right now.', motion_id: 'nod' }),
  }).catch(() => {})
}

// ── Archetype demos ────────────────────────────────────────────────────────
// Both demos use the archetype's OWN signature move — id, speed and
// amplitude — so Grump shakes his head slowly and Buddy bounces. Before this
// every character sent the same 'gesture' and the traits were only words.
function demoSpeak(): void {
  characterStore.demo('speak')
  fetch(`${BRAIN_URL}/robot/say`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text: preview.value.sample.replace(/^[“”]|[“”]$/g, '').slice(0, 140),
      motion_id: preview.value.move.id,
    }),
  }).catch(() => {})
}
function demoMove(): void {
  characterStore.demo('move')
  const m = preview.value.move
  act(m.id, m.speed, m.amplitude)
}

// ── Ask him to… ────────────────────────────────────────────────────────────
const acting = ref(false)
const actError = ref('')
async function act(motionId: string, speed = 1.0, amplitude = 0.6): Promise<void> {
  acting.value = true
  actError.value = ''
  try {
    const resp = await fetch(`${BRAIN_URL}/robot/motion`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      // manual → the robot pauses follow-me so the move is fully visible (U137).
      body: JSON.stringify({ motion_id: motionId, speed, amplitude, manual: true }),
    })
    if (!resp.ok) actError.value = 'Robot unreachable — is it switched on?'
  } catch { actError.value = 'Robot unreachable — is it switched on?' } finally { acting.value = false }
}
const PERFORMANCES: Record<string, { text: string[]; motion: string }> = {
  'say hi': { text: ['Hi there! Great to see you.'], motion: 'wave' },
  'introduce himself': {
    text: ['Hello! I am AURA, your robot assistant. I can chat, manage your calendar and tasks, recognize faces, and help you code.'],
    motion: 'bow',
  },
  'tell a joke': {
    text: [
      'Why did the robot go on holiday? It needed to recharge its batteries!',
      'I would tell you a UDP joke… but you might not get it.',
      'My favorite music? Heavy metal, obviously.',
    ],
    motion: 'gesture',
  },
  'give a compliment': { text: ['You are doing great today — keep it up!'], motion: 'nod' },
}
interface ActionItem { label: string; motion?: string }
async function runAction(a: ActionItem): Promise<void> {
  const perf = PERFORMANCES[a.label]
  if (perf) {
    acting.value = true
    actError.value = ''
    try {
      const text = perf.text[Math.floor(Math.random() * perf.text.length)]
      const resp = await fetch(`${BRAIN_URL}/robot/say`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, motion_id: perf.motion }),
      })
      if (!resp.ok) actError.value = 'Robot unreachable — is it switched on?'
    } catch { actError.value = 'Robot unreachable — is it switched on?' } finally { acting.value = false }
  } else {
    await act(a.motion ?? a.label.replace(/\s+/g, '_'))
  }
}
// Density decides how much of the library shows — never what he may do.
const actionGroups = computed(() => {
  const calm = prefs.density === 'calm'
  if (calm) {
    return [{ title: 'Gestures', items: [
      { label: 'wave' }, { label: 'nod' }, { label: 'dance' }, { label: 'say hi' },
    ] }]
  }
  if (full.value) {
    return [
      { title: 'Gestures', items: [
        { label: 'wave' }, { label: 'nod' }, { label: 'shake head', motion: 'shake' },
        { label: 'look around', motion: 'look_around' }, { label: 'bow' }, { label: 'gesture' },
      ] },
      { title: 'Dance', items: [{ label: 'dance' }, { label: 'bop' }, { label: 'sway' }, { label: 'spin' }] },
      { title: 'Speak & move', items: [
        { label: 'say hi' }, { label: 'introduce himself' }, { label: 'tell a joke' }, { label: 'give a compliment' },
      ] },
    ]
  }
  return [
    { title: 'Gestures', items: [
      { label: 'wave' }, { label: 'nod' }, { label: 'look around', motion: 'look_around' }, { label: 'bow' },
    ] },
    { title: 'Speak & move', items: [{ label: 'say hi' }, { label: 'tell a joke' }, { label: 'dance' }] },
  ]
})
function fmtTime(iso: string): string { return new Date(iso).toLocaleTimeString() }

// ── Connection (the honest diagnosis stays) ────────────────────────────────
const offlineReason = ref('')
const robotAddr = ref('')
const savingAddr = ref(false)
const addrResult = ref('')
const scanning = ref(false)
const discovered = ref<{ url: string; adapter: string }[]>([])

async function syncStatus(): Promise<void> {
  try {
    const r = await fetch(`${BRAIN_URL}/robot/status`)
    if (r.ok) {
      offlineReason.value = ''
      robot.syncFromStatus(await r.json())
      return
    }
    const body = await r.json().catch(() => null)
    offlineReason.value = body?.reason ?? ''
    robot.syncFromStatus(null)
    if (offlineReason.value) void loadAddr()
  } catch { /* leave last known state */ }
}
async function loadAddr(): Promise<void> {
  try {
    const r = await fetch(`${BRAIN_URL}/robot/address`)
    if (r.ok) robotAddr.value = (await r.json()).url ?? ''
  } catch { /* offline */ }
}
async function saveAddr(): Promise<void> {
  savingAddr.value = true
  addrResult.value = ''
  try {
    const r = await fetch(`${BRAIN_URL}/robot/address`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: robotAddr.value.trim() }),
    })
    const body = await r.json().catch(() => null)
    if (body) {
      robotAddr.value = body.url
      addrResult.value = body.reachable ? 'Connected.' : body.detail
      if (body.reachable) await syncStatus()
    }
  } catch { addrResult.value = 'The brain did not respond.' } finally { savingAddr.value = false }
}
async function scan(): Promise<void> {
  scanning.value = true
  discovered.value = []
  addrResult.value = ''
  try {
    const r = await fetch(`${BRAIN_URL}/robot/discover`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
    const body = await r.json()
    discovered.value = body.found ?? []
    if (!discovered.value.length) addrResult.value = 'Nothing answered on this network.'
  } catch { addrResult.value = 'The brain did not respond.' } finally { scanning.value = false }
}

let statusTimer: ReturnType<typeof setInterval> | undefined
onMounted(() => {
  fetchPersonas(); fetchSleep(); fetchProactive(); fetchVolume(); syncStatus(); loadAddr()
  knowledge.fetchPeople()
  statusTimer = setInterval(syncStatus, 8000)
})
onUnmounted(() => clearInterval(statusTimer))
</script>

<style scoped>
.robot-grid { display: flex; align-items: flex-start; gap: 14px; flex-wrap: wrap; max-width: 960px; }
.mono { font-family: var(--font-mono); }
.spacer { flex: 1; }

.cam-sec { flex: 1 1 330px; min-width: 280px; overflow: hidden; }
.cam-frame { position: relative; width: 100%; height: 196px; background: linear-gradient(160deg, #2b3a30 0%, #1a231d 60%, #121a15 100%); }
.cam-img { width: 100%; height: 100%; object-fit: cover; display: block; }
.cam-empty { position: absolute; inset: 0; }
.cam-tag {
  position: absolute; left: 9px; bottom: 9px; color: #fff; font-size: 11.5px;
  padding: 3px 10px; border-radius: 999px; background: rgba(8, 16, 11, 0.5);
}
/* U161: the aim pad sits over the whole picture; the crosshair says "this is
   a control", the ball says where the head is pointed. */
.aim-pad { position: absolute; inset: 0; cursor: crosshair; touch-action: none; }
.aim-cross { position: absolute; background: rgba(255, 255, 255, 0.18); pointer-events: none; }
.aim-cross--h { left: 8%; right: 8%; top: 50%; height: 1px; }
.aim-cross--v { top: 8%; bottom: 8%; left: 50%; width: 1px; }
.aim-ball {
  position: absolute; width: 14px; height: 14px; border-radius: 50%;
  background: var(--accent); border: 2px solid #fff;
  transform: translate(-50%, -50%); pointer-events: none;
  box-shadow: 0 0 8px rgba(0, 0, 0, 0.45);
}
.head-mode { position: absolute; right: 9px; bottom: 9px; display: flex; gap: 3px; }
.head-mode-btn {
  display: inline-flex; align-items: center; gap: 5px; padding: 4px 10px;
  border-radius: 999px; font-size: 11px; font-weight: 600; cursor: pointer;
  background: rgba(8, 16, 11, 0.55); border: 1px solid rgba(255, 255, 255, 0.25);
  color: #fff; font-family: inherit;
}
.head-mode-btn.on { background: var(--accent); border-color: var(--accent); }
.face-dot { width: 7px; height: 7px; border-radius: 50%; background: rgba(255, 255, 255, 0.35); }
.face-dot.on { background: #fff; }
.cam-body { padding: 12px 14px; display: flex; flex-direction: column; gap: 10px; }
.toggle-row { display: flex; gap: 6px; flex-wrap: wrap; }
.slider-row { display: flex; align-items: center; gap: 9px; }
.row-label { font-size: 12.5px; color: var(--ink-3); width: 52px; flex-shrink: 0; }
.row-val { font-size: 11px; color: var(--ink-3); width: 34px; text-align: right; flex-shrink: 0; }
.row-note { font-size: 12px; color: var(--ink-3); }
.vol { flex: 1 1 auto; min-width: 40px; accent-color: var(--accent); }
.time-field, .persona-select { width: auto; flex: 1; min-width: 0; padding: 6px 9px; font-size: 12.5px; }

.ask-sec { flex: 1 1 300px; min-width: 260px; padding: 14px 16px; }
.ask-group { margin-bottom: 13px; }
.ask-group-title { font-size: 11.5px; font-weight: 600; color: var(--ink-3); margin-bottom: 6px; }
.ask-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.ask-chip {
  padding: 6px 12px; border-radius: 999px; background: var(--surface-2);
  border: 1px solid var(--line); color: var(--ink-2);
  font-size: 12.5px; font-weight: 600; cursor: pointer; font-family: inherit;
}
.ask-chip:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
.act-error { margin: 4px 0 0; font-size: 12.5px; color: var(--danger); }
.motion-sec { border-top: 1px solid var(--line); padding-top: 11px; margin-top: 4px; }
.motion-row { display: flex; align-items: center; gap: 9px; padding: 3px 0; font-size: 12.5px; }
.motion-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; background: var(--info); }
.motion-dot.completed { background: var(--ok); }
.motion-dot.failed { background: var(--danger); }
.motion-dot.started { background: var(--warn); }
.motion-name { flex: 1; min-width: 0; }
.motion-time { font-size: 10.5px; color: var(--ink-3); }

.persona-editor { order: 2; flex: 1 1 100%; border: 1.5px solid var(--accent); padding: 16px 18px; }
.pe-head { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
.pe-head h3 { margin: 0; font-size: 15px; }
.pe-meta { font-size: 11px; color: var(--ink-3); }
.pe-x { background: none; border: none; color: var(--ink-3); cursor: pointer; font-size: 15px; padding: 0; }
.pe-fields { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 12px; }
.pe-field { flex: 1 1 180px; min-width: 170px; display: flex; flex-direction: column; gap: 5px; }
.pe-field span { font-size: 12px; color: var(--ink-3); }
.pe-prompt { display: flex; flex-direction: column; gap: 5px; margin-bottom: 12px; }
.pe-prompt span { font-size: 12px; color: var(--ink-3); }
.pe-prompt em { font-style: normal; font-size: 11.5px; }
.pe-prompt-area {
  width: 100%; box-sizing: border-box; background: var(--sunken);
  border: 1.5px solid var(--line-strong); border-radius: 11px; color: var(--ink);
  padding: 11px 13px; font-size: 13px; line-height: 1.6; resize: vertical; font-family: inherit;
}
.pe-foot { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.pe-saved { margin: 8px 0 0; font-size: 12.5px; color: var(--ok); }

.char-sec { order: 3; flex: 1 1 100%; padding: 14px 16px; }
.char-head { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; margin-bottom: 4px; }
.char-note { font-size: 12.5px; color: var(--ink-2); }
.char-sub { margin: 0 0 12px; font-size: 12px; color: var(--ink-3); }
.char-preview {
  display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
  padding: 14px 16px; border: 1.5px solid var(--line-strong); border-radius: 12px;
  background: var(--surface-2); margin-bottom: 14px;
}
.char-art-box {
  position: relative; width: 92px; height: 92px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  border-radius: 14px; background: var(--surface); border: 1px solid var(--line);
}
.char-ripple { position: absolute; inset: 14px; border-radius: 50%; animation: ripple 3.4s ease-out infinite; }
.char-art { position: relative; display: flex; }
.char-preview-text { flex: 1; min-width: 200px; }
.char-preview-title { display: flex; align-items: center; gap: 9px; flex-wrap: wrap; }
.char-preview-title strong { font-size: 16px; }
.selected-chip {
  font-size: 10.5px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase;
  padding: 2px 10px; border-radius: 999px; background: var(--surface-2);
  border: 1px solid var(--line-strong); color: var(--ink-2);
}
.char-tagline { margin: 5px 0 9px; font-size: 13px; color: var(--ink-2); line-height: 1.45; }
.char-sample {
  margin: 0; font-size: 14px; line-height: 1.5; color: var(--ink);
  background: var(--surface); border: 1px solid var(--line); border-left: 3px solid var(--accent);
  border-radius: 4px 10px 10px 4px; padding: 9px 13px;
}
.char-traits { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 9px; }
.trait-chip {
  font-size: 11.5px; font-weight: 600; padding: 3px 10px; border-radius: 999px;
  background: var(--surface); border: 1px solid var(--line); color: var(--ink-2);
}
.trait-chip--move { border-style: dashed; color: var(--ink-2); }
.char-preview-actions { display: flex; flex-direction: column; gap: 6px; flex-shrink: 0; }
.char-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(168px, 100%), 1fr)); gap: 8px; }
.char-card {
  display: flex; align-items: center; gap: 9px; padding: 9px 11px; border-radius: 11px;
  cursor: pointer; font-family: inherit; text-align: left;
  background: var(--surface-2); border: 1.5px solid var(--line); color: var(--ink);
}
.char-card.active { background: var(--accent-wash); border-color: var(--accent); }
.char-avatar {
  width: 36px; height: 36px; flex-shrink: 0; display: inline-flex;
  align-items: center; justify-content: center; border-radius: 9px;
  background: var(--surface); border: 1px solid var(--line);
}
.char-card-text { flex: 1; min-width: 0; }
.char-card-name { display: block; font-size: 13.5px; font-weight: 700; }
.char-card-traits { display: block; font-size: 11.5px; color: var(--ink-3); margin-top: 3px; line-height: 1.35; }

.conn-sec { order: 4; flex: 1 1 100%; padding: 14px 16px; }
.conn-offline {
  display: flex; gap: 9px; align-items: flex-start; padding: 11px 13px;
  border: 1.5px solid var(--warn); border-radius: 11px; background: var(--warn-wash);
  font-size: 13px; color: var(--ink-2); line-height: 1.5; margin-bottom: 12px;
}
.conn-warn-icon { color: var(--warn); flex-shrink: 0; margin-top: 2px; }
.conn-facts { display: flex; flex-wrap: wrap; gap: 12px 28px; margin-bottom: 12px; }
.conn-fact { min-width: 140px; }
.conn-k { font-size: 11.5px; color: var(--ink-3); }
.conn-v { font-size: 13.5px; font-weight: 600; }
/* U270: a real, low reading is the one case worth shouting about. The
   "not reported" case stays quiet — it is a fact, not an alarm. */
.conn-v.low { color: var(--danger, #e5484d); }
.conn-edit { display: flex; gap: 8px; flex-wrap: wrap; }
.conn-addr { flex: 1; min-width: 220px; width: auto; }
.conn-found { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
.conn-hit {
  padding: 6px 12px; border-radius: 9px; background: var(--surface);
  border: 1.5px solid var(--ok); color: var(--ink); font-size: 12px; cursor: pointer;
}
.conn-result { margin: 8px 0 0; font-size: 12.5px; color: var(--ink-2); }
</style>
