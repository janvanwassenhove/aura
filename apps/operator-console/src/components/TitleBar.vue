<template>
  <header class="titlebar">
    <div class="titlebar-left">
      <Bot :size="17" class="titlebar-logo" />
      <span class="titlebar-name">{{ prefsStore.assistantName }}</span>
      <span class="titlebar-sep" />
      <!-- U151: label each status by its subject — "Connected · offline" side
           by side read as contradictory. App = console↔brain; Robot = the Pi. -->
      <span class="titlebar-status" :title="`Console ↔ brain event stream: ${wsStatus}`">
        <span :class="['status-dot', `status-dot--${wsStatus}`]" />
        App: {{ wsLabel }}
      </span>
      <span class="titlebar-status" :title="`Robot connection: ${robotStore.mode}`">
        <Cpu :size="12" :class="['status-icon', robotStore.connected ? 'status-icon--ok' : 'status-icon--off']" />
        Robot: {{ robotStore.connected ? robotStore.mode : 'offline' }}
      </span>
    </div>

    <div class="titlebar-drag" />

    <div class="titlebar-right">
      <button class="titlebar-btn" title="Toggle left panel" aria-label="Toggle left panel" @click="$emit('toggle-left')">
        <PanelLeft :size="15" />
      </button>
      <button class="titlebar-btn" title="Toggle bottom panel (Events)" aria-label="Toggle bottom panel" @click="$emit('toggle-bottom')">
        <PanelBottom :size="15" />
      </button>
      <button class="titlebar-btn" title="Brain panel (people, skills, graph)" aria-label="Toggle right panel" @click="$emit('toggle-right')">
        <PanelRight :size="15" />
      </button>
      <button v-if="isElectron" class="titlebar-btn" :title="restarting ? 'Restarting brain…' : 'Restart brain (load new code/settings)'" aria-label="Restart brain" :disabled="restarting" @click="restartBrain">
        <RotateCw :size="15" :class="restarting ? 'spin' : ''" />
      </button>
      <button class="titlebar-btn" title="Capabilities & permissions" aria-label="Capabilities and permissions" @click="$emit('open-capabilities')">
        <ShieldCheck :size="16" />
      </button>
      <button class="titlebar-btn" title="About AURA" aria-label="About" @click="$emit('open-about')">
        <Info :size="16" />
      </button>
      <button class="titlebar-btn" title="Settings" aria-label="Settings" @click="$emit('open-settings')">
        <Settings :size="16" />
      </button>
      <template v-if="isElectron">
        <span class="titlebar-sep" />
        <button class="titlebar-btn win-btn" title="Minimize" aria-label="Minimize window" @click="winControl('minimize')">
          <Minus :size="15" />
        </button>
        <button class="titlebar-btn win-btn" title="Maximize" aria-label="Maximize window" @click="winControl('toggleMaximize')">
          <Square :size="12" />
        </button>
        <button class="titlebar-btn win-btn win-btn--close" title="Close" aria-label="Close window" @click="winControl('close')">
          <X :size="15" />
        </button>
      </template>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onMounted } from 'vue'
import { Bot, Cpu, Info, Minus, RotateCw, Settings, ShieldCheck, Square, X, PanelBottom, PanelLeft, PanelRight } from 'lucide-vue-next'
import { useRobotStore } from '../stores/robotStore'
import { usePrefsStore } from '../stores/prefsStore'

const props = defineProps<{ wsStatus: 'connecting' | 'open' | 'closed' }>()
defineEmits<{
  'open-settings': []; 'open-capabilities': []; 'open-about': []
  'toggle-left': []; 'toggle-right': []; 'toggle-bottom': []
}>()

const restarting = ref(false)
async function restartBrain() {
  if (restarting.value || !auraWindow?.restartBrain) return
  restarting.value = true
  try {
    const r = await auraWindow.restartBrain()
    if (r?.ok) location.reload()  // reconnect the console to the fresh brain
    else alert('Brain restart failed: ' + (r?.error ?? 'unknown'))
  } finally { restarting.value = false }
}

const robotStore = useRobotStore()
const prefsStore = usePrefsStore()

onMounted(prefsStore.fetchPrefs)

const wsLabel = computed(() => {
  if (props.wsStatus === 'open') return 'Connected'
  if (props.wsStatus === 'connecting') return 'Connecting…'
  return 'Reconnecting…'
})

// Injected by the Electron preload; absent when running in a plain browser.
const auraWindow = (window as any).aura
const isElectron = Boolean(auraWindow?.isElectron)

function winControl(action: 'minimize' | 'toggleMaximize' | 'close') {
  auraWindow?.[action]?.()
}
</script>

<style scoped>
.titlebar {
  display: flex; align-items: stretch;
  height: 38px; flex-shrink: 0;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  user-select: none;
  -webkit-app-region: drag; /* whole bar drags the window… */
}
.titlebar-left {
  display: flex; align-items: center; gap: 0.5rem;
  padding: 0 0.9rem;
}
.titlebar-logo { color: var(--accent-soft); }
.titlebar-name { font-weight: 600; font-size: 0.85rem; letter-spacing: 0.03em; }
.titlebar-sep { width: 1px; height: 16px; background: var(--border); margin: 0 0.35rem; align-self: center; }

.titlebar-status {
  display: flex; align-items: center; gap: 0.3rem;
  font-size: 0.72rem; color: var(--text-muted);
}
.status-icon { color: var(--text-faint); }
.status-icon--ok { color: var(--ok-text, #2f9e6e); }
.status-icon--off { color: var(--danger-text, #e5484d); }
.status-dot { width: 8px; height: 8px; border-radius: 50%; }
.status-dot--open { background: var(--ok); }
.status-dot--connecting { background: var(--warn); }
.status-dot--closed { background: var(--danger); }

.titlebar-drag { flex: 1; }

.titlebar-right {
  display: flex; align-items: center;
  -webkit-app-region: no-drag; /* …except the buttons */
}
.titlebar-btn {
  display: flex; align-items: center; justify-content: center;
  width: 40px; height: 38px;
  background: none; border: none; cursor: pointer;
  color: var(--text-muted);
}
.titlebar-btn:hover { color: var(--text); background: var(--surface-hover); }
.win-btn:hover { background: var(--surface-hover); }
.win-btn--close:hover { background: var(--danger); color: #fff; }

.spin { animation: tb-spin 0.9s linear infinite; }
@keyframes tb-spin { to { transform: rotate(360deg); } }
</style>
