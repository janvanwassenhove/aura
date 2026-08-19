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
            <div class="row-title">
              {{ p.label }}
              <span v-if="p.state.domains?.length" class="mono dom">{{ p.state.domains.join(' · ') }}</span>
            </div>
            <!-- The brain composes this sentence, so the page and the assistant
                 can never disagree about what is true. -->
            <div class="row-sub">{{ p.state.detail || p.sub }}</div>
            <div v-if="p.state.nextStep && p.state.status !== 'ok'" class="row-next">
              → {{ p.state.nextStep }}
            </div>
            <div v-if="p.state.deviceCode" class="device-code">
              Enter <strong class="mono">{{ p.state.deviceCode }}</strong> at
              <a :href="p.state.verificationUri ?? '#'" target="_blank" rel="noopener">{{ p.state.verificationUri }}</a>
              — he waits and completes on his own.
            </div>
            <div v-if="p.state.error" class="sec-error">{{ p.state.error }}</div>
          </div>
          <span class="row-val" :class="statusClass(p.state.status)">{{ statusLabel(p.state.status) }}</span>
          <!-- Switching on is the FIRST step and belongs on every row, so an
               off connector is one click from being reachable. -->
          <button
            class="switch" :class="{ on: p.state.enabled !== false }"
            :aria-pressed="p.state.enabled !== false" :aria-label="`Use ${p.label}`"
            :title="p.state.enabled === false ? `Switch ${p.label} on` : `Switch ${p.label} off — he stops using it`"
            @click="connections.setEnabled(p.id, p.state.enabled === false)"
          ><span class="knob" /></button>
          <template v-if="p.state.enabled !== false && !p.state.missing?.length">
            <template v-if="p.tokenField && p.state.status !== 'ok'">
              <input v-model="tokens[p.id]" type="password" class="d2-field row-field"
                     :placeholder="p.tokenField.placeholder" autocomplete="off"
                     :aria-label="`${p.label} token`">
              <button class="d2-ghost-btn" :disabled="!tokens[p.id]?.trim() || p.state.authPending"
                      @click="saveToken(p.id)">{{ p.state.authPending ? 'Saving…' : 'Save' }}</button>
            </template>
            <button v-else-if="p.state.status !== 'ok'" class="d2-ghost-btn" :disabled="p.state.authPending" @click="p.connect()">
              {{ p.state.authPending ? 'Waiting…' : 'Connect' }}
            </button>
            <template v-else>
              <button class="d2-ghost-btn" title="One real call, so a green badge means something" @click="connections.testProvider(p.id)">Test</button>
              <button class="d2-ghost-btn" title="Revoke the stored token" @click="connections.disconnect(p.id)">Disconnect</button>
            </template>
          </template>
        </div>
        <p v-if="connections.liveDomains.length" class="sec-note">
          He can currently answer about:
          <strong>{{ connections.liveDomains.join(', ') }}</strong>.
          Anything else he will say he cannot reach, instead of trying and failing.
        </p>
        <p v-for="p in providers.filter(x => x.state.testResult)" :key="p.id + '-test'" class="sec-note">
          {{ p.label }}: {{ p.state.testResult }}
        </p>
      </section>

      <!-- ═══ Added tools (MCP) ═══ -->
      <section class="d2-card sec">
        <header class="sec-head">
          <h3>Added tools</h3>
          <span class="mono sec-meta">MCP servers · adding is not switching on</span>
        </header>

        <div v-for="srv in mcp.servers" :key="srv.name" class="row">
          <div class="row-text">
            <div class="row-title">
              {{ srv.name }}
              <span class="mono dom">{{ srv.tools.length }} tool{{ srv.tools.length === 1 ? '' : 's' }}</span>
            </div>
            <div class="row-sub mono">{{ srv.url }}</div>
            <div v-if="srv.last_error" class="sec-error">{{ srv.last_error }}</div>
            <div v-else-if="!srv.tools.length" class="row-next">
              → Nothing discovered yet. Press Refresh to ask the server what it offers.
            </div>
            <!-- Show WHAT you are switching on, before you switch it on. -->
            <div v-else class="tool-list">
              <span v-for="t in srv.tools" :key="t.name" class="tool-pill mono" :title="t.description">{{ t.name }}</span>
            </div>
          </div>
          <span class="row-val" :class="srv.enabled ? 'ok' : ''">{{ srv.enabled ? 'on' : 'off' }}</span>
          <button
            class="switch" :class="{ on: srv.enabled }" :aria-pressed="srv.enabled"
            :disabled="!srv.tools.length"
            :aria-label="`Use ${srv.name}`"
            :title="srv.tools.length ? `Switch ${srv.name} on — its tools stop for your approval` : 'Discover its tools first'"
            @click="mcp.setEnabled(srv.name, !srv.enabled)"
          ><span class="knob" /></button>
          <button class="d2-ghost-btn" :disabled="mcp.busy" @click="mcp.refresh(srv.name)">Refresh</button>
          <button class="d2-ghost-btn" title="Remove this server and its tools" @click="removeServer(srv.name)">Remove</button>
        </div>

        <div class="row">
          <div class="row-text">
            <div class="row-title">Add a server</div>
            <div class="row-sub">
              Any MCP server with an HTTP endpoint. Its tools are discovered first;
              you decide afterwards whether he may use them.
            </div>
          </div>
          <input v-model="draft.name" class="d2-field row-field" placeholder="name (e.g. wiki)" aria-label="Server name">
          <input v-model="draft.url" class="d2-field row-field" placeholder="https://…/mcp" aria-label="Server URL">
          <select v-model="draft.authType" class="d2-field row-field" aria-label="Authentication">
            <option value="none">no auth</option>
            <option value="bearer">bearer token</option>
            <option value="api_key">API key</option>
          </select>
          <input v-if="draft.authType !== 'none'" v-model="draft.secret" type="password"
                 class="d2-field row-field" placeholder="token" autocomplete="off" aria-label="Token">
          <button class="d2-primary-btn" :disabled="!draft.name.trim() || !draft.url.trim() || mcp.busy"
                  @click="addServer">{{ mcp.busy ? 'Asking…' : 'Add' }}</button>
        </div>

        <p v-if="mcp.error" class="sec-error">{{ mcp.error }}</p>
        <p class="sec-note">
          Added tools always stop for your approval before they run — they were
          written by someone else. Change that per mode under
          <strong>Modes › {{ mcp.group }}</strong>.
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
import { useMcpStore } from '../stores/mcpStore'
import { useThemeStore } from '../stores/themeStore'

