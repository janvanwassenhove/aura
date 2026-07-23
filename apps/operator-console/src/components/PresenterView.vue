<template>
  <div class="presenter">
    <!-- Setup: build (or paste) a scenario before starting -->
    <div v-if="!store.status.active" class="pv-setup">
      <div class="pv-setup-head">
        <h2>Present with the robot</h2>
        <div class="pv-mode-toggle">
          <button :class="['pv-tab', !rawMode && 'pv-tab--on']" @click="rawMode = false">Build</button>
          <button :class="['pv-tab', rawMode && 'pv-tab--on']" @click="rawMode = true">YAML</button>
        </div>
        <button class="pv-x" aria-label="Close" @click="$emit('close')"><X :size="18" /></button>
      </div>
      <p class="pv-hint">
        Keep PowerPoint open in a slideshow — slide beats fire as you advance it;
        keyword beats fire when you say the word.
      </p>

      <!-- Form builder (default) -->
      <ScenarioBuilder v-if="!rawMode" ref="builder" @start="startFromScenario" />

      <!-- Raw YAML (power users) -->
      <template v-else>
        <textarea v-model="yamlText" class="pv-yaml" spellcheck="false"
                  placeholder="title: …&#10;beats:&#10;  - id: intro&#10;    trigger: slide:1&#10;    mode: speak&#10;    text: …"></textarea>
        <div class="pv-setup-actions">
          <button class="pv-btn pv-btn--go" :disabled="!yamlText.trim() || store.busy" @click="start">
            {{ store.busy ? 'Starting…' : 'Start presentation' }}
          </button>
          <span v-if="store.error" class="pv-err">{{ store.error }}</span>
        </div>
      </template>
    </div>

    <!-- Live: the presenter stage -->
    <div v-else class="pv-stage">
      <div class="pv-top">
        <span class="pv-title">{{ store.status.title || 'Presentation' }}</span>
        <span class="pv-slide" v-if="store.status.current_slide != null">
          <Presentation :size="14" /> slide {{ store.status.current_slide }}
        </span>
        <span :class="['pv-ppt', store.status.powerpoint_watching ? 'pv-ppt--on' : 'pv-ppt--off']">
          {{ store.status.powerpoint_watching ? 'PowerPoint linked' : 'manual slides' }}
        </span>
        <span class="pv-spacer" />
        <button class="pv-btn pv-btn--stop" :disabled="store.busy" @click="stop">End</button>
        <button class="pv-x" aria-label="Close" @click="$emit('close')"><X :size="18" /></button>
      </div>

      <!-- The big subtitle: what the robot just said -->
      <div class="pv-subtitle-wrap">
        <p v-if="store.subtitle" class="pv-subtitle">{{ store.subtitle }}</p>
        <p v-else class="pv-subtitle pv-subtitle--idle">
          {{ store.lastMode === 'silent' ? '(the robot holds the floor for you)' : 'Waiting for a cue…' }}
        </p>
      </div>

      <div class="pv-bottom">
        <!-- camera thumbnail -->
        <div class="pv-cam">
          <img v-if="frameSrc" :src="frameSrc" class="pv-cam-img" alt="Robot camera" />
          <div v-else class="pv-cam-idle"><VideoOff :size="20" /></div>
        </div>

        <!-- armed keywords -->
        <div class="pv-armed">
          <span class="pv-armed-label">Chimes in on</span>
          <template v-if="store.status.armed_keywords?.length">
            <span v-for="k in store.status.armed_keywords" :key="k" class="pv-kw">“{{ k }}”</span>
          </template>
          <span v-else class="pv-armed-none">— all used —</span>
        </div>

        <span class="pv-spacer" />

        <!-- advance a manual beat -->
        <button class="pv-btn pv-btn--next" :disabled="store.busy" @click="store.next()">
          Next beat →
          <span class="pv-progress" v-if="store.status.manual_total">
            {{ store.status.manual_pos }}/{{ store.status.manual_total }}
          </span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { Presentation, VideoOff, X } from 'lucide-vue-next'
import { usePresentationStore } from '../stores/presentationStore'
import ScenarioBuilder from './ScenarioBuilder.vue'

defineEmits<{ close: [] }>()

const store = usePresentationStore()
const BRAIN_URL = import.meta.env.VITE_BRAIN_URL ?? import.meta.env.VITE_ORCHESTRATOR_URL ?? 'http://localhost:8020'

const yamlText = ref('')
const rawMode = ref(false)
const builder = ref<InstanceType<typeof ScenarioBuilder> | null>(null)
const frameSrc = ref('')
let statusTimer: ReturnType<typeof setInterval> | null = null
let camLoop = 0

async function start() {
  if (await store.start(yamlText.value)) startCamera()
}

async function startFromScenario(scenario: object) {
  const ok = await store.startScenario(scenario)
  if (ok) startCamera()
  else builder.value?.setError(store.error || 'Could not start.')
}

async function stop() {
  await store.stop()
  camLoop++            // halt the camera loop
  frameSrc.value = ''
}

