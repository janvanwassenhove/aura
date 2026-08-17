<template>
  <header class="hdr">
    <!-- The mark breathes while idle; silence looks like silence -->
    <span class="hdr-mark" v-html="characterStore.current.art(24, 'idle')" />

    <!-- MODE: the visually heaviest control on screen — its consequence is the highest -->
    <div class="mode-group" role="group" aria-label="Mode">
      <button
        v-for="m in modes" :key="m.id"
        class="mode-btn" :class="{ active: m.id === modeStore.mode }"
        :style="m.id === modeStore.mode ? { background: modeColor(m.id), color: '#fff' } : {}"
        :title="`${m.label} mode — ${m.hint}`" :aria-label="m.label"
        @click="modeStore.setMode(m.id)"
      >
        <component :is="m.icon" :size="17" />
        <span v-if="m.id === modeStore.mode" class="mode-label">{{ m.label }}</span>
      </button>
    </div>

    <!-- Quiet is a behaviour, not a mode — it composes with any of them -->
    <button
      class="quiet-btn" :class="{ on: modeStore.quiet }"
      title="Quiet hours — he answers when asked but never speaks first. Works in any mode."
      @click="modeStore.toggleQuiet()"
    >
      <Moon :size="14" /> Quiet
    </button>

    <span class="hdr-spacer" />

    <!-- One health chip: silent when fine, specific when not -->
    <button class="health-chip" :class="{ warn: !health.ok }" :title="health.hint" @click="health.go?.()">
      <span class="health-dot" :style="{ background: health.ok ? 'var(--ok)' : 'var(--warn)' }" />
      {{ health.label }}
    </button>

    <!-- Persistent identity — click to reassign, always escapable -->
    <button class="who-chip" :class="{ unknown: !speakerPerson }" :title="whoHint" @click="cycleSpeaker">
      <span class="who-avatar" :class="{ guest: isGuestSpeaker || !speakerPerson }">{{ whoInitials }}</span>
      <span class="who-text">
        <span class="who-name">{{ whoName }}</span>
        <span class="who-sub">{{ whoSub }}</span>
      </span>
      <ChevronDown :size="12" class="who-chev" />
    </button>

    <!-- Density: demoted to a small dial, never mistaken for mode -->
    <div class="density-group" role="group" aria-label="Detail level" :title="densityHint">
      <button
        v-for="d in densities" :key="d.id"
        class="density-btn" :class="{ active: d.id === prefs.density }"
        :title="`${d.label} detail — ${d.hint}`" :aria-label="d.label"
        @click="prefs.setDensity(d.id)"
      >
        <component :is="d.icon" :size="15" />
      </button>
    </div>

    <!-- Theme lives where the eyes already are; one click, no settings trip -->
    <button
      class="theme-btn" :title="theme.theme === 'dark' ? 'Switch to light — warm paper' : 'Switch to dark — deep evergreen'"
      :aria-label="theme.theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'"
      @click="theme.theme = theme.theme === 'dark' ? 'light' : 'dark'"
    >
      <Sun v-if="theme.theme === 'dark'" :size="15" />
      <MoonStar v-else :size="15" />
    </button>

    <!-- Stop never moves. Same place, same colour, every mode, every density. -->
    <button class="stop-btn" :disabled="stopping" title="Stops speech mid-word, ends the turn, mic off" @click="panicStop">
      <CircleStop :size="13" /> {{ stopping ? 'Stopping…' : 'Stop' }}
    </button>

    <!-- The header IS the title bar (frameless window): OS controls, our chrome -->
    <div v-if="isElectron" class="win-controls" role="group" aria-label="Window">
      <button class="win-btn" title="Minimize" aria-label="Minimize" @click="aura?.minimize()"><Minus :size="14" /></button>
      <button class="win-btn" title="Maximize / restore" aria-label="Maximize or restore" @click="aura?.toggleMaximize()"><Square :size="11" /></button>
      <button class="win-btn win-btn--close" title="Close" aria-label="Close window" @click="aura?.close()"><X :size="14" /></button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  BriefcaseBusiness, ChevronDown, CircleStop, Equal, Home, Menu, Minus,
  Moon, MoonStar, Presentation, Square, Sun, X,
} from 'lucide-vue-next'
import { BRAIN_URL } from '../../lib/endpoints'
import { DENSITY_META, usePrefsStore, type Density } from '../../stores/prefsStore'
import { MODE_META, useModeStore, type UiMode } from '../../stores/modeStore'
import { useCharacterStore } from '../../stores/characterStore'
import { useKnowledgeStore } from '../../stores/knowledgeStore'
import { useNavStore } from '../../stores/navStore'
import { useThemeStore } from '../../stores/themeStore'

