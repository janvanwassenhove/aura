<template>
  <section class="panel video-panel">
    <div class="flex items-center justify-between mb-2">
      <h2 class="panel-title mb-0">Robot Camera</h2>
      <span class="cam-header-right">
        <!-- U175: manual revive for a silently-stalled MJPEG stream -->
        <button class="cam-refresh" title="Reconnect the camera stream" aria-label="Reconnect camera" @click="bumpStream">
          <RotateCw :size="12" />
        </button>
        <span v-if="state === 'live'" class="live-badge"><Video :size="11" /> LIVE</span>
      </span>
    </div>

    <div class="video-frame">
      <!-- U195: one frame per request, next one asked only after this one has
           rendered. Self-paces to whatever the link can carry, and nothing can
           queue up behind it. -->
      <img
        v-show="state === 'live'"
        :src="frameSrc"
        alt="Robot camera"
        class="video-img"
      />
      <div v-if="state !== 'live'" class="video-placeholder">
        <VideoOff :size="28" class="mb-2" />
        <p v-if="state === 'connecting'">Connecting to the robot camera…</p>
        <template v-else>
          <p>No camera feed.</p>
          <p class="hint">Is the robot on? The camera starts ~10 s after the robot boots. Retrying…</p>
        </template>
      </div>

      <!-- U161: aim the head by dragging on the picture — the ball sits where
           you last pointed, so the control reads like "look there", not
           "press left four times".
           U162: only in Manual mode. In Follow mode the pad is not rendered at
           all, so aiming and face-tracking can never fight over the head. -->
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

      <!-- Recognition overlay -->
      <div v-if="recognized" class="recognized-overlay">
        <UserCheck v-if="recognized.known" :size="13" />
        <UserX v-else :size="13" />
        {{ recognized.known ? recognized.display_name : 'Unknown face' }}
        <span v-if="recognized.known" class="confidence">{{ Math.round(recognized.confidence * 100) }}%</span>
      </div>

      <!-- U162: one explicit switch. The robot is either following you or
           taking aim from you — never both, so they cannot fight. -->
      <div class="mode-switch" role="group" aria-label="Head control mode">
        <button
          :class="['mode-btn', !manualMode && 'mode-btn--on']"
          :disabled="switching"
          :title="followTitle"
          @click="setMode(false)"
        >
          <Eye :size="12" /> Follow
          <!-- U165: a still head looks the same whether the tracker is broken
               or simply has nobody in view — say which it is. -->
          <span v-if="!manualMode" :class="['face-dot', robotStore.faceVisible && 'face-dot--on']" />
        </button>
        <button
          :class="['mode-btn', manualMode && 'mode-btn--on']"
          :disabled="switching"
          title="You aim the head and torso — follow-me is off"
          @click="setMode(true)"
        >
          <Move :size="12" /> Manual
        </button>
      </div>
    </div>

    <!-- Torso: a separate axis from the head, so it gets its own control -->
    <div v-if="manualMode" class="aim-bar">
      <div class="aim-row">
        <label class="aim-label" for="torso">Torso</label>
        <input
          id="torso" v-model.number="bodyYaw" class="aim-slider" type="range"
          min="-1" max="1" step="0.02" @input="sendAim" @dblclick="centreTorso"
        />
        <button class="aim-mini" title="Centre the torso" @click="centreTorso">⌖</button>
      </div>
      <p class="aim-note aim-note--faint">Drag on the picture to aim · double-click to centre</p>
    </div>
    <p v-if="modeError" class="aim-note aim-note--err">{{ modeError }}</p>

    <!-- Recognition / enrollment -->
    <!-- U179: the old text pointed at a "Knowledge" panel that is no longer
         mounted. Point at what actually exists: the brain panel's
         "Secure profiles" box, which enables recognition. -->
    <div v-if="recognitionEnabled === false" class="hint mt-2">
      Face recognition is off, so <strong>This is me</strong> is hidden. Open the
      <strong>brain panel</strong> (top right) and set a passphrase under
      <strong>Secure profiles</strong> to switch it on.
    </div>
    <form v-else-if="recognitionEnabled" class="enroll-row mt-2" @submit.prevent="enroll">
      <input v-model="enrollId" class="filter-input" placeholder="person id (e.g. jan)" />
      <button class="btn-primary enroll-btn" :disabled="!enrollId.trim() || enrolling" type="submit">
        <ScanFace :size="13" /> {{ enrolling ? '…' : 'This is me' }}
      </button>
    </form>
    <p v-if="enrollMessage" :class="['enroll-msg', enrollOk ? 'enroll-msg--ok' : 'enroll-msg--err']">{{ enrollMessage }}</p>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { Eye, Move, RotateCw, ScanFace, UserCheck, UserX, Video, VideoOff } from 'lucide-vue-next'
