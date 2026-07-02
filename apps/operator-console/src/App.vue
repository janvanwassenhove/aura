<template>
  <div class="app-layout">
    <!-- Header -->
    <header class="app-header">
      <span class="app-title">AURA Operator Console</span>
      <div class="header-status">
        <span :class="['ws-indicator', `ws-${wsStatus}`]" />
        <span class="ws-label">{{ wsStatusLabel }}</span>
        <button class="btn-gear" title="Knowledge" @click="showKnowledge = true">🧠</button>
        <button class="btn-gear" title="Settings" @click="showSettings = true">⚙</button>
      </div>
    </header>

    <!-- Approval overlay (rendered on top of everything) -->
    <ApprovalPanel />

    <!-- Settings modal (LLM + Connections tabs) -->
    <SettingsPanel v-if="showSettings" @close="showSettings = false" />

    <!-- Knowledge transparency modal (ADR-008 §8: inspect/edit/erase profiles) -->
    <KnowledgePanel v-if="showKnowledge" @close="showKnowledge = false" />

    <!-- Main grid: 3 columns -->
    <main class="app-grid">
      <RobotPanel />
      <ConversationPanel />
      <EventLogPanel />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import RobotPanel from './components/RobotPanel.vue'
import ConversationPanel from './components/ConversationPanel.vue'
import EventLogPanel from './components/EventLogPanel.vue'
import ApprovalPanel from './components/ApprovalPanel.vue'
import SettingsPanel from './components/SettingsPanel.vue'
import KnowledgePanel from './components/KnowledgePanel.vue'
import { useEventBusWs } from './composables/useEventBusWs'

const { wsStatus, connect } = useEventBusWs()
const showSettings = ref(false)
const showKnowledge = ref(false)

const wsStatusLabel = computed(() => {
  if (wsStatus.value === 'open') return 'Connected'
  if (wsStatus.value === 'connecting') return 'Connecting…'
  return 'Reconnecting…'
})

onMounted(connect)
</script>

<style>
@import "tailwindcss";

:root {
  font-family: Inter, system-ui, sans-serif;
  background: #0f172a;
  color: #e2e8f0;
}

.app-layout { display: flex; flex-direction: column; height: 100vh; }

.app-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0.75rem 1.5rem;
  background: #1e293b;
  border-bottom: 1px solid #334155;
}