// D2: the frameless window's title bar is this header — Electron exposes the
// window verbs on `window.aura`, absent when the console runs in a browser.
const aura = (window as never as { aura?: {
  isElectron?: boolean; minimize: () => void; toggleMaximize: () => void; close: () => void
} }).aura
const isElectron = !!aura?.isElectron

const props = defineProps<{ wsStatus: 'connecting' | 'open' | 'closed' }>()

const modeStore = useModeStore()
const prefs = usePrefsStore()
const characterStore = useCharacterStore()
const knowledge = useKnowledgeStore()
const nav = useNavStore()
const theme = useThemeStore()

const modes = ([
  { id: 'home', icon: Home },
  { id: 'work', icon: BriefcaseBusiness },
  { id: 'present', icon: Presentation },
] as const).map(m => ({ ...m, label: MODE_META[m.id].label, hint: MODE_META[m.id].hint }))

function modeColor(id: UiMode): string {
  return id === 'present' ? 'var(--present)' : id === 'work' ? 'var(--info)' : 'var(--accent)'
}

const densities = ([
  { id: 'calm', icon: Minus },
  { id: 'standard', icon: Equal },
  { id: 'full', icon: Menu },
] as const).map(d => ({ ...d, label: DENSITY_META[d.id as Density].label, hint: DENSITY_META[d.id as Density].hint }))

// ── Health: one chip, one grammar. Quiet when fine, names the problem when not.
import { useRobotStore } from '../../stores/robotStore'
const robot = useRobotStore()
const health = computed(() => {
  if (props.wsStatus !== 'open') {
    return { ok: false, label: 'Brain unreachable', hint: 'The console lost the brain — check that AURA is running.', go: () => nav.go('settings') }
  }
  if (knowledge.locked) {
    return { ok: false, label: 'Vault locked', hint: 'Profiles are encrypted and locked — unlock in Settings › Privacy.', go: () => nav.go('settings') }
  }
  if (!robot.connected) {
    return { ok: false, label: 'Robot offline', hint: 'Everything else keeps working, text only. Reconnect in Robot › Connection.', go: () => nav.go('robot') }
  }
  return {
    ok: true, label: 'All good',
    hint: `Brain connected · robot ${robot.mode || 'online'} · vault ${knowledge.omkLoaded ? 'unlocked' : 'not set up'}`,
    go: undefined,
  }
})

// ── Identity chip ──────────────────────────────────────────────────────────
const speakerPerson = computed(() =>
  knowledge.people.find(p => p.person_id === knowledge.speaker) ?? null)
const isGuestSpeaker = computed(() => knowledge.speaker === 'guest')

const whoName = computed(() =>
  isGuestSpeaker.value ? 'Guest' : speakerPerson.value?.display_name ?? 'Who is this?')
const whoInitials = computed(() => {
  if (isGuestSpeaker.value) return 'G'
  const n = speakerPerson.value?.display_name
  return n ? n.slice(0, 2).toUpperCase() : '?'
})
const whoSub = computed(() => {
  if (isGuestSpeaker.value) return 'nothing saved'
  if (!speakerPerson.value) return 'tap to choose'
  return `${speakerPerson.value.role} · tap to switch`
})
const whoHint = computed(() =>
  speakerPerson.value || isGuestSpeaker.value
    ? `Answering as ${whoName.value}. Click to switch person or drop to Guest — he also drops to Guest after 10 minutes with no face.`
    : 'Nobody selected — click to say who is talking')

function cycleSpeaker(): void {
  const order = [...knowledge.people.map(p => p.person_id), 'guest']
  if (!order.length) return
  const i = order.indexOf(knowledge.speaker ?? '')
  knowledge.setSpeaker(order[(i + 1) % order.length], 'manual')
  prefs.resetDensityTouch()
  const role = order[(i + 1) % order.length] === 'guest'
    ? 'guest'
    : knowledge.people.find(p => p.person_id === order[(i + 1) % order.length])?.role
  prefs.followPerson(role)
}

const densityHint = computed(() =>
  prefs.densityTouched
    ? 'Detail level (set by hand)'
    : `Detail level — automatically ${DENSITY_META[prefs.density].label} for ${whoName.value}`)

// ── Stop ───────────────────────────────────────────────────────────────────
const stopping = ref(false)
async function panicStop(): Promise<void> {
  if (stopping.value) return
  stopping.value = true
  try {
    await fetch(`${BRAIN_URL}/voice/panic`, { method: 'POST' })
  } catch { /* the robot may already be unreachable — nothing left to stop */ }
  finally { stopping.value = false }
}
</script>

