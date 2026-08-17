<template>
  <div class="alog" :class="{ strip }">
    <div class="alog-tabs">
      <button
        v-for="t in TABS" :key="t"
        class="alog-tab mono" :class="{ active: tab === t }"
        @click="tab = t"
      >{{ t }}</button>
      <span class="alog-spacer" />
      <input v-model="filter" placeholder="filter" class="alog-filter mono" aria-label="Filter the log" />
    </div>
    <div class="alog-body">
      <div v-for="l in lines" :key="l.id" class="alog-line mono">
        <span class="alog-time">{{ l.time }}</span>
        <span class="alog-lvl" :style="{ color: LVL_COLOR[l.lvl] ?? 'var(--ink-3)' }">{{ l.lvl }}</span>
        <span class="alog-msg">{{ l.msg }}</span>
      </div>
      <p v-if="!lines.length" class="alog-empty">Nothing yet — this fills as he works.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { BRAIN_URL } from '../lib/endpoints'
import { useEventStore } from '../stores/eventStore'
import { useRobotStore } from '../stores/robotStore'

/** The faceted log — Events · Motion · App log · Approvals. The Talk strip at
 * Full and the Activity view show the SAME data through this one component. */

defineProps<{ strip?: boolean }>()

const TABS = ['events', 'motion', 'app log', 'approvals'] as const
type Tab = typeof TABS[number]
const tab = ref<Tab>('events')
const filter = ref('')

const LVL_COLOR: Record<string, string> = {
  EVT: 'var(--accent)', MOT: 'var(--info)', WARN: 'var(--warn)',
  ERROR: 'var(--danger)', INFO: 'var(--ink-3)',
}

const eventStore = useEventStore()
const robotStore = useRobotStore()

interface Line { id: string; time: string; lvl: string; msg: string }

const fmtTime = (iso: string) => {
  try { return new Date(iso).toLocaleTimeString() } catch { return iso }
}

// App log: the brain's Python-logger ring buffer, polled while visible.
const appLog = ref<{ ts: string; level: string; logger: string; message: string }[]>([])
let appLogTimer: ReturnType<typeof setInterval> | undefined
async function fetchAppLog(): Promise<void> {
  try {
    const r = await fetch(`${BRAIN_URL}/logs/recent?n=80`)
    if (r.ok) appLog.value = (await r.json()).records ?? []
  } catch { /* brain offline */ }
}
onMounted(() => { fetchAppLog(); appLogTimer = setInterval(fetchAppLog, 5000) })
onUnmounted(() => clearInterval(appLogTimer))

const lines = computed<Line[]>(() => {
  let out: Line[]
  if (tab.value === 'events') {
    out = eventStore.events.map(e => ({
      id: e.id, time: fmtTime(e.timestamp), lvl: 'EVT',
      msg: `${e.event_type}${e.session_id ? ` session=${e.session_id}` : ''}`,
    }))
  } else if (tab.value === 'motion') {
    out = robotStore.motionLog.map(m => ({
      id: m.id, time: fmtTime(m.timestamp), lvl: 'MOT',
      msg: `${m.name} · ${m.status}`,
    }))
  } else if (tab.value === 'app log') {
    out = [...appLog.value].reverse().map((r, i) => ({
      id: `app-${i}-${r.ts}`, time: r.ts,
      lvl: r.level === 'WARNING' ? 'WARN' : r.level,
      msg: `${r.logger} · ${r.message}`,
    }))
  } else {
    out = eventStore.events
      .filter(e => e.event_type.startsWith('Approval'))
      .map(e => ({
        id: e.id, time: fmtTime(e.timestamp),
        lvl: e.event_type === 'ApprovalRequested' ? 'WARN' : 'INFO',
        msg: `${e.event_type.replace('Approval', '').toUpperCase()} ${String(e.payload.tool_name ?? '')} ${String(e.payload.arguments_summary ?? '')}`.trim(),
      }))
  }
  const q = filter.value.trim().toLowerCase()
  if (q) out = out.filter(l => l.msg.toLowerCase().includes(q))
  return out.slice(0, 120)
})
</script>

<style scoped>
.alog { display: flex; flex-direction: column; min-height: 0; flex: 1; }
.mono { font-family: var(--font-mono); }

.alog-tabs {
  display: flex; align-items: stretch; height: 26px; flex-shrink: 0;
  border-bottom: 1px solid var(--line); padding-left: 6px;
}
.alog-tab {
  padding: 0 11px; border: none; background: none;
  border-bottom: 2px solid transparent; color: var(--ink-3);
  font-size: 10.5px; font-weight: 700; letter-spacing: 0.08em;
  text-transform: uppercase; cursor: pointer;
}
.alog-tab.active { border-bottom-color: var(--accent); color: var(--ink); }
.alog-spacer { flex: 1; }
.alog-filter {
  align-self: center; width: 110px; padding: 2px 7px; margin-right: 8px;
  background: var(--sunken); border: 1px solid var(--line-strong);
  border-radius: 4px; color: var(--ink); font-size: 11px; outline: none;
}

.alog-body { flex: 1; min-height: 0; overflow-y: auto; padding: 5px 10px; }
.alog-line { display: flex; gap: 10px; padding: 1.5px 0; font-size: 11.5px; line-height: 1.6; }
.alog-line:hover { background: var(--hover); }
.alog-time { color: var(--ink-3); flex-shrink: 0; }
.alog-lvl { width: 40px; flex-shrink: 0; font-weight: 700; }
.alog-msg { color: var(--ink-2); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.alog-empty { font-size: 12px; color: var(--ink-3); padding: 8px 2px; }
</style>
