<template>
  <main class="d2-main settings">
    <div class="settings-inner">
      <h2>Settings</h2>
      <p class="lead">One home for everything configurable — nothing here needs a text editor.</p>

      <!-- ═══ Intelligence ═══ -->
      <section class="d2-card sec">
        <header class="sec-head">
          <h3>Intelligence</h3>
          <span class="mono sec-meta">provider · models · conversation engine</span>
        </header>
        <div class="row">
          <div class="row-text">
            <div class="row-title">Provider</div>
            <div class="row-sub">Who he thinks with. The key is stored on this laptop and never shown again.</div>
          </div>
          <select v-model="settingsStore.provider" class="d2-field row-field" aria-label="Provider" @change="onProviderChange">
            <option value="openai">OpenAI</option>
            <option value="openrouter">OpenRouter</option>
            <option value="gemini">Google Gemini</option>
            <option value="echo">Echo (test, no key)</option>
          </select>
          <span class="row-val" :class="keySet ? 'ok' : 'warn'">{{ keySet ? 'key set ✓' : 'no key' }}</span>
        </div>
        <div class="row">
          <div class="row-text">
            <div class="row-title">API key</div>
            <div class="row-sub">{{ keySet ? 'Leave empty to keep the stored key.' : 'Pasted once, encrypted immediately, never displayed again.' }}</div>
          </div>
          <input v-model="newKey" type="password" class="d2-field row-field" :placeholder="keyPlaceholder" aria-label="API key">
          <button class="d2-ghost-btn" :disabled="!newKey.trim() || savingKey" @click="saveKey">{{ savingKey ? 'Saving…' : 'Save key' }}</button>
        </div>
        <div class="row">
          <div class="row-text">
            <div class="row-title">Model</div>
            <div class="row-sub">The conversation model for this provider.</div>
          </div>
          <select v-model="settingsStore.model" class="d2-field row-field" aria-label="Model" @change="applyModel">
            <option v-for="m in settingsStore.models" :key="m.id" :value="m.id">{{ m.name }}{{ m.free ? ' · free' : '' }}</option>
            <option v-if="!settingsStore.models.length" :value="settingsStore.model">{{ settingsStore.model || 'default' }}</option>
          </select>
        </div>
        <!-- U90/U202: per-task-type model roles — empty means "use the model
             above". Only Voice takes a realtime model; the others go through
             chat-completions, which a realtime model cannot serve (U191). -->
        <template v-if="settingsStore.provider === 'openai'">
          <div v-for="role in MODEL_ROLES" :key="role.field" class="row">
            <div class="row-text">
              <div class="row-title">{{ role.label }}</div>
              <div class="row-sub">{{ role.sub }}</div>
            </div>
            <select v-model="roles[role.field]" class="d2-field row-field" :aria-label="role.label" @change="saveModelRoles">
              <option value="">{{ role.field === 'realtime_model' ? '— automatic —' : '— use the model above —' }}</option>
              <option v-for="m in roleOptions(role.kind, roles[role.field])" :key="m.id" :value="m.id">{{ m.name }}</option>
            </select>
          </div>
          <p v-if="rolesSaved" class="sec-note">Model roles saved.</p>
        </template>
        <div class="row">
          <div class="row-text">
            <div class="row-title">Conversation engine</div>
            <div class="row-sub">Pipeline runs tools and is cheaper; realtime is fluid speech-to-speech.</div>
          </div>
          <select :value="prefs.voiceEngine" class="d2-field row-field" aria-label="Conversation engine" @change="saveEngine">
            <option value="pipeline">pipeline</option>
            <option value="realtime">realtime</option>
          </select>
          <button class="d2-ghost-btn" :disabled="testingRealtime"
                  title="Checks whether your account can actually open a realtime session"
                  @click="testRealtime">{{ testingRealtime ? 'Testing…' : 'Test realtime access' }}</button>
        </div>
        <p v-if="realtimeResult" class="sec-note">{{ realtimeResult }}</p>
        <p v-if="settingsStore.error" class="sec-error">{{ settingsStore.error }}</p>
      </section>

      <!-- ═══ Connections ═══ -->
      <section class="d2-card sec">
        <header class="sec-head">
          <h3>Connections</h3>
          <span class="mono sec-meta">device-code sign-in · a green badge means a real call worked</span>
        </header>
        <div v-for="p in providers" :key="p.id" class="row">
          <div class="row-text">
            <div class="row-title">{{ p.label }}</div>
            <div class="row-sub">{{ p.sub }}</div>
            <div v-if="p.state.deviceCode" class="device-code">
              Enter <strong class="mono">{{ p.state.deviceCode }}</strong> at
              <a :href="p.state.verificationUri ?? '#'" target="_blank" rel="noopener">{{ p.state.verificationUri }}</a>
              — he waits and completes on his own.
            </div>
          </div>
          <span class="row-val" :class="statusClass(p.state.status)">{{ statusLabel(p.state.status) }}</span>
          <button v-if="p.state.status !== 'ok'" class="d2-ghost-btn" :disabled="p.state.authPending" @click="p.connect()">
            {{ p.state.authPending ? 'Waiting…' : 'Connect' }}
          </button>
          <template v-else>
            <button class="d2-ghost-btn" title="One real call, so a green badge means something" @click="connections.testProvider(p.id)">Test</button>
            <button class="d2-ghost-btn" title="Revoke the stored token" @click="connections.disconnect(p.id)">Disconnect</button>
          </template>
        </div>
        <!-- Slack is a pasted bot token, not a device code. -->
        <div class="row">
          <div class="row-text">
            <div class="row-title">Slack</div>
            <div class="row-sub">
              Messages and channels ·
              <a href="https://api.slack.com/apps" target="_blank" rel="noopener">create an app</a>,
              install it to the workspace, paste the Bot User OAuth Token.
            </div>
          </div>
          <span class="row-val" :class="statusClass(slackState.status)">{{ statusLabel(slackState.status) }}</span>
          <template v-if="slackState.status !== 'ok'">
            <input v-model="slackToken" type="password" class="d2-field row-field" placeholder="xoxb-…"
                   autocomplete="off" aria-label="Slack bot token">
            <button class="d2-ghost-btn" :disabled="!slackToken.trim() || slackState.authPending"
                    @click="saveSlack">{{ slackState.authPending ? 'Saving…' : 'Save' }}</button>
          </template>
          <template v-else>
            <button class="d2-ghost-btn" title="One real call, so a green badge means something" @click="connections.testProvider('slack')">Test</button>
            <button class="d2-ghost-btn" title="Revoke the stored token" @click="connections.disconnect('slack')">Disconnect</button>
          </template>
        </div>
        <p v-if="slackState.testResult" class="sec-note">Slack: {{ slackState.testResult }}</p>
        <div class="row">
          <div class="row-text">
            <div class="row-title">Spotify / Sonos</div>
            <div class="row-sub">Running on canned data until a token is set — playback needs the connection.</div>
          </div>
          <span class="row-val" :class="musicState === 'ok' ? 'ok' : 'warn'">{{ musicState }}</span>
        </div>
        <p v-for="p in providers.filter(x => x.state.testResult)" :key="p.id + '-test'" class="sec-note">
          {{ p.label }}: {{ p.state.testResult }}
        </p>
      </section>

      <!-- ═══ Capabilities — permissions are settings ═══ -->
      <section class="d2-card sec">
        <header class="sec-head">
          <h3>Capabilities</h3>
          <span class="mono sec-meta">what he is able to do at all</span>
        </header>
        <div v-for="c in caps.capabilities" :key="c.key" class="row">
          <div class="row-text">
            <div class="row-title">{{ c.label }}</div>
            <div class="row-sub">{{ c.description }}</div>
          </div>
          <span v-if="c.key === 'app_launch' && caps.allowedApps.length" class="row-val warn">limited to {{ caps.allowedApps.length }} apps</span>
          <button
            class="switch" :class="{ on: c.enabled }" :aria-pressed="c.enabled"
            :aria-label="c.label" @click="caps.toggle(c.key, !c.enabled)"
          ><span class="knob" /></button>
        </div>
        <p v-if="caps.notice" class="sec-note">{{ caps.notice }}</p>
      </section>

      <!-- ═══ Privacy & permissions ═══ -->
      <section class="d2-card sec">
        <header class="sec-head">
          <h3>Privacy &amp; permissions</h3>
          <span class="mono sec-meta">vault · remembered decisions</span>
        </header>
        <div class="row">
          <div class="row-text">
            <div class="row-title">Vault</div>
            <div class="row-sub">Profiles, faces and memory, encrypted on this laptop (AES-256).</div>
          </div>
          <span class="row-val" :class="knowledge.omkLoaded ? 'ok' : 'warn'">
            {{ knowledge.omkLoaded ? 'encrypted · unlocked' : 'not set up' }}
          </span>
        </div>
        <div v-if="!knowledge.omkLoaded" class="row">
          <div class="row-text">
            <div class="row-title">Set a passphrase</div>
            <div class="row-sub">There is no recovery. Forget it and the profiles are gone — which is the point.</div>
          </div>
          <input v-model="passphrase" type="password" class="d2-field row-field" placeholder="At least 8 characters" aria-label="Vault passphrase">
          <button class="d2-primary-btn" :disabled="passphrase.length < 8 || securing" @click="securePassphrase">
            {{ securing ? 'Encrypting…' : 'Encrypt' }}
          </button>
        </div>
        <p v-if="secureResult" class="sec-note">{{ secureResult }}</p>
        <div class="row">
          <div class="row-text">
            <div class="row-title">Remembered decisions</div>
            <div class="row-sub">Tools you told him to always allow. Revoke any of them here.</div>
          </div>
          <div class="auto-chips">
            <span v-for="t in caps.autoApproved" :key="t" class="auto-chip mono">
              {{ t }}
              <button aria-label="Revoke" class="chip-x" @click="caps.revokeAuto(t)">✕</button>
            </span>
            <span v-if="!caps.autoApproved.length" class="row-sub">None — every sensitive action still asks.</span>
          </div>
        </div>
      </section>

      <!-- ═══ Voice & wake word ═══ -->
      <section class="d2-card sec">
        <header class="sec-head">
          <h3>Voice &amp; wake word</h3>
          <span class="mono sec-meta">listening happens on the device</span>
        </header>
        <div class="row">
          <div class="row-text">
            <div class="row-title">Assistant name</div>
            <div class="row-sub">Used in greetings, the wake word and the header.</div>
          </div>
          <input :value="prefs.assistantName" maxlength="24" class="d2-field row-field" aria-label="Assistant name"
                 @change="prefs.save({ assistant_name: ($event.target as HTMLInputElement).value })">
        </div>
        <div class="row">
          <div class="row-text">
            <div class="row-title">Hands-free voice</div>
            <div class="row-sub">Off means he only listens when you press Talk.</div>
          </div>
          <button
            class="switch" :class="{ on: prefs.voiceMode === 'wake_word' }" :aria-pressed="prefs.voiceMode === 'wake_word'"
            aria-label="Hands-free voice" @click="prefs.save({ voice_mode: prefs.voiceMode === 'wake_word' ? 'off' : 'wake_word' })"
          ><span class="knob" /></button>
        </div>
        <div v-if="prefs.voiceMode === 'wake_word'" class="row">
          <div class="row-text">
            <div class="row-title">Wake word</div>
            <div class="row-sub">Two or three syllables work best; short words trigger by accident.</div>
          </div>
          <input :value="prefs.wakeWord" maxlength="24" class="d2-field row-field" aria-label="Wake word"
                 @change="prefs.save({ wake_word: ($event.target as HTMLInputElement).value })">
        </div>
        <div class="row">
          <div class="row-text">
            <div class="row-title">Voice</div>
            <div class="row-sub">The default voice — modes can override it in Modes.</div>
          </div>
          <select :value="prefs.ttsVoice" class="d2-field row-field" aria-label="Voice"
                  @change="prefs.save({ tts_voice: ($event.target as HTMLSelectElement).value })">
            <option v-for="v in TTS_VOICES" :key="v" :value="v">{{ v }}</option>
          </select>
        </div>
        <div class="row">
          <div class="row-text">
            <div class="row-title">Reply language</div>
            <div class="row-sub">Automatic answers each person in the language they used.</div>
          </div>
          <select :value="prefs.language" class="d2-field row-field" aria-label="Reply language"
                  @change="prefs.save({ language: ($event.target as HTMLSelectElement).value as Language })">
            <option v-for="l in LANGUAGES" :key="l.id" :value="l.id">{{ l.label }}</option>
          </select>
        </div>
      </section>

      <!-- ═══ Appearance ═══ -->
      <section class="d2-card sec">
        <header class="sec-head">
          <h3>Appearance</h3>
          <span class="mono sec-meta">theme · detail level</span>
        </header>
        <div class="row">
          <div class="row-text">
            <div class="row-title">Theme</div>
            <div class="row-sub">Light is warm paper; dark is deep evergreen.</div>
          </div>
          <select v-model="themeStore.theme" class="d2-field row-field" aria-label="Theme">
            <option value="light">light</option>
            <option value="dark">dark</option>
          </select>
        </div>
        <div class="row">
          <div class="row-text">
            <div class="row-title">Detail level per person</div>
            <div class="row-sub">Calm for kids and guests, Standard for family, Full for the owner — until the dial is set by hand.</div>
          </div>
          <span class="row-val" :class="prefs.densityTouched ? '' : 'ok'">{{ prefs.densityTouched ? `by hand · ${prefs.density}` : 'automatic' }}</span>
          <button v-if="prefs.densityTouched" class="d2-ghost-btn" @click="prefs.resetDensityTouch()">Back to automatic</button>
        </div>
      </section>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { BRAIN_URL } from '../lib/endpoints'