const settingsStore = useSettingsStore()
const connections = useConnectionsStore()
const caps = useCapabilitiesStore()
const knowledge = useKnowledgeStore()
const prefs = usePrefsStore()
const themeStore = useThemeStore()
const mcp = useMcpStore()

// ── Added tools (MCP) ──────────────────────────────────────────────────────
const draft = ref({ name: '', url: '', authType: 'none', secret: '' })
async function addServer(): Promise<void> {
  const ok = await mcp.add(draft.value.name, draft.value.url,
                           draft.value.authType, draft.value.secret)
  if (ok) draft.value = { name: '', url: '', authType: 'none', secret: '' }
}
function removeServer(name: string): void {
  if (window.confirm(`Remove ${name}? Its tools disappear with it.`)) mcp.remove(name)
}

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
  {
    // Slack signs in with a pasted bot token rather than a device code, so the
    // row shows a field instead of a Connect button — one list, one shape.
    id: 'slack' as const, label: 'Slack', sub: 'Messages and channels',
    state: connections.providers.find(p => p.provider === 'slack') ?? blank(),
    connect: () => {},
    tokenField: { placeholder: 'xoxb-…' },
  },
])
function blank() {
  return { provider: 'microsoft', label: '', status: 'unknown', authPending: false } as never
}
const musicState = computed(() =>
  connections.providers.find(p => p.provider === 'music')?.status ?? 'unknown')
// Token-based connectors (Slack today) hold their pasted secret here only
// until it is sent; it is never read back from the brain.
const tokens = ref<Record<string, string>>({})
async function saveToken(id: 'github' | 'slack'): Promise<void> {
  const value = (tokens.value[id] ?? '').trim()
  if (!value) return
  await connections.saveToken(id, value)
  tokens.value[id] = ''
  await connections.refreshAllStatuses()
}
const STATUS_LABELS: Record<string, string> = {
  ok: 'connected',
  mock: 'canned data',
  unauthenticated: 'not signed in',
  not_enabled: 'off',
  no_credentials: 'needs an app',
  unavailable: 'failed to start',
}
function statusLabel(s: string): string {
  return STATUS_LABELS[s] ?? s
}
function statusClass(s: string): string {
  if (s === 'ok') return 'ok'
  if (s === 'not_enabled' || s === 'unknown') return ''   // off is not a fault
  return 'warn'
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
    ['added tools', () => mcp.fetchServers()],
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

.dom {
  font-size: 10px; color: var(--ink-3); margin-left: 7px;
  text-transform: uppercase; letter-spacing: 0.04em;
}
.tool-list { display: flex; gap: 5px; flex-wrap: wrap; margin-top: 5px; }
.tool-pill {
  font-size: 10.5px; padding: 2px 8px; border-radius: 999px;
  background: var(--sunken); color: var(--ink-2); border: 1px solid var(--line);
}
.row-next { font-size: 12px; color: var(--info); margin-top: 3px; }
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