import { useRobotStore } from '../stores/robotStore'

const BRAIN_URL = import.meta.env.VITE_BRAIN_URL ?? import.meta.env.VITE_ORCHESTRATOR_URL ?? 'http://localhost:8000'

const robotStore = useRobotStore()
const recognized = computed(() => robotStore.lastRecognized)

const state = ref<'connecting' | 'live' | 'off'>('connecting')
const streamKey = ref(0)
const frameSrc = ref('')
const recognitionEnabled = ref<boolean | null>(null)
const enrollId = ref('')
const enrolling = ref(false)
const enrollMessage = ref('')
const enrollOk = ref(false)

let retryTimer: ReturnType<typeof setTimeout> | null = null

// U175: restart the frame loop. A stream whose SERVER went away used to stall
// silently — no error event, no retry, frozen panel until a page reload
// ("camera lijkt niet meer te werken"). The polling loop cannot stall the same
// way (each frame is its own request), but an explicit restart still gives the
// owner a way back after a long outage.
function bumpStream() {
  state.value = 'connecting'
  streamKey.value++
  startFrameLoop()
}

// ---------------------------------------------------------------------------
// U195: the live view, one frame at a time.
//
// The MJPEG stream pushed frames at a fixed rate whether or not the link could
// carry them, and TCP delays rather than drops — so the picture drifted further
// behind the longer it ran (measured 0.6s -> 2.5s and climbing). Asking for one
// frame and only requesting the next once it has decoded means at most one
// frame is ever in flight: no queue can form, and the rate settles at whatever
// the link actually sustains. Measured flat at ~0.25s.
// ---------------------------------------------------------------------------
const MIN_FRAME_MS = 66      // ~15 fps ceiling; the link decides the real rate
let loopId = 0
let currentUrl = ''

async function startFrameLoop() {
  const myLoop = ++loopId   // any older loop sees the mismatch and stops
  while (myLoop === loopId) {
    const started = performance.now()
    try {
      const resp = await fetch(`${BRAIN_URL}/robot/camera/frame.jpg`, { cache: 'no-store' })
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const blob = await resp.blob()
      if (myLoop !== loopId) break
      const next = URL.createObjectURL(blob)
      // Revoke the PREVIOUS url only after swapping, so the <img> is never
      // pointed at a blob that has already been freed (that renders blank).
      const prev = currentUrl
      currentUrl = next
      frameSrc.value = next
      if (prev) URL.revokeObjectURL(prev)
      state.value = 'live'
      // On a fast link the loop would otherwise spin as fast as the robot can
      // encode, pegging the Pi for frames no eye can tell apart. Cap the rate;
      // on a slow link the request itself already takes longer than this and
      // the wait is zero.
      const left = MIN_FRAME_MS - (performance.now() - started)
      if (left > 0) await new Promise(r => setTimeout(r, left))
    } catch {
      if (myLoop !== loopId) break
      state.value = 'off'
      await new Promise(r => setTimeout(r, 2000))   // robot down — back off
    }
  }
}

function stopFrameLoop() {
  loopId++                                   // running loop exits on mismatch
  if (currentUrl) { URL.revokeObjectURL(currentUrl); currentUrl = '' }
}

// Brain restarted (WS reconnected) → the stream endpoint is back; remount.
watch(() => robotStore.wsGeneration, (n, old) => {
  if (old !== undefined && old > 0 && n > old) bumpStream()
})
// Robot came back online (Pi restart) → the brain's proxy source is back.
watch(() => robotStore.connected, (now, was) => {
  if (now && was === false) bumpStream()
})

async function fetchRecognitionStatus() {
  try {
    const resp = await fetch(`${BRAIN_URL}/recognition/status`)
    recognitionEnabled.value = resp.ok ? (await resp.json()).enabled === true : false
  } catch {
    recognitionEnabled.value = false
  }
}