import { useCapabilitiesStore } from '../stores/capabilitiesStore'
import { useConnectionsStore } from '../stores/connectionsStore'
import { useKnowledgeStore } from '../stores/knowledgeStore'
import { LANGUAGES, usePrefsStore, type Language } from '../stores/prefsStore'
import { useSettingsStore, type LLMProvider } from '../stores/settingsStore'
import { useThemeStore } from '../stores/themeStore'

const settingsStore = useSettingsStore()
const connections = useConnectionsStore()
const caps = useCapabilitiesStore()
const knowledge = useKnowledgeStore()
const prefs = usePrefsStore()
const themeStore = useThemeStore()

const TTS_VOICES = ['alloy', 'ash', 'ballad', 'coral', 'echo', 'fable', 'onyx', 'nova', 'sage', 'shimmer', 'verse']

// ── Intelligence ───────────────────────────────────────────────────────────
const keySet = computed(() => {
  const p = settingsStore.provider
  return p === 'openai' ? settingsStore.openaiKeySet
    : p === 'openrouter' ? settingsStore.openrouterKeySet
      : p === 'gemini' ? settingsStore.geminiKeySet : true
})
const keyPlaceholder = computed(() =>
  keySet.value ? '••••••••••••'
    : settingsStore.provider === 'openai' ? 'sk-…'
      : settingsStore.provider === 'gemini' ? 'AIza…' : 'sk-or-…')
