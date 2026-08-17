<template>
  <main class="d2-main about">
    <div class="about-inner">
      <div class="about-hero">
        <span class="about-art" v-html="characterStore.current.art(56, 'idle')" />
        <div>
          <h2>AURA</h2>
          <p class="about-sub">Adaptive Unified Robotic Assistant</p>
          <p class="mono about-version">version {{ version }}</p>
        </div>
      </div>
      <p class="about-desc">
        An embodied AI assistant living in a Reachy Mini robot — voice conversations,
        face recognition, a personal knowledge graph and a self-optimizing skills library.
      </p>

      <dl class="acronym">
        <template v-for="a in ACRONYM" :key="a.word">
          <dt>{{ a.word }}</dt>
          <dd>{{ a.meaning }}</dd>
        </template>
      </dl>

      <div class="links">
        <a href="https://mityjohn.com" target="_blank" rel="noopener" class="link-card">
          <Globe :size="17" class="link-icon" />
          <span class="link-label">mityjohn.com</span>
          <span class="link-spacer" />
          <span class="link-note">blog &amp; projects by mITy.John</span>
        </a>
        <a href="https://github.com/janvanwassenhove/aura" target="_blank" rel="noopener" class="link-card">
          <Github :size="17" class="link-icon" />
          <span class="link-label">GitHub</span>
          <span class="link-spacer" />
          <span class="link-note">source &amp; releases</span>
        </a>
      </div>

      <div class="about-row">
        <div class="about-row-text">
          <div class="about-row-title">Updates</div>
          <div class="about-row-sub">Console and robot check nightly</div>
        </div>
        <button class="d2-ghost-btn" :disabled="checking" @click="checkUpdates">{{ checking ? 'Checking…' : 'Check for updates' }}</button>
      </div>
      <p v-if="updateMsg" class="about-note" :class="updateKind">{{ updateMsg }}</p>
      <div class="about-row">
        <div class="about-row-text">
          <div class="about-row-title">Restart the brain</div>
          <div class="about-row-sub">Reload code and settings without losing memory</div>
        </div>
        <button class="d2-ghost-btn" :disabled="restarting" @click="restartBrain">{{ restarting ? 'Restarting…' : 'Restart' }}</button>
      </div>
      <div class="about-row">
        <div class="about-row-text">
          <div class="about-row-title">Run setup again</div>
          <div class="about-row-sub">The first-run wizard, any time</div>
        </div>
        <button class="d2-ghost-btn" @click="$emit('rerun-setup')">Open wizard</button>
      </div>
      <div class="about-row">
        <div class="about-row-text">
          <div class="about-row-title">Diagnostics</div>
          <div class="about-row-sub">Copy a report for troubleshooting — no personal data</div>
        </div>
        <button class="d2-ghost-btn" @click="copyDiagnostics">{{ copied ? 'Copied ✓' : 'Copy' }}</button>
      </div>

      <p class="about-footer">
        Made by <a href="https://mityjohn.com" target="_blank" rel="noopener">Jan Van Wassenhove</a>
        · built with the Reachy Mini SDK
      </p>
    </div>
  </main>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Github, Globe } from 'lucide-vue-next'
import { BRAIN_URL } from '../lib/endpoints'
import { useCharacterStore } from '../stores/characterStore'
import { useKnowledgeStore } from '../stores/knowledgeStore'
import { useModeStore } from '../stores/modeStore'
import { useRobotStore } from '../stores/robotStore'

defineEmits<{ (e: 'rerun-setup'): void }>()

const characterStore = useCharacterStore()
const robot = useRobotStore()
const knowledge = useKnowledgeStore()
const modeStore = useModeStore()

const ACRONYM = [
  { word: 'Adaptive', meaning: 'Adapts behaviour and interaction to the person, the context and the situation.' },
  { word: 'Unified', meaning: 'Brings conversation, mail, Teams, calendar, todos, memory and agents together.' },
  { word: 'Robotic', meaning: 'Physically embodied through Reachy Mini.' },
  { word: 'Assistant', meaning: 'A personal assistant and copilot, not just another chatbot.' },
]

// Packaged builds get their real version from Electron (stamped per release);
// a plain browser/dev run shows "dev" rather than pretending.
const auraWindow = (window as unknown as { aura?: { appVersion?: () => Promise<string>; checkUpdate?: () => Promise<Record<string, unknown>> } }).aura
const version = ref('dev')
onMounted(async () => {
  try {
    const v = await auraWindow?.appVersion?.()
    if (v) version.value = v
  } catch { /* dev / browser — keep "dev" */ }
})