async function enroll() {
  enrolling.value = true
  enrollMessage.value = ''
  try {
    const resp = await fetch(`${BRAIN_URL}/recognition/enroll`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ person_id: enrollId.value.trim().toLowerCase() }),
    })
    const body = await resp.json().catch(() => ({}))
    enrollOk.value = resp.ok
    enrollMessage.value = resp.ok
      ? `Enrolled ${body.enrolled} — the robot will now recognize this face.`
      : (body.error ?? `Enrollment failed (${resp.status})`)
  } catch {
    enrollOk.value = false
    enrollMessage.value = 'Could not reach the brain.'
  } finally {
    enrolling.value = false
  }
}

// ── U161: manual aim (head via the pad, torso via its own slider) ──
// ── U162: gated behind an explicit Follow/Manual mode ──
const padEl = ref<HTMLElement | null>(null)
const aimX = ref(0)          // -1..1, left → right   (head yaw)
const aimY = ref(0)          // -1..1, up   → down    (head pitch)
const bodyYaw = ref(0)       // -1..1                 (torso yaw)
const dragging = ref(false)
const switching = ref(false)
const modeError = ref('')

// Manual is simply "follow-me is off" — deriving it from the shared store
// instead of a second local flag is what keeps the Robot panel's Follow toggle
// and this switch from disagreeing.
const manualMode = computed(() => !robotStore.tracking)

const followTitle = computed(() => {
  if (manualMode.value) return 'The robot follows the nearest face'
  return robotStore.faceVisible
    ? 'Following — a face is in view'
    : 'Following, but no face in view right now (it will look around to find one)'
})

async function setMode(manual: boolean): Promise<void> {
  if (switching.value || manual === manualMode.value) return
  switching.value = true
  modeError.value = ''
  try {
    if (!(await robotStore.setTracking(!manual, BRAIN_URL))) {
      modeError.value = 'Could not switch mode — is the robot reachable?'
      return
    }
    if (manual) {
      // Start from where the head actually is (centre) rather than wherever
      // the ball was left last time, which would yank the head on first drag.
      aimX.value = 0
      aimY.value = 0
    }
  } finally {
    switching.value = false
  }
}

const ballStyle = computed(() => ({
  left: `${((aimX.value + 1) / 2) * 100}%`,
  top: `${((aimY.value + 1) / 2) * 100}%`,
}))

// The robot moves far slower than pointermove fires; sending every event would
// queue hundreds of poses and the head would keep moving long after you let go.
// Send at most one in flight, always with the LATEST position (coalesced).
let inFlight = false
let pendingSend = false

