<template>
  <main class="d2-main activity">
    <div class="activity-inner">
      <!-- ═══ The Mind — the same events, drawn as a working brain ═══ -->
      <section class="d2-card mind-sec">
        <div class="mind-head">
          <h2>Mind</h2>
          <span class="mind-note">Every node lights from a real event — nothing here is decorative.</span>
          <span class="spacer" />
          <span class="mind-pulse" :class="{ quiet: modeStore.quiet }" />
          <span class="mono mind-state">{{ modeStore.quiet ? 'hushed' : status === WAITING ? 'idle' : 'working' }}</span>
        </div>
        <div class="mind-canvas-wrap">
          <MindCanvas :height="330" big @status="status = $event" />
        </div>
        <div class="mono mind-event">{{ status }}</div>
      </section>

      <!-- ═══ The faceted log ═══ -->
      <div class="log-head">
        <h2>Activity</h2>
      </div>
      <section class="d2-card log-sec">
        <ActivityLog />
      </section>
    </div>
  </main>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import ActivityLog from '../components/ActivityLog.vue'
import MindCanvas from '../components/canvas/MindCanvas.vue'
import { useModeStore } from '../stores/modeStore'

const modeStore = useModeStore()
const WAITING = 'Waiting for something to happen'
const status = ref(WAITING)
</script>

<style scoped>
.activity-inner { max-width: 860px; }
.mono { font-family: var(--font-mono); }
.spacer { flex: 1; }

.mind-sec { border-radius: 12px; padding: 14px 16px 12px; margin-bottom: 14px; }
.mind-head { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; flex-wrap: wrap; }
.mind-head h2 { margin: 0; font-size: 15px; }
.mind-note { font-size: 12.5px; color: var(--ink-2); }
.mind-pulse { width: 7px; height: 7px; border-radius: 50%; background: var(--accent); animation: ripple 1.6s ease-out infinite; }
.mind-pulse.quiet { background: var(--ink-3); animation: none; }
.mind-state { font-size: 11px; color: var(--ink-3); }
.mind-canvas-wrap { max-width: 520px; margin: 0 auto; }
.mind-event {
  font-size: 11.5px; color: var(--ink-2); margin-top: 8px; padding-top: 8px;
  border-top: 1px solid var(--line); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

.log-head { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }
.log-head h2 { margin: 0; font-size: 19px; }
.log-sec { border-radius: 12px; overflow: hidden; min-height: 260px; display: flex; }
</style>