.app-title { font-size: 1.1rem; font-weight: 600; }
.header-status { display: flex; align-items: center; gap: 0.5rem; }
.ws-indicator { width: 10px; height: 10px; border-radius: 50%; }
.ws-open { background: #22c55e; }
.ws-connecting { background: #f59e0b; }
.ws-closed { background: #ef4444; }
.ws-label { font-size: 0.8rem; color: #94a3b8; }
.btn-gear {
  background: none; border: 1px solid #334155; border-radius: 0.25rem;
  color: #94a3b8; cursor: pointer; font-size: 1rem; padding: 0.15rem 0.45rem;
  line-height: 1;
}
.btn-gear:hover { color: #e2e8f0; border-color: #475569; }

.app-grid {
  display: grid;
  grid-template-columns: 280px 1fr 320px;
  gap: 1rem;
  padding: 1rem;
  flex: 1;
  min-height: 0;
}

.panel {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 0.5rem;
  padding: 1rem;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.panel-title {
  font-size: 0.9rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #94a3b8;
  margin-bottom: 0.75rem;
}

.status-row { display: flex; justify-content: space-between; align-items: center; padding: 0.25rem 0; }
.label { font-size: 0.8rem; color: #94a3b8; }
.value { font-size: 0.85rem; }
.section-label { font-size: 0.75rem; color: #64748b; text-transform: uppercase; margin-bottom: 0.4rem; }

.badge { font-size: 0.7rem; padding: 0.15rem 0.5rem; border-radius: 999px; text-transform: uppercase; font-weight: 600; }
.badge-blue { background: #1d4ed8; color: #bfdbfe; }
.badge-green { background: #15803d; color: #bbf7d0; }
.badge-purple { background: #7e22ce; color: #e9d5ff; }
.badge-red { background: #b91c1c; color: #fecaca; }
.badge-gray { background: #374151; color: #d1d5db; }

.indicator { font-size: 0.8rem; }
.indicator-active { color: #4ade80; }
.indicator-idle { color: #6b7280; }

.transcript-box { margin-top: 0.5rem; padding: 0.5rem; background: #0f172a; border-radius: 0.25rem; font-size: 0.8rem; color: #a5f3fc; }

.motion-log { list-style: none; padding: 0; font-size: 0.8rem; }
.motion-entry { display: flex; align-items: center; gap: 0.4rem; padding: 0.2rem 0; }
.status-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.dot-started { background: #f59e0b; }
.dot-completed { background: #22c55e; }
.dot-failed { background: #ef4444; }
.motion-name { flex: 1; }
.motion-time { color: #64748b; }

.conversation-scroll { overflow-y: auto; flex: 1; }
.turn { padding: 0.5rem; border-radius: 0.375rem; }
.turn-user { background: #0f172a; border-left: 3px solid #3b82f6; }
.turn-assistant { background: #172033; border-left: 3px solid #22c55e; }
.turn-header { display: flex; justify-content: space-between; margin-bottom: 0.2rem; }
.turn-role { font-size: 0.7rem; font-weight: 600; text-transform: uppercase; color: #94a3b8; }
.turn-time { font-size: 0.7rem; color: #475569; }
.turn-text { font-size: 0.85rem; }

.tool-badge { margin-top: 0.3rem; font-size: 0.7rem; padding: 0.1rem 0.4rem; border-radius: 0.25rem; display: inline-block; }
.tool-pending { background: #78350f; color: #fde68a; }
.tool-approved { background: #14532d; color: #86efac; }
.tool-denied { background: #450a0a; color: #fca5a5; }
.tool-succeeded { background: #052e16; color: #6ee7b7; }
.tool-failed { background: #450a0a; color: #fca5a5; }

.input-row { display: flex; gap: 0.5rem; }
.chat-input {
  flex: 1; padding: 0.4rem 0.75rem;
  background: #0f172a; border: 1px solid #334155; border-radius: 0.375rem;
  color: #e2e8f0; font-size: 0.85rem; outline: none;
}
.chat-input:focus { border-color: #3b82f6; }
.chat-input:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-primary { padding: 0.4rem 1rem; border-radius: 0.375rem; background: #2563eb; color: white; font-size: 0.85rem; cursor: pointer; border: none; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-ghost { background: transparent; border: none; color: #64748b; cursor: pointer; padding: 0.25rem 0.5rem; }
.btn-ghost:hover { color: #94a3b8; }

.filter-input { width: 100%; padding: 0.3rem 0.5rem; background: #0f172a; border: 1px solid #334155; border-radius: 0.25rem; color: #e2e8f0; font-size: 0.8rem; outline: none; }
.filter-input:focus { border-color: #3b82f6; }

.event-list { list-style: none; padding: 0; }
.event-row { display: flex; align-items: center; gap: 0.4rem; padding: 0.2rem 0.25rem; border-radius: 0.2rem; font-size: 0.75rem; }
.event-row:hover { background: #0f172a; }
.event-type { flex: 1; color: #93c5fd; font-family: monospace; }
.event-session { color: #6b7280; font-family: monospace; font-size: 0.7rem; }
.event-time { color: #475569; white-space: nowrap; }

.approval-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 1rem; z-index: 50; }
.approval-modal { background: #1e293b; border: 1px solid #475569; border-radius: 0.75rem; padding: 1.5rem; width: 400px; max-width: 90vw; box-shadow: 0 25px 50px rgba(0,0,0,0.5); }
.approval-header { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 1rem; }
.approval-icon { font-size: 1.25rem; }
.approval-header h3 { font-size: 1rem; font-weight: 600; }
.approval-field { display: flex; justify-content: space-between; padding: 0.3rem 0; border-bottom: 1px solid #334155; }
.field-label { font-size: 0.75rem; color: #94a3b8; }
.field-value { font-size: 0.85rem; text-align: right; max-width: 60%; word-break: break-all; }
.approval-countdown { font-size: 0.75rem; color: #f59e0b; margin-top: 0.75rem; }
.approval-actions { display: flex; justify-content: flex-end; gap: 0.75rem; margin-top: 1rem; }
.btn-deny { padding: 0.4rem 1.25rem; border-radius: 0.375rem; background: #7f1d1d; color: #fca5a5; border: none; cursor: pointer; font-size: 0.85rem; }
.btn-deny:hover { background: #991b1b; }
.btn-grant { padding: 0.4rem 1.25rem; border-radius: 0.375rem; background: #14532d; color: #86efac; border: none; cursor: pointer; font-size: 0.85rem; }
.btn-grant:hover { background: #166534; }

.mt-3 { margin-top: 0.75rem; }
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
.text-gray-400 { color: #9ca3af; }
.text-sm { font-size: 0.875rem; }
.p-2 { padding: 0.5rem; }
.animate-pulse { animation: pulse 1.5s cubic-bezier(0.4,0,0.6,1) infinite; }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: .5; } }
</style>
