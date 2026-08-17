<template>
  <nav class="rail" :class="{ collapsed }" aria-label="Views">
    <button
      class="rail-toggle" :title="collapsed ? 'Expand the menu' : 'Collapse the menu to icons'"
      :aria-label="collapsed ? 'Expand the menu' : 'Collapse the menu to icons'"
      @click="prefs.toggleRail()"
    >
      <ChevronRight :size="15" class="rail-chev" :class="{ open: !collapsed }" />
    </button>

    <button
      v-for="item in items" :key="item.id"
      class="rail-item" :class="{ active: nav.view === item.id }"
      :title="item.hint" @click="nav.go(item.id)"
    >
      <span class="rail-icon"><component :is="item.icon" :size="18" /></span>
      <span class="rail-label">{{ item.label }}</span>
      <span v-if="item.badge" class="rail-badge">{{ item.badge }}</span>
    </button>

    <div class="rail-spacer" />

    <button
      class="rail-item" :class="{ active: nav.view === 'about' }"
      title="About AURA — version, updates, licences" @click="nav.go('about')"
    >
      <span class="rail-icon"><Info :size="18" /></span>
      <span class="rail-label">About</span>
    </button>
    <button
      class="rail-item" :class="{ active: nav.view === 'settings' }"
      title="Settings — one home for everything configurable" @click="nav.go('settings')"
    >
      <span class="rail-icon"><Settings :size="18" /></span>
      <span class="rail-label">Settings</span>
    </button>
  </nav>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  Activity, Bot, ChevronRight, Info, MessageCircle, Presentation, Settings, Shield, Sparkles, Users,
} from 'lucide-vue-next'
import { useNavStore, type View } from '../../stores/navStore'
import { usePrefsStore } from '../../stores/prefsStore'
import { useModeStore } from '../../stores/modeStore'
import { useApprovalStore } from '../../stores/approvalStore'

const nav = useNavStore()
const prefs = usePrefsStore()
const modeStore = useModeStore()
const approvals = useApprovalStore()

const collapsed = computed(() => prefs.railCollapsed)

interface RailItem { id: View; label: string; hint: string; icon: unknown; badge?: string }

const items = computed<RailItem[]>(() => {
  const base: RailItem[] = [
    { id: 'talk', label: 'Talk', hint: 'The conversation', icon: MessageCircle },
    { id: 'people', label: 'People', hint: 'Who he knows and what he remembers', icon: Users },
    { id: 'skills', label: 'Skills', hint: 'Procedures he has learned, and their triggers', icon: Sparkles },
    { id: 'robot', label: 'Robot', hint: 'Body, camera, gestures, motion, connection', icon: Bot },
    { id: 'modes', label: 'Modes', hint: 'What he may do, per mode', icon: Shield },
    {
      id: 'activity', label: 'Activity', hint: 'Events, motion, app log, approvals', icon: Activity,
      // Derived, never hand-written: the badge is the pending-approval count.
      badge: approvals.pending.length ? String(approvals.pending.length) : undefined,
    },
  ]
  // Presentations only earn a slot when they are relevant: in Present mode, or
  // while you are authoring one (reached from Modes › Present).
  if (modeStore.mode === 'present' || nav.view === 'present') {
    base.splice(4, 0, {
      id: 'present', label: 'Present', hint: 'Build, rehearse and run a presentation',
      icon: Presentation, badge: modeStore.mode === 'present' ? '●' : undefined,
    })
  }
  return base
})
</script>

<style scoped>
.rail {
  width: 158px; flex-shrink: 0; background: var(--chrome);
  border-right: 1px solid var(--line);
  display: flex; flex-direction: column; padding: 8px; gap: 3px;
}
.rail.collapsed { width: 62px; padding: 8px 6px; }

.rail-toggle {
  display: inline-flex; align-items: center; justify-content: flex-end;
  width: 100%; padding: 4px 6px 8px; background: none; border: none;
  color: var(--ink-3); cursor: pointer;
}
.rail.collapsed .rail-toggle { justify-content: center; }
.rail-chev { transition: transform 0.15s; }
.rail-chev.open { transform: rotate(180deg); }

.rail-item {
  display: flex; align-items: center; gap: 9px; width: 100%;
  padding: 8px 10px; border: none; border-radius: 9px;
  cursor: pointer; font-family: inherit;
  background: none; color: var(--ink-2);
}
.rail-item.active { background: var(--accent-wash); color: var(--accent); }
.rail.collapsed .rail-item {
  flex-direction: column; gap: 3px; padding: 9px 2px; border-radius: 10px;
  color: var(--ink-3);
}
.rail.collapsed .rail-item.active { color: var(--accent); }

.rail-icon { display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.rail-label { flex: 1; text-align: left; font-size: 13px; font-weight: 600; }
.rail.collapsed .rail-label { flex: none; text-align: center; font-size: 9.5px; letter-spacing: 0.02em; }

.rail-badge {
  min-width: 17px; height: 17px; padding: 0 5px; border-radius: 9px;
  background: var(--warn); color: var(--sunken);
  font-size: 10px; font-weight: 700;
  display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.rail-spacer { flex: 1; }
</style>
