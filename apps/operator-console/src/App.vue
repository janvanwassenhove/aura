<template>
  <div class="app-layout">
    <TitleBar
      :ws-status="wsStatus"
      @open-knowledge="layoutStore.openRight('brain')"
      @open-settings="showSettings = true"
      @open-capabilities="showCapabilities = true"
      @toggle-left="layoutStore.showLeft = !layoutStore.showLeft"
      @toggle-right="layoutStore.showRight = !layoutStore.showRight"
      @toggle-bottom="layoutStore.showBottom = !layoutStore.showBottom"
    />

    <!-- Approval overlay (rendered on top of everything) -->
    <ApprovalPanel />

    <!-- U34: full-screen onboarding on first run -->
    <SetupWizard v-if="showWizard" @done="showWizard = false" />

    <!-- Settings modal (LLM + Connections + Appearance tabs) -->
    <SettingsPanel v-if="showSettings" @close="showSettings = false" />

    <!-- Knowledge transparency modal (ADR-008 §8: inspect/edit/erase profiles) -->
    <KnowledgePanel v-if="showKnowledge" @close="showKnowledge = false" />

    <!-- Capabilities / permissions center (U40) -->
    <CapabilitiesPanel v-if="showCapabilities" @close="showCapabilities = false" />

    <!-- U76: VS Code-like workspace — toggleable, resizable docks -->
    <main class="workspace">
      <div v-if="layoutStore.showLeft" class="ws-left" :style="{ width: layoutStore.leftWidth + 'px' }">
        <RobotPanel />
        <VideoPanel />
      </div>
      <div v-if="layoutStore.showLeft" class="ws-splitter" title="Drag to resize"
           @pointerdown="startDrag('left', $event)" />
      <div class="ws-center">
        <div class="ws-center-main"><ConversationPanel /></div>
        <div v-if="layoutStore.showBottom" class="ws-hsplitter" title="Drag to resize"
             @pointerdown="startVDrag($event)" />
        <div v-if="layoutStore.showBottom" class="ws-bottom"
             :style="{ height: layoutStore.bottomHeight + 'px' }">
          <EventLogPanel />
        </div>
      </div>
      <div v-if="layoutStore.showRight" class="ws-splitter" title="Drag to resize"
           @pointerdown="startDrag('right', $event)" />
      <aside v-if="layoutStore.showRight" class="ws-right" :style="{ width: layoutStore.rightWidth + 'px' }">
        <div class="ws-right-body">
          <BrainPanel docked @open-knowledge="showKnowledge = true" />
        </div>
      </aside>
    </main>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import TitleBar from './components/TitleBar.vue'
import RobotPanel from './components/RobotPanel.vue'
import VideoPanel from './components/VideoPanel.vue'
import ConversationPanel from './components/ConversationPanel.vue'
import EventLogPanel from './components/EventLogPanel.vue'
import ApprovalPanel from './components/ApprovalPanel.vue'
import SettingsPanel from './components/SettingsPanel.vue'
import BrainPanel from './components/BrainPanel.vue'
import KnowledgePanel from './components/KnowledgePanel.vue'
import CapabilitiesPanel from './components/CapabilitiesPanel.vue'
import SetupWizard from './components/SetupWizard.vue'
import { useEventBusWs } from './composables/useEventBusWs'
import { useLayoutStore } from './stores/layoutStore'
import { useNavStore } from './stores/navStore'
import { useSetupStore } from './stores/setupStore'
import { useThemeStore } from './stores/themeStore'

const { wsStatus, connect } = useEventBusWs()
const showSettings = ref(false)
const showKnowledge = ref(false)
const layoutStore = useLayoutStore()

// U76: draggable splitters (VS Code-style resize).
function startVDrag(ev: PointerEvent): void {
  ev.preventDefault()
  const startY = ev.clientY
  const startH = layoutStore.bottomHeight
  const move = (e: PointerEvent) => {
    layoutStore.bottomHeight = Math.max(110, Math.min(520, startH - (e.clientY - startY)))
  }
  const up = () => {
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', up)
  }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', up)
}

