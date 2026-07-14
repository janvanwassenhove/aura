<template>
  <section class="panel video-panel">
    <div class="flex items-center justify-between mb-2">
      <h2 class="panel-title mb-0">Robot Camera</h2>
      <span v-if="state === 'live'" class="live-badge"><Video :size="11" /> LIVE</span>
    </div>

    <div class="video-frame">
      <!-- MJPEG stream: the <img> renders continuous frames natively -->
      <img
        v-show="state === 'live'"
        :key="streamKey"
        :src="streamUrl"
        alt="Robot camera"
        class="video-img"
        @load="state = 'live'"
        @error="onStreamError"
      />
      <div v-if="state !== 'live'" class="video-placeholder">
        <VideoOff :size="28" class="mb-2" />
        <p v-if="state === 'connecting'">Connecting to the robot camera…</p>
        <template v-else>
          <p>No camera feed.</p>
          <p class="hint">Is the robot on? The camera starts ~10 s after the robot boots. Retrying…</p>
        </template>
      </div>

      <!-- Recognition overlay -->
      <div v-if="recognized" class="recognized-overlay">
        <UserCheck v-if="recognized.known" :size="13" />
        <UserX v-else :size="13" />
        {{ recognized.known ? recognized.display_name : 'Unknown face' }}
        <span v-if="recognized.known" class="confidence">{{ Math.round(recognized.confidence * 100) }}%</span>
      </div>
    </div>

    <!-- Recognition / enrollment -->
    <div v-if="recognitionEnabled === false" class="hint mt-2">
      Face recognition is off — open <strong>Knowledge</strong> (brain icon, top right)
      and secure it with a passphrase to enable.
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
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ScanFace, UserCheck, UserX, Video, VideoOff } from 'lucide-vue-next'
import { useRobotStore } from '../stores/robotStore'

const BRAIN_URL = import.meta.env.VITE_BRAIN_URL ?? import.meta.env.VITE_ORCHESTRATOR_URL ?? 'http://localhost:8000'

const robotStore = useRobotStore()
const recognized = computed(() => robotStore.lastRecognized)

const state = ref<'connecting' | 'live' | 'off'>('connecting')
const streamKey = ref(0)
const streamUrl = computed(() => `${BRAIN_URL}/robot/camera/stream?r=${streamKey.value}`)
const recognitionEnabled = ref<boolean | null>(null)
const enrollId = ref('')
const enrolling = ref(false)
const enrollMessage = ref('')
const enrollOk = ref(false)

let retryTimer: ReturnType<typeof setTimeout> | null = null

function onStreamError() {
  state.value = 'off'
  if (retryTimer) clearTimeout(retryTimer)
  retryTimer = setTimeout(() => {
    state.value = 'connecting'
    streamKey.value++ // remount the <img> → reconnect the stream
  }, 4000)
}

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

onMounted(fetchRecognitionStatus)
onUnmounted(() => { if (retryTimer) clearTimeout(retryTimer) })
</script>

<style scoped>
.video-panel { margin-top: 1rem; }
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
.enroll-row { display: flex; gap: 0.4rem; }
.enroll-btn { display: inline-flex; align-items: center; gap: 0.3rem; font-size: 0.78rem; padding: 0.3rem 0.7rem; white-space: nowrap; }
.enroll-msg { font-size: 0.72rem; margin: 0.3rem 0 0; }
.enroll-msg--ok { color: var(--ok); }
.enroll-msg--err { color: var(--danger-text); }
.mt-2 { margin-top: 0.5rem; }
.mb-2 { margin-bottom: 0.5rem; }
.mb-0 { margin-bottom: 0; }
</style>