<style scoped>
.hdr {
  display: flex; align-items: center; gap: 12px; flex-shrink: 0;
  background: var(--chrome); border-bottom: 1px solid var(--line);
  padding: 9px 12px 9px 14px;
  /* The header doubles as the frameless window's title bar: the background
     drags the window, every control below opts back out. */
  -webkit-app-region: drag;
}
.hdr button, .hdr [role='group'] { -webkit-app-region: no-drag; }
.hdr-mark { display: flex; flex-shrink: 0; }
.hdr-spacer { flex: 1; min-width: 6px; }

.mode-group {
  display: flex; background: var(--sunken); border: 1px solid var(--line-strong);
  border-radius: 11px; padding: 3px; gap: 3px; flex-shrink: 0;
}
.mode-btn {
  display: inline-flex; align-items: center; gap: 7px; padding: 8px 11px;
  border: none; border-radius: 9px; cursor: pointer; font-family: inherit;
  background: transparent; color: var(--ink-3);
}
.mode-btn.active { padding: 8px 14px; }
.mode-label { font-size: 13.5px; font-weight: 700; letter-spacing: -0.01em; }

.quiet-btn {
  display: inline-flex; align-items: center; gap: 6px; padding: 7px 12px;
  border-radius: 9px; cursor: pointer; font-family: inherit;
  font-size: 12.5px; font-weight: 600; flex-shrink: 0;
  background: transparent; border: 1.5px solid var(--line-strong); color: var(--ink-3);
}
.quiet-btn.on { background: var(--accent-wash); border-color: var(--accent); color: var(--accent); }

.health-chip {
  display: inline-flex; align-items: center; gap: 7px; padding: 6px 11px;
  border-radius: 999px; cursor: pointer; font-family: inherit;
  font-size: 12px; font-weight: 600; flex-shrink: 0;
  background: var(--surface); border: 1px solid var(--line); color: var(--ink-2);
}
.health-chip.warn { color: var(--warn); }
.health-dot { width: 8px; height: 8px; border-radius: 50%; }

.who-chip {
  display: inline-flex; align-items: center; gap: 8px; padding: 5px 9px 5px 5px;
  border-radius: 999px; cursor: pointer; font-family: inherit;
  flex: 0 1 auto; min-width: 38px; overflow: hidden;
  background: var(--surface); border: 1.5px solid var(--line); color: var(--ink);
}
.who-chip.unknown { border-color: var(--warn); }
.who-avatar {
  width: 26px; height: 26px; border-radius: 50%; flex-shrink: 0;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 10.5px; font-weight: 700;
  background: var(--accent); color: var(--on-accent);
}
.who-avatar.guest { background: var(--sunken); color: var(--ink-3); }
.who-text {
  display: flex; flex-direction: column; align-items: flex-start;
  line-height: 1.15; min-width: 0; overflow: hidden;
}
.who-name {
  font-size: 12.5px; font-weight: 600; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap; max-width: 100%;
}
.who-sub {
  font-size: 10px; color: var(--ink-3); overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap; max-width: 100%;
}
.who-chev { color: var(--ink-3); flex-shrink: 0; }

.density-group {
  display: flex; background: var(--sunken); border: 1px solid var(--line);
  border-radius: 9px; padding: 2px; gap: 1px; flex-shrink: 0;
}
.density-btn {
  display: inline-flex; align-items: center; justify-content: center;
  width: 28px; height: 26px; border: none; border-radius: 7px;
  cursor: pointer; font-family: inherit; background: transparent; color: var(--ink-3);
}
.density-btn.active { background: var(--surface); color: var(--ink); }

.stop-btn {
  display: inline-flex; align-items: center; gap: 6px; padding: 7px 13px;
  background: var(--danger-wash); color: var(--danger);
  border: 1.5px solid var(--danger); border-radius: 9px;
  font-size: 12.5px; font-weight: 700; cursor: pointer; font-family: inherit; flex-shrink: 0;
}
.stop-btn:hover:not(:disabled) { background: var(--danger); color: #fff; }

.theme-btn {
  display: inline-flex; align-items: center; justify-content: center;
  width: 30px; height: 28px; border-radius: 8px; flex-shrink: 0;
  background: transparent; border: 1px solid var(--line); color: var(--ink-3);
  cursor: pointer;
}
.theme-btn:hover { color: var(--ink); background: var(--sunken); }

.win-controls { display: flex; flex-shrink: 0; margin: -9px -12px -9px 2px; align-self: stretch; }
.win-btn {
  display: inline-flex; align-items: center; justify-content: center;
  width: 40px; border: none; background: transparent; color: var(--ink-3);
  cursor: pointer;
}
.win-btn:hover { background: var(--sunken); color: var(--ink); }
.win-btn--close:hover { background: var(--danger); color: #fff; }
</style>