const newKey = ref('')
const savingKey = ref(false)
async function saveKey(): Promise<void> {
  savingKey.value = true
  try {
    const field = `${settingsStore.provider}_api_key`
    const r = await fetch(`${BRAIN_URL}/setup/config`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ [field]: newKey.value.trim() }),
    })
    if (r.ok) { newKey.value = ''; await settingsStore.fetchConfig() }
  } finally { savingKey.value = false }
}
function onProviderChange(): void {
  settingsStore.fetchModels(settingsStore.provider)
  settingsStore.applyConfig(settingsStore.provider as LLMProvider, '')
}
function applyModel(): void {
  settingsStore.applyConfig(settingsStore.provider as LLMProvider, settingsStore.model)
}
function saveEngine(e: Event): void {
  prefs.save({ voice_engine: (e.target as HTMLSelectElement).value as 'pipeline' | 'realtime' })
}
// ── Model roles (U90/U202) — stored in /setup/prefs, OpenAI only ───────────
type RoleField = 'chat_model' | 'realtime_model' | 'agent_model' | 'computer_use_model'
const MODEL_ROLES: { field: RoleField; label: string; sub: string; kind: string }[] = [
  { field: 'chat_model', label: 'Conversation model', sub: 'Fast replies, typed and spoken', kind: 'chat' },
  { field: 'realtime_model', label: 'Voice model', sub: 'Speech-to-speech (realtime)', kind: 'realtime' },
  { field: 'agent_model', label: 'Tasks & tools model', sub: 'Multi-step work — Spotify, computer use', kind: 'chat' },
  { field: 'computer_use_model', label: 'Screen control model', sub: 'Drives the mouse and keyboard', kind: 'vision' },
]
const roles = ref<Record<RoleField, string>>({ chat_model: '', realtime_model: '', agent_model: '', computer_use_model: '' })
const rolesSaved = ref(false)
// U191: the brain tags models with the roles they can fill; older brains send
// no `kinds` — infer from the id so voice models stay out of the chat rows.
function kindsOf(m: { id: string; kinds?: string[] }): string[] {
  if (m.kinds?.length) return m.kinds
  const low = m.id.toLowerCase()
  return (low.includes('realtime') || low.includes('-audio')) ? ['realtime'] : ['chat', 'vision']
}
/** A saved model that the provider no longer lists stays visible — opening
 *  settings must never silently drop a working configuration. */