function startDrag(side: 'left' | 'right', ev: PointerEvent): void {
  ev.preventDefault()
  const startX = ev.clientX
  const startW = side === 'left' ? layoutStore.leftWidth : layoutStore.rightWidth
  const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v))
  const move = (e: PointerEvent) => {
    const dx = e.clientX - startX
    if (side === 'left') layoutStore.leftWidth = clamp(startW + dx, 220, 560)
    else layoutStore.rightWidth = clamp(startW - dx, 280, 900)
  }
  const up = () => {
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', up)
  }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', up)
}
const showCapabilities = ref(false)
const showWizard = ref(false)
const themeStore = useThemeStore()
const setupStore = useSetupStore()
const navStore = useNavStore()

// U68: [[wikilink]] navigation — links open the right dock / settings.
watch(() => navStore.knowledgeRequest, (r) => { if (r) layoutStore.openRight('brain') })
watch(() => navStore.skillsRequest, (r) => { if (r) showSettings.value = true })

onMounted(async () => {
  themeStore.apply()
  connect()
  // U34: first-run onboarding — only when the brain is reachable, setup was
  // never completed AND the install genuinely looks fresh. An existing,
  // clearly-configured install (keys/people/encryption present but no
  // SETUP_DONE marker, e.g. set up before the wizard existed) must never get
  // hijacked by a full-screen wizard. Brain offline → normal dashboard.
  await setupStore.fetchStatus()
  const st = setupStore.status
  if (st && !st.setup_done) {
    const looksConfigured =
      st.openai_key_set || st.openrouter_key_set || st.gemini_key_set ||
      st.people_count > 0 || st.encrypted
    if (looksConfigured) {
      // Backfill the marker so the question never comes up again.
      setupStore.saveConfig({ setup_done: true })
    } else {
      showWizard.value = true
    }
  }
})
</script>

<style>
@import "tailwindcss";
@import "./styles/tokens.css";

:root {
  font-family: Inter, system-ui, sans-serif;
}

body {
  background: var(--bg);
  color: var(--text);
}

.app-layout { display: flex; flex-direction: column; height: 100vh; background: var(--bg); color: var(--text); }

