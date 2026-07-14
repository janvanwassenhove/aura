<template>
  <section class="panel">
    <h2 class="panel-title">Robot State</h2>

    <div class="status-row">
      <span class="label">Mode</span>
      <span :class="['badge', robotStore.statusBadgeClass]">{{ robotStore.mode }}</span>
    </div>

    <div class="status-row">
      <span class="label">Behavior</span>
      <span class="value">{{ robotStore.behaviorState }}</span>
    </div>

    <div class="status-row">
      <span class="label">Speaking</span>
      <span :class="['indicator', robotStore.isSpeaking ? 'indicator-active' : 'indicator-idle']">
        <Volume2 v-if="robotStore.isSpeaking" :size="14" />
        <VolumeX v-else :size="14" />
        {{ robotStore.isSpeaking ? 'Speaking' : 'Silent' }}
      </span>
    </div>

    <div v-if="robotStore.isSpeaking && robotStore.currentTranscript" class="transcript-box">
      {{ robotStore.currentTranscript }}
    </div>

    <div v-if="robotStore.lastRecognized" class="status-row">
      <span class="label">Recognized</span>
      <span v-if="robotStore.lastRecognized.known" class="value">
        {{ robotStore.lastRecognized.display_name }}
        <span class="text-gray-400 text-xs">({{ Math.round(robotStore.lastRecognized.confidence * 100) }}%)</span>
      </span>
      <span v-else class="value text-gray-400">Unknown face</span>
    </div>

    <div class="status-row mt-3">
      <span class="label volume-label"><Eye :size="14" /> Follow me</span>
      <button
        :class="['toggle', tracking && 'toggle--on']"
        :title="tracking ? 'Stop following faces' : 'Follow the nearest face'"
        @click="toggleTracking"
      ><span class="toggle-knob" /></button>
    </div>

    <div class="status-row">
      <span class="label volume-label">
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

    <div class="mt-3">
      <h3 class="section-label">Quick Actions</h3>
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
      <p v-if="actError" class="qa-error">{{ actError }}</p>
    </div>

    <div class="mt-3 motion-section">
      <h3 class="section-label">Motion Log</h3>
      <ul class="motion-log-scroll">
        <li v-for="entry in robotStore.motionLog" :key="entry.id" class="motion-row">
          <span :class="['motion-dot', `mdot-${entry.status}`]" />
          <span class="motion-row-name">{{ entry.name }}</span>
          <span class="motion-row-time">{{ fmtTime(entry.timestamp) }}</span>
        </li>
        <li v-if="robotStore.motionLog.length === 0" class="motion-empty">No motions yet</li>
      </ul>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  Bot, ChevronsDown, Eye, Hand, Laugh, Moon, MoveHorizontal, MoveVertical,
  Power, Sparkles, ThumbsUp, Volume1, Volume2, VolumeX,
} from 'lucide-vue-next'
import { useRobotStore } from '../stores/robotStore'

const BRAIN_URL = import.meta.env.VITE_BRAIN_URL ?? import.meta.env.VITE_ORCHESTRATOR_URL ?? 'http://localhost:8000'

const robotStore = useRobotStore()
const acting = ref(false)
const actError = ref('')
const volume = ref(0.8)

const tracking = ref(true) // adapter enables head tracking on connect

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
.volume-slider { flex: 1; margin: 0 0.5rem; accent-color: var(--accent); }
.volume-pct { font-size: 0.72rem; color: var(--text-faint); min-width: 2.2rem; text-align: right; }
</style>
