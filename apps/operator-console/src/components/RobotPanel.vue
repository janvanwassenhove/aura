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
      </div>
      <p v-if="actError" class="qa-error">{{ actError }}</p>
    </div>

    <div class="mt-3">
      <h3 class="section-label">Motion Log</h3>
      <ul class="motion-log">
        <li v-for="entry in robotStore.motionLog" :key="entry.id" class="motion-entry">
          <span :class="['status-dot', `dot-${entry.status}`]" />
          <span class="motion-name">{{ entry.name }}</span>
          <span class="motion-time">{{ fmtTime(entry.timestamp) }}</span>
        </li>
        <li v-if="robotStore.motionLog.length === 0" class="text-gray-400 text-sm">No motions yet</li>
      </ul>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ChevronsDown, Hand, Moon, MoveVertical, Power, Sparkles, Volume2, VolumeX } from 'lucide-vue-next'
import { useRobotStore } from '../stores/robotStore'

const BRAIN_URL = import.meta.env.VITE_BRAIN_URL ?? import.meta.env.VITE_ORCHESTRATOR_URL ?? 'http://localhost:8000'

const robotStore = useRobotStore()
const acting = ref(false)
const actError = ref('')

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
.qa-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.4rem; }
.qa-btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 0.3rem;
  background: var(--surface-3); border: 1px solid var(--border); border-radius: var(--radius-sm);
  color: var(--text-muted); font-size: 0.78rem; padding: 0.35rem 0.5rem; cursor: pointer;
}
.qa-btn:hover:not(:disabled) { color: var(--text); border-color: var(--accent-border); }
.qa-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.qa-error { font-size: 0.72rem; color: var(--danger-text); margin-top: 0.3rem; }
</style>