.workspace {
  display: flex;
  padding: 0.8rem;
  gap: 0;
  flex: 1;
  min-height: 0;
}
.ws-left { display: flex; flex-direction: column; min-height: 0; overflow-y: auto; flex-shrink: 0; }
.ws-center { flex: 1; min-width: 20rem; min-height: 0; display: flex; flex-direction: column; }
.ws-center-main { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.ws-center-main > * { flex: 1; min-height: 0; }
.ws-bottom { flex-shrink: 0; min-height: 0; display: flex; flex-direction: column; }
.ws-bottom > * { flex: 1; min-height: 0; }
.ws-hsplitter { height: 9px; cursor: row-resize; flex-shrink: 0; position: relative; }
.ws-hsplitter::after { content: ''; position: absolute; inset: 3px 0; border-radius: 2px; transition: background 0.12s; }
.ws-hsplitter:hover::after { background: var(--accent); opacity: 0.55; }
/* U77: left-column panels must not shrink-clip — the column scrolls instead. */
.ws-left > * { flex-shrink: 0; }
.ws-right {
  flex-shrink: 0; min-height: 0; display: flex; flex-direction: column;
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg);
  overflow: hidden;
}
.ws-splitter {
  width: 9px; cursor: col-resize; flex-shrink: 0; position: relative;
}
.ws-splitter::after {
  content: ''; position: absolute; inset: 0 3px;
  border-radius: 2px; transition: background 0.12s;
}
.ws-splitter:hover::after { background: var(--accent); opacity: 0.55; }
.ws-tabs { display: flex; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.ws-tab {
  padding: 0.45rem 0.9rem; background: none; border: none; cursor: pointer;
  color: var(--text-faint); font-size: 0.78rem; border-bottom: 2px solid transparent;
}
.ws-tab--active { color: var(--text); border-bottom-color: var(--accent); }
.ws-right-body { flex: 1; min-height: 0; display: flex; flex-direction: column; overflow: hidden; }
.ws-right-body > * { flex: 1; min-height: 0; }

.panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 1.15rem 1.15rem 1rem;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.panel-title {
  font-size: 0.9rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
  margin-bottom: 0.9rem;
}

.status-row { display: flex; justify-content: space-between; align-items: center; gap: 0.75rem; padding: 0.4rem 0; }
.label { font-size: 0.8rem; color: var(--text-muted); }
.value { font-size: 0.85rem; }
.section-label { font-size: 0.72rem; font-weight: 600; letter-spacing: 0.04em; color: var(--text-faint); text-transform: uppercase; margin: 0.3rem 0 0.55rem; }

.badge { font-size: 0.7rem; padding: 0.15rem 0.5rem; border-radius: 999px; text-transform: uppercase; font-weight: 600; }
.badge-blue { background: var(--accent); color: var(--on-accent); }
.badge-green { background: var(--ok-bg); color: var(--ok-text); }
.badge-purple { background: var(--info-bg); color: var(--info-text); }
.badge-red { background: var(--danger-bg); color: var(--danger-text); }
.badge-gray { background: var(--surface-hover); color: var(--text-muted); }

.indicator { font-size: 0.8rem; display: inline-flex; align-items: center; gap: 0.3rem; }
.indicator-active { color: var(--ok); }
.indicator-idle { color: var(--text-faint); }

.transcript-box { margin-top: 0.5rem; padding: 0.5rem; background: var(--surface-3); border-radius: var(--radius-sm); font-size: 0.8rem; color: var(--accent-soft); }

.motion-log { list-style: none; padding: 0; font-size: 0.8rem; }
.motion-entry { display: flex; align-items: center; gap: 0.4rem; padding: 0.2rem 0; }
.status-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.dot-started { background: var(--warn); }
.dot-completed { background: var(--ok); }
.dot-failed { background: var(--danger); }
.motion-name { flex: 1; }
.motion-time { color: var(--text-faint); }

.conversation-scroll { overflow-y: auto; flex: 1; }
.turn { padding: 0.5rem; border-radius: var(--radius); }
.turn-user { background: var(--surface-3); border-left: 3px solid var(--accent); }
.turn-assistant { background: var(--surface-2); border-left: 3px solid var(--ok); }
.turn-header { display: flex; justify-content: space-between; margin-bottom: 0.2rem; }
.turn-role { font-size: 0.7rem; font-weight: 600; text-transform: uppercase; color: var(--text-muted); }
.turn-time { font-size: 0.7rem; color: var(--text-faint); }
.turn-text { font-size: 0.85rem; }

.tool-badge { margin-top: 0.3rem; font-size: 0.7rem; padding: 0.1rem 0.4rem; border-radius: var(--radius-sm); display: inline-flex; align-items: center; gap: 0.25rem; }
.tool-pending { background: var(--warn-bg); color: var(--warn-text); }
.tool-approved { background: var(--ok-bg); color: var(--ok-text); }
.tool-denied { background: var(--danger-bg); color: var(--danger-text); }
.tool-succeeded { background: var(--ok-bg-deep); color: var(--ok-text); }
.tool-failed { background: var(--danger-bg); color: var(--danger-text); }

.input-row { display: flex; gap: 0.5rem; align-items: center; padding-top: 0.25rem; }
.chat-input {
  flex: 1; padding: 0.4rem 0.75rem;
  background: var(--surface-3); border: 1px solid var(--border); border-radius: var(--radius);
  color: var(--text); font-size: 0.85rem; outline: none;
}
.chat-input:focus { border-color: var(--accent); }
.chat-input:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-primary { padding: 0.4rem 1rem; border-radius: var(--radius); background: var(--accent); color: var(--on-accent); font-size: 0.85rem; cursor: pointer; border: none; }
.btn-primary:hover:not(:disabled) { background: var(--accent-hover); }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-ghost { background: transparent; border: none; color: var(--text-faint); cursor: pointer; padding: 0.25rem 0.5rem; }
.btn-ghost:hover { color: var(--text-muted); }

.filter-input { width: 100%; padding: 0.3rem 0.5rem; background: var(--surface-3); border: 1px solid var(--border); border-radius: var(--radius-sm); color: var(--text); font-size: 0.8rem; outline: none; }
.filter-input:focus { border-color: var(--accent); }

.event-list { list-style: none; padding: 0; }
.event-row { display: flex; align-items: center; gap: 0.4rem; padding: 0.2rem 0.25rem; border-radius: var(--radius-sm); font-size: 0.75rem; }
.event-row:hover { background: var(--surface-3); }
.event-type { flex: 1; color: var(--accent-soft); font-family: monospace; }
.event-session { color: var(--text-faint); font-family: monospace; font-size: 0.7rem; }
.event-time { color: var(--text-faint); white-space: nowrap; }

.approval-overlay { position: fixed; inset: 0; background: var(--overlay); display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 1rem; z-index: 50; }
.approval-modal { background: var(--surface); border: 1px solid var(--border-strong); border-radius: var(--radius-xl); padding: 1.5rem; width: 400px; max-width: 90vw; box-shadow: var(--shadow-modal); }
.approval-header { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 1rem; }
.approval-icon { color: var(--warn); display: flex; }
.approval-header h3 { font-size: 1rem; font-weight: 600; }
.approval-field { display: flex; justify-content: space-between; padding: 0.3rem 0; border-bottom: 1px solid var(--border); }
.field-label { font-size: 0.75rem; color: var(--text-muted); }
.field-value { font-size: 0.85rem; text-align: right; max-width: 60%; word-break: break-all; }
.approval-countdown { font-size: 0.75rem; color: var(--warn); margin-top: 0.75rem; }
.approval-remember { display: flex; align-items: center; gap: 0.4rem; font-size: 0.75rem; color: var(--text-muted); margin-top: 0.6rem; cursor: pointer; }
.approval-actions { display: flex; justify-content: flex-end; gap: 0.75rem; margin-top: 1rem; }
.btn-deny { padding: 0.4rem 1.25rem; border-radius: var(--radius); background: var(--danger-bg-hover); color: var(--danger-text); border: none; cursor: pointer; font-size: 0.85rem; }
.btn-deny:hover { background: var(--danger); color: #fff; }
.btn-grant { padding: 0.4rem 1.25rem; border-radius: var(--radius); background: var(--ok-bg); color: var(--ok-text); border: none; cursor: pointer; font-size: 0.85rem; }
.btn-grant:hover { background: var(--ok); color: #fff; }

.mt-3 { margin-top: 1.1rem; }
.mb-2 { margin-bottom: 0.5rem; }
.mb-3 { margin-bottom: 0.75rem; }
.flex { display: flex; }
.flex-col { flex-direction: column; }
.flex-1 { flex: 1; }
.items-center { align-items: center; }
.justify-between { justify-content: space-between; }
.space-y-2 > * + * { margin-top: 0.5rem; }
.space-y-1 > * + * { margin-top: 0.25rem; }
.overflow-y-auto { overflow-y: auto; }
.h-full { height: 100%; }
.text-gray-400 { color: var(--text-faint); }
.text-sm { font-size: 0.875rem; }
.p-2 { padding: 0.5rem; }
.animate-pulse { animation: pulse 1.5s cubic-bezier(0.4,0,0.6,1) infinite; }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: .5; } }
</style>
