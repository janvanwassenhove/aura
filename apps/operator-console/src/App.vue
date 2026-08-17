<template>
  <div class="app-layout">
    <AppHeader :ws-status="wsStatus" />

    <!-- U197: sits directly under the header so it is impossible to miss,
         but blocks nothing the owner was doing. -->
    <UpdateBanner />

    <!-- D2: the capability chip row — mode's consequences, always visible -->
    <CapabilityRow />

    <!-- Approvals render inline in Talk; the overlay only covers the views
         where the transcript is not on screen, so an ask is never missed. -->
    <ApprovalPanel v-if="nav.view !== 'talk'" />

    <!-- U34: full-screen onboarding on first run (re-runnable from About) -->
    <SetupWizard v-if="showWizard" @done="showWizard = false" />

    <div class="app-body">
      <NavRail />
      <TalkView v-if="nav.view === 'talk'" />
      <PeopleView v-else-if="nav.view === 'people'" />
      <SkillsView v-else-if="nav.view === 'skills'" />
      <RobotView v-else-if="nav.view === 'robot'" />
      <PresentView v-else-if="nav.view === 'present'" />
      <ActivityView v-else-if="nav.view === 'activity'" />
      <ModesView v-else-if="nav.view === 'modes'" />
      <SettingsView v-else-if="nav.view === 'settings'" />
      <AboutView v-else-if="nav.view === 'about'" @rerun-setup="showWizard = true" />
      <GraphView v-else-if="nav.view === 'graph'" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import AppHeader from './components/shell/AppHeader.vue'
import CapabilityRow from './components/shell/CapabilityRow.vue'
import NavRail from './components/shell/NavRail.vue'
import UpdateBanner from './components/UpdateBanner.vue'
import ApprovalPanel from './components/ApprovalPanel.vue'
import SetupWizard from './components/SetupWizard.vue'
import TalkView from './views/TalkView.vue'
import PeopleView from './views/PeopleView.vue'
import SkillsView from './views/SkillsView.vue'
import RobotView from './views/RobotView.vue'
import PresentView from './views/PresentView.vue'
import ActivityView from './views/ActivityView.vue'
import ModesView from './views/ModesView.vue'
import SettingsView from './views/SettingsView.vue'
import AboutView from './views/AboutView.vue'
import GraphView from './views/GraphView.vue'
import { useEventBusWs } from './composables/useEventBusWs'
import { useKnowledgeStore } from './stores/knowledgeStore'
import { useModeStore } from './stores/modeStore'
import { useNavStore } from './stores/navStore'
import { usePrefsStore } from './stores/prefsStore'
import { useRobotStore } from './stores/robotStore'
import { useSetupStore } from './stores/setupStore'
import { useThemeStore } from './stores/themeStore'

const { wsStatus, connect } = useEventBusWs()
const showWizard = ref(false)
const themeStore = useThemeStore()
const setupStore = useSetupStore()
const nav = useNavStore()
const modeStore = useModeStore()
const knowledge = useKnowledgeStore()
const prefs = usePrefsStore()
const robot = useRobotStore()

// A recognised face sets the speaker (and their density) without asking; a
// lost face starts the drop-to-Guest clock. Manual choices always win.
watch(() => robot.lastRecognized, (r) => {
  if (!r) return
  if (r.known && r.person_id) {
    knowledge.setSpeaker(r.person_id, 'face')
    knowledge.noteFaceSeen()
    prefs.followPerson(knowledge.people.find(p => p.person_id === r.person_id)?.role)
  }
})
watch(() => robot.faceVisible, (visible) => {
  if (visible === false) knowledge.noteNoFace()
  else if (visible) knowledge.noteFaceSeen()
})

onMounted(async () => {
  themeStore.apply()
  connect()
  modeStore.fetchPolicy()
  knowledge.fetchTier()
  knowledge.fetchPeople()
  // U34: first-run onboarding — only when the brain is reachable, setup was
  // never completed AND the install genuinely looks fresh. An existing,
  // clearly-configured install (keys/people/encryption present but no
  // SETUP_DONE marker) must never get hijacked by a full-screen wizard.
  await setupStore.fetchStatus()
  const st = setupStore.status
  if (st && !st.setup_done) {
    const looksConfigured =
      st.openai_key_set || st.openrouter_key_set || st.gemini_key_set ||
      st.people_count > 0 || st.encrypted
    if (looksConfigured) {
      setupStore.saveConfig({ setup_done: true })
    } else {
      showWizard.value = true
    }
  }
})
</script>

<style>
@import "tailwindcss";
@import "./styles/fonts.css";
@import "./styles/tokens.css";

:root {
  font-family: var(--font-ui);
}

body {
  background: var(--bg);
  color: var(--ink);
}

.app-layout { display: flex; flex-direction: column; height: 100vh; background: var(--bg); color: var(--ink); }
.app-body { flex: 1; min-height: 0; display: flex; }

/* ── D2 shared primitives (used across views) ─────────────────────────── */
.mono { font-family: var(--font-mono); }

.d2-main { flex: 1; min-width: 0; overflow-y: auto; padding: 18px 24px; }

.d2-card {
  background: var(--surface); border: 1px solid var(--line);
  border-radius: var(--radius-card);
}

.d2-h3 {
  margin: 0 0 10px; font-size: 12px; font-weight: 700;
  letter-spacing: 0.08em; text-transform: uppercase; color: var(--ink-3);
}

.d2-ghost-btn {
  padding: 6px 13px; border-radius: 9px; background: var(--surface);
  border: 1px solid var(--line-strong); color: var(--ink-2);
  font-size: 12.5px; font-weight: 600; cursor: pointer; font-family: inherit;
}
.d2-ghost-btn:hover { border-color: var(--accent); color: var(--accent); }

.d2-primary-btn {
  padding: 8px 16px; border-radius: 10px; background: var(--accent);
  color: var(--on-accent); border: none; font-size: 13px; font-weight: 700;
  cursor: pointer; font-family: inherit;
}
.d2-primary-btn:hover:not(:disabled) { background: var(--accent-deep); }
.d2-primary-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.d2-danger-btn {
  padding: 6px 13px; border-radius: 9px; background: transparent;
  border: 1px solid var(--danger); color: var(--danger);
  font-size: 12.5px; font-weight: 600; cursor: pointer; font-family: inherit;
}
.d2-danger-btn:hover { background: var(--danger); color: #fff; }

.d2-field {
  padding: 8px 11px; background: var(--surface-2);
  border: 1.5px solid var(--line-strong); border-radius: 10px;
  color: var(--ink); font-size: 13px; outline: none; font-family: inherit;
  box-sizing: border-box; width: 100%;
}
.d2-field:focus { border-color: var(--accent); }

.d2-mini-toggle {
  padding: 5px 10px; border-radius: 8px; font-size: 11.5px; font-weight: 600;
  cursor: pointer; font-family: inherit;
  background: var(--surface-2); border: 1px solid var(--line); color: var(--ink-3);
}
.d2-mini-toggle.on {
  background: var(--accent-wash); border-color: var(--accent); color: var(--accent);
}

@keyframes breathe { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-3px); } }
@keyframes ripple { 0% { transform: scale(0.85); opacity: 0.38; } 100% { transform: scale(1.45); opacity: 0; } }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