function roleOptions(kind: string, current: string) {
  const list = settingsStore.models.filter(m => kindsOf(m).includes(kind))
  const id = (current || '').trim()
  if (!id || list.some(m => m.id === id)) return list
  return [{ id, name: `${id} (not in the provider's list)`, free: false }, ...list]
}
async function fetchModelRoles(): Promise<void> {
  try {
    const d = await (await fetch(`${BRAIN_URL}/setup/prefs`)).json()
    for (const { field } of MODEL_ROLES) roles.value[field] = d[field] ?? ''
  } catch { /* brain offline — the selects just start empty */ }
}
async function saveModelRoles(): Promise<void> {
  rolesSaved.value = false
  const body: Record<string, string> = {}
  for (const { field } of MODEL_ROLES) body[field] = roles.value[field].trim()
  try {
    const r = await fetch(`${BRAIN_URL}/setup/prefs`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    rolesSaved.value = r.ok
  } catch { /* shown as not-saved */ }
}

const testingRealtime = ref(false)
const realtimeResult = ref('')
async function testRealtime(): Promise<void> {
  testingRealtime.value = true
  realtimeResult.value = ''
  try {
    const r = await fetch(`${BRAIN_URL}/voice/realtime-check`, { method: 'POST' })
    const body = await r.json().catch(() => ({}))
    realtimeResult.value = body.detail ?? body.result ?? (r.ok ? 'Realtime access works.' : `Check failed (${r.status})`)
  } catch { realtimeResult.value = 'Could not reach the brain.' } finally { testingRealtime.value = false }
}

// ── Connections ────────────────────────────────────────────────────────────
const providers = computed(() => [
  {
    id: 'microsoft' as const, label: 'Microsoft 365', sub: 'Mail, calendar, todos, Teams',
    state: connections.providers.find(p => p.provider === 'microsoft') ?? blank(),
    connect: () => connections.startMicrosoftAuth(),
  },
  {
    id: 'google' as const, label: 'Google', sub: 'Calendar and mail · sign in with a device code',
    state: connections.providers.find(p => p.provider === 'google') ?? blank(),
    connect: () => connections.startGoogleAuth(),
  },
  {
    id: 'github' as const, label: 'GitHub', sub: 'Repos, issues, PR review',
    state: connections.providers.find(p => p.provider === 'github') ?? blank(),
    connect: () => connections.startGitHubAuth(),
  },
])
function blank() {
  return { provider: 'microsoft', label: '', status: 'unknown', authPending: false } as never
}
const musicState = computed(() =>
  connections.providers.find(p => p.provider === 'music')?.status ?? 'unknown')
const slackState = computed(() =>
  connections.providers.find(p => p.provider === 'slack')
  ?? ({ status: 'unknown', authPending: false, testResult: '' } as never))
const slackToken = ref('')
async function saveSlack(): Promise<void> {
  await connections.saveToken('slack', slackToken.value.trim())
  slackToken.value = ''
}
function statusLabel(s: string): string {
  return s === 'ok' ? 'connected' : s === 'mock' ? 'canned data' : s === 'unauthenticated' ? 'not connected' : s
}
function statusClass(s: string): string {
  return s === 'ok' ? 'ok' : s === 'unknown' ? '' : 'warn'
}

// ── Privacy ────────────────────────────────────────────────────────────────
const passphrase = ref('')
const securing = ref(false)
const secureResult = ref('')
async function securePassphrase(): Promise<void> {
  securing.value = true
  secureResult.value = ''
  const ok = await knowledge.secure(passphrase.value, true)
  secureResult.value = ok
    ? 'Encrypted — profiles, faces and memory are locked to this passphrase now.'
    : (knowledge.error ?? 'Encryption failed.')
  await knowledge.fetchTier()
  passphrase.value = ''
  securing.value = false
}

// Every section loads INDEPENDENTLY. They used to sit in one arrow function,
// so the first line that threw took the other six with it — a single wrong
// method name left Connections, Capabilities, the vault state and the voice
// prefs all silently empty, which reads as "the backend is down" rather than
// "one call is wrong". A section that cannot load is one grey row, not six.
onMounted(() => {
  const load: [string, () => unknown][] = [
    ['llm', () => settingsStore.fetchConfig().then(() => settingsStore.fetchModels(settingsStore.provider))],
    ['model roles', fetchModelRoles],
    // refreshAllStatuses does connector health AND identity in one pass; the
    // two halves are not exported separately.
    ['connections', () => connections.refreshAllStatuses()],
    ['capabilities', () => caps.fetchCapabilities()],
    ['auto-approvals', () => caps.fetchAutoApprovals()],
    ['vault', () => knowledge.fetchTier()],
    ['prefs', () => prefs.fetchPrefs()],
  ]
  for (const [what, fn] of load) {
    try {
      Promise.resolve(fn()).catch(e => console.warn(`settings: ${what} failed`, e))
    } catch (e) { console.warn(`settings: ${what} failed`, e) }
  }
})
watch(() => themeStore.theme, () => { /* persisted by the store's own watcher */ })
</script>

<style scoped>
.settings-inner { max-width: 840px; }
.mono { font-family: var(--font-mono); }
.settings-inner h2 { margin: 0 0 3px; font-size: 19px; }
.lead { margin: 0 0 18px; font-size: 13.5px; color: var(--ink-2); }

.sec { border-radius: 12px; margin-bottom: 11px; overflow: hidden; }
.sec-head { display: flex; align-items: baseline; gap: 10px; padding: 12px 16px 8px; }
.sec-head h3 { margin: 0; font-size: 14.5px; }
.sec-meta { font-size: 10.5px; color: var(--ink-3); }
.row { display: flex; align-items: center; gap: 12px; padding: 9px 16px; border-top: 1px solid var(--line); flex-wrap: wrap; }
.row-text { flex: 1; min-width: 200px; }
.row-title { font-size: 13.5px; font-weight: 600; }
.row-sub { font-size: 12px; color: var(--ink-3); margin-top: 1px; }
.row-field { width: auto; flex: 0 1 220px; min-width: 140px; }
.row-val { font-size: 12.5px; font-weight: 600; color: var(--ink-3); flex-shrink: 0; }
.row-val.ok { color: var(--ok); }
.row-val.warn { color: var(--warn); }
.sec-note { margin: 0; padding: 8px 16px 12px; font-size: 12.5px; color: var(--ink-2); }
.sec-error { margin: 0; padding: 8px 16px 12px; font-size: 12.5px; color: var(--danger); }

.device-code {
  margin-top: 6px; font-size: 12.5px; color: var(--info);
  background: var(--info-wash); border-radius: 8px; padding: 6px 10px;
}
.device-code a { color: var(--info); }

.switch {
  position: relative; width: 44px; height: 25px; border-radius: 999px;
  flex-shrink: 0; cursor: pointer; border: none; padding: 0; background: var(--line-strong);
}
.switch.on { background: var(--accent); }
.knob {
  position: absolute; top: 3px; left: 3px; width: 19px; height: 19px;
  border-radius: 50%; background: #fff; transition: left 0.15s;
}
.switch.on .knob { left: 22px; }

.auto-chips { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
.auto-chip {
  display: inline-flex; align-items: center; gap: 6px; font-size: 11.5px;
  padding: 3px 9px; border-radius: 999px; background: var(--warn-wash); color: var(--warn);
}
.chip-x { background: none; border: none; color: inherit; cursor: pointer; padding: 0; font-size: 11px; }
</style>