// U206: the camera runs the same one-frame-per-request loop as VideoPanel
// (U195) so the presenter view can't fall behind live either.
async function startCamera() {
  const mine = ++camLoop
  while (mine === camLoop && store.status.active) {
    const t0 = performance.now()
    try {
      const r = await fetch(`${BRAIN_URL}/robot/camera/frame.jpg`, { cache: 'no-store' })
      if (r.ok) {
        const blob = await r.blob()
        if (mine !== camLoop) break
        const url = URL.createObjectURL(blob)
        const prev = frameSrc.value
        frameSrc.value = url
        if (prev.startsWith('blob:')) URL.revokeObjectURL(prev)
      }
    } catch { /* robot down — keep the last frame */ }
    const wait = 200 - (performance.now() - t0)
    if (wait > 0) await new Promise(r => setTimeout(r, wait))
  }
}

onMounted(() => {
  store.fetchStatus().then(() => { if (store.status.active) startCamera() })
  statusTimer = setInterval(() => { if (store.status.active) store.fetchStatus() }, 3000)
})
onUnmounted(() => {
  if (statusTimer) clearInterval(statusTimer)
  camLoop++
  if (frameSrc.value.startsWith('blob:')) URL.revokeObjectURL(frameSrc.value)
})
</script>

<style scoped>
.presenter {
  position: fixed; inset: 0; z-index: 60;
  background: var(--bg); color: var(--text);
  display: flex; flex-direction: column;
}
.pv-setup { max-width: 640px; margin: auto; width: 100%; padding: 1.5rem; }
.pv-setup-head { display: flex; align-items: center; justify-content: space-between; }
.pv-setup-head h2 { margin: 0; font-size: 1.15rem; }
.pv-mode-toggle { display: flex; gap: 2px; margin-left: auto; margin-right: 0.6rem; }
.pv-tab { background: var(--surface); border: 1px solid var(--border-strong); color: var(--text-muted); padding: 0.25rem 0.7rem; font-size: 0.78rem; cursor: pointer; }
.pv-tab:first-child { border-radius: var(--radius-md) 0 0 var(--radius-md); }
.pv-tab:last-child { border-radius: 0 var(--radius-md) var(--radius-md) 0; border-left: none; }
.pv-tab--on { background: var(--accent); color: var(--accent-contrast, #fff); border-color: var(--accent); }
.pv-hint { color: var(--text-muted); font-size: 0.85rem; line-height: 1.5; }
.pv-yaml {
  width: 100%; min-height: 220px; margin-top: 0.5rem; resize: vertical;
  font-family: ui-monospace, monospace; font-size: 0.8rem; line-height: 1.5;
  background: var(--surface); color: var(--text);
  border: 1px solid var(--border-strong); border-radius: var(--radius-md); padding: 0.6rem;
}
.pv-setup-actions { display: flex; align-items: center; gap: 0.8rem; margin-top: 0.8rem; }
.pv-err { color: var(--danger, #e5484d); font-size: 0.8rem; }

.pv-stage { display: flex; flex-direction: column; height: 100%; }
.pv-top {
  display: flex; align-items: center; gap: 0.8rem;
  padding: 0.7rem 1rem; border-bottom: 1px solid var(--border-strong);
  font-size: 0.82rem;
}
.pv-title { font-weight: 600; }
.pv-slide { display: inline-flex; align-items: center; gap: 0.3rem; color: var(--text-muted); }
.pv-ppt { font-size: 0.72rem; padding: 0.15rem 0.5rem; border-radius: 999px; border: 1px solid var(--border-strong); }
.pv-ppt--on { color: var(--ok-text, #2f9e6e); border-color: currentColor; }
.pv-ppt--off { color: var(--text-faint); }
.pv-spacer { flex: 1; }

.pv-subtitle-wrap { flex: 1; display: flex; align-items: center; justify-content: center; padding: 2rem; }
.pv-subtitle {
  margin: 0; text-align: center; max-width: 20ch; font-size: clamp(1.8rem, 5vw, 3.4rem);
  line-height: 1.25; font-weight: 600; max-width: 24ch;
}
.pv-subtitle--idle { color: var(--text-faint); font-weight: 400; font-size: clamp(1rem, 3vw, 1.6rem); }

.pv-bottom {
  display: flex; align-items: center; gap: 1rem;
  padding: 0.8rem 1rem; border-top: 1px solid var(--border-strong);
}
.pv-cam { width: 96px; height: 54px; border-radius: var(--radius-md); overflow: hidden; background: var(--surface); flex-shrink: 0; }
.pv-cam-img { width: 100%; height: 100%; object-fit: cover; }
.pv-cam-idle { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; color: var(--text-faint); }
.pv-armed { display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap; font-size: 0.8rem; }
.pv-armed-label { color: var(--text-faint); }
.pv-kw { color: var(--accent); }
.pv-armed-none { color: var(--text-faint); }

.pv-btn {
  border: 1px solid var(--border-strong); border-radius: var(--radius-md);
  background: transparent; color: var(--text); cursor: pointer;
  padding: 0.5rem 1rem; font-size: 0.85rem;
}
.pv-btn:disabled { opacity: 0.6; cursor: default; }
.pv-btn--go, .pv-btn--next { background: var(--accent); color: var(--accent-contrast, #fff); border-color: var(--accent); font-weight: 600; }
.pv-btn--next { font-size: 1rem; padding: 0.6rem 1.4rem; }
.pv-btn--stop { color: var(--danger, #e5484d); border-color: var(--danger, #e5484d); }
.pv-progress { margin-left: 0.5rem; opacity: 0.8; font-size: 0.8rem; }
.pv-x { background: none; border: none; color: var(--text-muted); cursor: pointer; padding: 0.2rem; }
.pv-x:hover { color: var(--text); }
</style>