async function sendAim(): Promise<void> {
  // U162: never aim while following — the guard lives here too, not just in
  // the template, so a stale drag (or a keyboard nudge on the slider) can't
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
      // The robot pauses tracking on any aim; mirror that so the switch
      // shows Manual even if the pose came from somewhere else.
      if (r.tracking_paused) robotStore.tracking = false
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

function centreAim(): void {
  aimX.value = 0
  aimY.value = 0
  void sendAim()
}

function centreTorso(): void {
  bodyYaw.value = 0
  void sendAim()
}

// U162: read the real mode on open — the robot may already be in Manual (a
// motion paused tracking, or the Robot panel toggled it) and the switch must
// not claim otherwise.
async function fetchRobotMode(): Promise<void> {
  try {
    const resp = await fetch(`${BRAIN_URL}/robot/status`)
    if (resp.ok) robotStore.syncFromStatus(await resp.json())
  } catch { /* offline — keep whatever the store has */ }
}

onMounted(() => {
  void fetchRecognitionStatus()
  void fetchRobotMode()
  void startFrameLoop()
})
onUnmounted(() => {
  if (retryTimer) clearTimeout(retryTimer)
  stopFrameLoop()   // a hidden panel must not keep pulling frames off the robot
})
</script>

<style scoped>
.video-panel { margin-top: 1rem; }
.cam-header-right { display: inline-flex; align-items: center; gap: 0.4rem; }
.cam-refresh {
  display: inline-flex; align-items: center; justify-content: center;
  width: 22px; height: 22px; border-radius: 5px; cursor: pointer;
  background: none; border: 1px solid var(--border); color: var(--text-muted);
}
.cam-refresh:hover { color: var(--text); border-color: var(--accent); }
.live-badge {
  display: inline-flex; align-items: center; gap: 0.25rem;
  font-size: 0.65rem; font-weight: 700; letter-spacing: 0.05em;
  color: var(--danger); border: 1px solid var(--danger);
  border-radius: 999px; padding: 0.05rem 0.45rem;
}
.video-frame {
  position: relative; width: 100%; aspect-ratio: 16 / 9;
  background: var(--surface-3); border: 1px solid var(--border);
  border-radius: var(--radius); overflow: hidden;
}
.video-img { width: 100%; height: 100%; object-fit: cover; display: block; }
.video-placeholder {
  position: absolute; inset: 0;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  color: var(--text-faint); font-size: 0.78rem; text-align: center; padding: 0 1rem;
}
.video-placeholder p { margin: 0.1rem 0; }
.hint { font-size: 0.72rem; color: var(--text-faint); }
.recognized-overlay {
  position: absolute; left: 0.5rem; bottom: 0.5rem;
  display: inline-flex; align-items: center; gap: 0.3rem;
  background: var(--overlay); color: #fff;
  font-size: 0.72rem; padding: 0.2rem 0.55rem; border-radius: 999px;
  backdrop-filter: blur(4px);
}
.confidence { opacity: 0.75; }

/* U161: aim pad — a ball you drag on the live picture */
.aim-pad { position: absolute; inset: 0; cursor: grab; touch-action: none; }
.aim-pad:active { cursor: grabbing; }
.aim-cross { position: absolute; background: rgba(255, 255, 255, 0.18); pointer-events: none; }
.aim-cross--h { left: 8%; right: 8%; top: 50%; height: 1px; }
.aim-cross--v { top: 8%; bottom: 8%; left: 50%; width: 1px; }
.aim-ball {
  position: absolute; width: 30px; height: 30px;
  margin: -15px 0 0 -15px; border-radius: 50%;
  border: 2px solid #fff; background: rgba(255, 255, 255, 0.22);
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.35), 0 2px 8px rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(2px); pointer-events: none;
  transition: left 0.08s linear, top 0.08s linear;
}
/* U162: segmented Follow | Manual switch, floating on the picture */
.mode-switch {
  position: absolute; right: 0.5rem; top: 0.5rem;
  display: inline-flex; border-radius: 6px; overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.25);
  background: var(--overlay); backdrop-filter: blur(4px);
}
.mode-btn {
  display: inline-flex; align-items: center; gap: 0.25rem;
  padding: 0.2rem 0.5rem; font-size: 0.66rem; font-weight: 600;
  background: none; border: none; color: #fff; cursor: pointer;
  opacity: 0.65;
}
.mode-btn + .mode-btn { border-left: 1px solid rgba(255, 255, 255, 0.25); }
.mode-btn:hover:not(:disabled) { opacity: 1; }
.mode-btn--on { background: var(--accent); opacity: 1; }
/* U165: lit = a face is actually in view; dim = following but nobody there */
.face-dot {
  width: 5px; height: 5px; border-radius: 50%;
  background: rgba(255, 255, 255, 0.35); margin-left: 0.1rem;
}
.face-dot--on { background: var(--ok, #2f9e6e); box-shadow: 0 0 4px var(--ok, #2f9e6e); }
.mode-btn:disabled { cursor: default; }
.aim-bar { margin-top: 0.45rem; }
.aim-row { display: flex; align-items: center; gap: 0.5rem; }
.aim-label { font-size: 0.72rem; color: var(--text-muted); min-width: 3rem; }
.aim-slider { flex: 1; accent-color: var(--accent); }
.aim-mini {
  background: none; border: 1px solid var(--border-strong); color: var(--text-muted);
  border-radius: 4px; width: 22px; height: 22px; cursor: pointer; line-height: 1;
}
.aim-mini:hover { color: var(--text); }
.aim-note { font-size: 0.7rem; color: var(--warn, #d9a441); margin: 0.3rem 0 0; }
.aim-note--faint { color: var(--text-faint); }
.aim-note--err { color: var(--danger-text, #e5484d); }
.enroll-row { display: flex; gap: 0.4rem; }
.enroll-btn { display: inline-flex; align-items: center; gap: 0.3rem; font-size: 0.78rem; padding: 0.3rem 0.7rem; white-space: nowrap; }
.enroll-msg { font-size: 0.72rem; margin: 0.3rem 0 0; }
.enroll-msg--ok { color: var(--ok); }
.enroll-msg--err { color: var(--danger-text); }
.mt-2 { margin-top: 0.5rem; }
.mb-2 { margin-bottom: 0.5rem; }
.mb-0 { margin-bottom: 0; }
</style>