// U178: a manual check must always say what happened.
const checking = ref(false)
const updateMsg = ref('')
const updateKind = ref<'ok' | 'new' | 'warn'>('ok')
async function checkUpdates(): Promise<void> {
  checking.value = true
  updateMsg.value = ''
  try {
    const r = await auraWindow?.checkUpdate?.() as { status?: string; update?: { version: string }; latest?: string; reason?: string } | undefined
    if (!r) { updateKind.value = 'warn'; updateMsg.value = 'Update checking is unavailable here.'; return }
    if (r.status === 'update') {
      updateKind.value = 'new'
      updateMsg.value = `Version ${r.update?.version} is available — the install prompt opens next.`
    } else if (r.status === 'current') {
      updateKind.value = 'ok'
      updateMsg.value = `You're up to date (${r.latest ?? version.value}).`
    } else if (r.status === 'unauthorized') {
      updateKind.value = 'warn'
      updateMsg.value = 'Could not check: the release repository is private. Add GITHUB_TOKEN to your settings, or make the repository public.'
    } else if (r.status === 'dev') {
      updateKind.value = 'ok'
      updateMsg.value = 'Development build — updates are not checked.'
    } else {
      updateKind.value = 'warn'
      updateMsg.value = `Could not check for updates (${r.reason ?? 'unknown'}).`
    }
  } finally { checking.value = false }
}

const restarting = ref(false)
async function restartBrain(): Promise<void> {
  restarting.value = true
  try {
    await fetch(`${BRAIN_URL}/setup/config`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ restart: true }),
    })
  } catch { /* the brain going away IS the restart */ }
  finally { setTimeout(() => { restarting.value = false }, 4000) }
}

// Diagnostics: states and versions only — no personal data, by construction.
const copied = ref(false)
async function copyDiagnostics(): Promise<void> {
  const report = [
    `AURA diagnostics · ${new Date().toISOString()}`,
    `console version: ${version.value}`,
    `mode: ${modeStore.mode} · quiet: ${modeStore.quiet}`,
    `robot: ${robot.connected ? 'connected' : 'offline'} · mode ${robot.mode} · tracking ${robot.tracking}`,
    `vault: ${knowledge.omkLoaded ? 'encrypted' : 'not set up'} · tier ${knowledge.tier}`,
    `people: ${knowledge.people.length}`,
    `platform: ${navigator.userAgent}`,
  ].join('\n')
  try {
    await navigator.clipboard.writeText(report)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2500)
  } catch { /* clipboard blocked */ }
}
</script>

<style scoped>
.about { padding: 26px 28px; }
.about-inner { max-width: 620px; }
.mono { font-family: var(--font-mono); }

.about-hero { display: flex; align-items: center; gap: 16px; margin-bottom: 20px; }
.about-art { display: flex; }
.about-hero h2 { margin: 0; font-size: 22px; letter-spacing: 0.04em; font-weight: 700; }
.about-sub { margin: 2px 0 0; font-size: 13.5px; color: var(--ink-2); }
.about-version { margin: 3px 0 0; font-size: 12px; color: var(--ink-3); }
.about-desc { margin: 0 0 18px; font-size: 14.5px; color: var(--ink-2); line-height: 1.6; max-width: 58ch; }

.acronym { margin: 0 0 22px; display: grid; grid-template-columns: auto 1fr; gap: 10px 22px; align-items: baseline; }
.acronym dt { font-size: 14px; font-weight: 700; }
.acronym dd { margin: 0; font-size: 13.5px; color: var(--ink-2); line-height: 1.5; }

.links { display: flex; flex-direction: column; gap: 8px; margin-bottom: 20px; max-width: 58ch; }
.link-card {
  display: flex; align-items: center; gap: 10px; padding: 11px 14px;
  border: 1px solid var(--line); border-radius: 11px; background: var(--surface);
  text-decoration: none; color: var(--ink);
}
.link-card:hover { border-color: var(--accent); }
.link-icon { color: var(--ink-2); flex-shrink: 0; }
.link-label { font-size: 13.5px; font-weight: 600; }
.link-spacer { flex: 1; }
.link-note { font-size: 12.5px; color: var(--ink-3); }

.about-row { display: flex; align-items: center; gap: 12px; padding: 12px 0; border-top: 1px solid var(--line); }
.about-row-text { flex: 1; min-width: 0; }
.about-row-title { font-size: 14px; font-weight: 600; }
.about-row-sub { font-size: 12.5px; color: var(--ink-3); margin-top: 2px; }
.about-note { margin: 0 0 8px; font-size: 12.5px; color: var(--ink-2); }
.about-note.warn { color: var(--warn); }
.about-note.new { color: var(--accent); }

.about-footer { margin: 22px 0 0; font-size: 12.5px; color: var(--ink-3); line-height: 1.6; text-align: center; }
.about-footer a { color: var(--accent); }
</style>
