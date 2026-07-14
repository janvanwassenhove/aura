<template>
  <div class="settings-overlay" @click.self="$emit('close')">
    <div class="settings-modal" :class="{ 'settings-modal--wide': activeTab === 'connections' }">
      <div class="settings-header">
        <span class="settings-title"><Settings :size="15" /> Settings</span>
        <button class="btn-close" @click="$emit('close')"><X :size="15" /></button>
      </div>

      <!-- Tab bar -->
      <div class="settings-tabs">
        <button :class="['tab-btn', activeTab === 'llm' && 'tab-btn--active']" @click="activeTab = 'llm'">LLM</button>
        <button :class="['tab-btn', activeTab === 'connections' && 'tab-btn--active']" @click="switchToConnections">Connections</button>
        <button :class="['tab-btn', activeTab === 'appearance' && 'tab-btn--active']" @click="activeTab = 'appearance'">Appearance</button>
      </div>

      <!-- ── LLM tab ── -->
      <template v-if="activeTab === 'llm'">
        <div v-if="llmStore.loading" class="settings-loading">Loading…</div>
        <div v-else class="settings-body">
          <div class="settings-field">
            <label class="field-label" for="llm-provider">Provider</label>
            <select id="llm-provider" v-model="localProvider" class="field-select">
              <option value="openai">OpenAI</option>
              <option value="openrouter">OpenRouter</option>
              <option value="gemini">Google Gemini</option>
              <option value="echo">Echo (test)</option>
            </select>
          </div>

          <div class="settings-badges">
            <span :class="['badge', llmStore.openaiKeySet ? 'badge-ok' : 'badge-warn']">
              <component :is="llmStore.openaiKeySet ? CircleCheck : Circle" :size="12" />
              {{ llmStore.openaiKeySet ? 'OpenAI key set' : 'OpenAI key not configured' }}
            </span>
            <span :class="['badge', llmStore.openrouterKeySet ? 'badge-ok' : 'badge-warn']">
              <component :is="llmStore.openrouterKeySet ? CircleCheck : Circle" :size="12" />
              {{ llmStore.openrouterKeySet ? 'OpenRouter key set' : 'OpenRouter key not configured' }}
            </span>
            <span :class="['badge', llmStore.geminiKeySet ? 'badge-ok' : 'badge-warn']">
              <component :is="llmStore.geminiKeySet ? CircleCheck : Circle" :size="12" />
              {{ llmStore.geminiKeySet ? 'Gemini key set' : 'Gemini key not configured' }}
            </span>
          </div>

          <div v-if="localProvider !== 'echo'" class="settings-field">
            <label class="field-label" for="llm-model">
              Model
              <LoaderCircle v-if="llmStore.modelsLoading" :size="11" class="spinner" />
            </label>
            <select v-if="llmStore.models.length > 0" id="llm-model" v-model="localModel" class="field-select">
              <option value="">— select a model —</option>
              <optgroup v-if="freeModels.length > 0" label="Free">
                <option v-for="m in freeModels" :key="m.id" :value="m.id">{{ m.name }}</option>
              </optgroup>
              <optgroup v-if="paidModels.length > 0" label="Paid">
                <option v-for="m in paidModels" :key="m.id" :value="m.id">{{ m.name }}</option>
              </optgroup>
            </select>
            <input v-else id="llm-model" v-model="localModel" type="text" class="field-input" :placeholder="modelPlaceholder" />
          </div>

          <p v-if="llmStore.error" class="settings-error">{{ llmStore.error }}</p>
          <p v-if="llmStore.successMessage" class="settings-success">{{ llmStore.successMessage }}</p>
        </div>

        <div class="settings-actions">
          <button class="btn-cancel" @click="$emit('close')">Cancel</button>
          <button class="btn-apply" :disabled="llmStore.loading" @click="applyLLM">Apply</button>
        </div>
      </template>

      <!-- ── Appearance tab ── -->
      <template v-if="activeTab === 'appearance'">
        <div class="settings-body">
          <div class="settings-field">
            <label class="field-label" for="assistant-name">Assistant name</label>
            <input id="assistant-name" v-model="localName" class="field-input" maxlength="24" placeholder="AURA" />
            <p class="conn-hint">The name you call it — used in greetings and its replies.</p>
          </div>
          <div class="settings-field">
            <label class="field-label" for="assistant-lang">Language</label>
            <select id="assistant-lang" v-model="localLang" class="field-select">
              <option v-for="l in LANGUAGES" :key="l.id" :value="l.id">{{ l.label }}</option>
            </select>
          </div>
          <div>
            <button class="btn-apply" :disabled="prefsStore.saving" @click="savePrefs">
              {{ prefsStore.saving ? 'Saving…' : 'Save' }}
            </button>
            <span v-if="prefsSaved" class="settings-success" style="margin-left:0.6rem">Saved</span>
            <span v-if="prefsStore.error" class="settings-error">{{ prefsStore.error }}</span>
          </div>

          <hr class="settings-divider" />

          <div class="settings-field">
            <label class="field-label">Theme</label>
            <div class="theme-row">
              <button :class="['theme-btn', themeStore.theme === 'dark' && 'theme-btn--active']" @click="themeStore.theme = 'dark'">
                <Moon :size="14" /> Dark
              </button>
              <button :class="['theme-btn', themeStore.theme === 'light' && 'theme-btn--active']" @click="themeStore.theme = 'light'">
                <Sun :size="14" /> Light
              </button>
            </div>
          </div>
          <div class="settings-field">
            <label class="field-label">Accent</label>
            <div class="theme-row">
              <button
                v-for="a in ACCENTS" :key="a.id"
                :class="['accent-swatch', `accent-swatch--${a.id}`, themeStore.accent === a.id && 'accent-swatch--active']"
                :title="a.label"
                @click="themeStore.accent = a.id"
              />
            </div>
          </div>
          <p class="conn-hint">Preferences are saved on this device.</p>
        </div>
      </template>

      <!-- ── Connections tab ── -->
      <template v-if="activeTab === 'connections'">
        <!-- User ID row -->
        <div class="conn-user-row">
          <label class="field-label" for="conn-user-id">User ID</label>
          <input id="conn-user-id" v-model="connStore.userId" class="field-input conn-user-input"
            placeholder="default" @change="connStore.refreshAllStatuses()" />
          <button class="btn-refresh" :disabled="connStore.loading" title="Refresh" @click="connStore.refreshAllStatuses()">
            <RefreshCw :size="14" :class="connStore.loading ? 'spinner' : ''" />
          </button>
        </div>

        <div class="conn-list">

          <!-- ── Microsoft M365 ── -->
          <div class="conn-card">
            <div class="conn-card-header">
              <div class="conn-provider-info"><span class="conn-icon"><Building2 :size="16" /></span><span class="conn-name">Microsoft M365</span></div>
              <ConnStatusBadge :status="msState.status" />
            </div>
            <p v-if="msState.error" class="conn-error">{{ msState.error }}</p>

            <div v-if="msState.deviceCode" class="device-code-box">
              <p class="device-code-hint">1. Go to <a :href="msState.verificationUri" target="_blank" class="device-link">{{ msState.verificationUri }}</a></p>
              <p class="device-code-hint">2. Enter this code:</p>
              <div class="device-code-value">{{ msState.deviceCode }}</div>
              <p class="device-code-hint">3. Sign in, then click <strong>Done</strong>.</p>
              <div class="conn-actions">
                <button class="btn-conn btn-primary" :disabled="msState.authPending" @click="connStore.pollMicrosoftAuth()">
                  <LoaderCircle v-if="msState.authPending" :size="13" class="spinner" /> Done — I've signed in
                </button>
                <button class="btn-conn btn-ghost" @click="connStore.cancelMicrosoftAuth()">Cancel</button>
              </div>
            </div>

            <div v-else class="conn-actions">
              <button v-if="msState.status !== 'ok'" class="btn-conn btn-primary"
                :disabled="msState.authPending" @click="connStore.startMicrosoftAuth()">
                <LoaderCircle v-if="msState.authPending" :size="13" class="spinner" /> Connect
              </button>
              <button v-else class="btn-conn btn-danger" @click="connStore.disconnect('microsoft')">Disconnect</button>
            </div>
          </div>

          <!-- ── Google Workspace ── -->
          <div class="conn-card">
            <div class="conn-card-header">
              <div class="conn-provider-info"><span class="conn-icon"><Globe :size="16" /></span><span class="conn-name">Google Workspace</span></div>
              <ConnStatusBadge :status="googleState.status" />
            </div>
            <p v-if="googleState.error" class="conn-error">{{ googleState.error }}</p>

            <div v-if="googleState.deviceCode" class="device-code-box">
              <p class="device-code-hint">1. Go to <a :href="googleState.verificationUri" target="_blank" class="device-link">{{ googleState.verificationUri }}</a></p>
              <p class="device-code-hint">2. Enter this code:</p>
              <div class="device-code-value">{{ googleState.deviceCode }}</div>
              <p class="device-code-hint">3. Sign in, then click <strong>Done</strong>.</p>
              <div class="conn-actions">
                <button class="btn-conn btn-primary" :disabled="googleState.authPending" @click="connStore.pollGoogleAuth()">
                  <LoaderCircle v-if="googleState.authPending" :size="13" class="spinner" /> Done — I've signed in
                </button>
                <button class="btn-conn btn-ghost" @click="connStore.cancelGoogleAuth()">Cancel</button>
              </div>
            </div>

            <div v-else class="conn-actions">
              <button v-if="googleState.status !== 'ok'" class="btn-conn btn-primary"
                :disabled="googleState.authPending" @click="connStore.startGoogleAuth()">
                <LoaderCircle v-if="googleState.authPending" :size="13" class="spinner" /> Connect
              </button>
              <button v-else class="btn-conn btn-danger" @click="connStore.disconnect('google')">Disconnect</button>
            </div>
          </div>

          <!-- ── GitHub ── -->
          <div class="conn-card">
            <div class="conn-card-header">
              <div class="conn-provider-info"><span class="conn-icon"><Github :size="16" /></span><span class="conn-name">GitHub</span></div>
              <ConnStatusBadge :status="githubState.status" />
            </div>
            <p v-if="githubState.error" class="conn-error">{{ githubState.error }}</p>

            <div v-if="githubState.deviceCode" class="device-code-box">
              <p class="device-code-hint">1. Go to <a :href="githubState.verificationUri" target="_blank" class="device-link">{{ githubState.verificationUri }}</a></p>
              <p class="device-code-hint">2. Enter this code:</p>
              <div class="device-code-value">{{ githubState.deviceCode }}</div>
              <p class="device-code-hint">3. Authorize, then click <strong>Done</strong>.</p>
              <div class="conn-actions">
                <button class="btn-conn btn-primary" :disabled="githubState.authPending" @click="connStore.pollGitHubAuth()">
                  <LoaderCircle v-if="githubState.authPending" :size="13" class="spinner" /> Done — I've authorized
                </button>
                <button class="btn-conn btn-ghost" @click="connStore.cancelGitHubAuth()">Cancel</button>
              </div>
            </div>

            <template v-else-if="githubState.status !== 'ok'">
              <div v-if="showGitHubPat" class="settings-field">
                <label class="field-label" for="gh-token">Personal Access Token</label>
                <input id="gh-token" v-model="githubToken" type="password" class="field-input" placeholder="ghp_…" autocomplete="off" />
                <div class="conn-actions">
                  <button class="btn-conn btn-primary" :disabled="!githubToken || githubState.authPending" @click="saveGitHub">
                    <LoaderCircle v-if="githubState.authPending" :size="13" class="spinner" /> Save
                  </button>
                  <button class="btn-conn btn-ghost" @click="showGitHubPat = false">Back</button>
                </div>
              </div>
              <div v-else class="conn-actions">
                <button class="btn-conn btn-primary" :disabled="githubState.authPending" @click="connStore.startGitHubAuth()">
                  <LoaderCircle v-if="githubState.authPending" :size="13" class="spinner" /> Connect
                </button>
                <button class="btn-conn btn-ghost btn-small" @click="showGitHubPat = true">Use PAT instead</button>
              </div>
            </template>
            <div v-else class="conn-actions">
              <button class="btn-conn btn-danger" @click="connStore.disconnect('github')">Disconnect</button>
            </div>
          </div>

          <!-- ── Slack ── -->
          <div class="conn-card">
            <div class="conn-card-header">
              <div class="conn-provider-info"><span class="conn-icon"><MessageSquare :size="16" /></span><span class="conn-name">Slack</span></div>
              <ConnStatusBadge :status="slackState.status" />
            </div>
            <p v-if="slackState.error" class="conn-error">{{ slackState.error }}</p>
            <template v-if="slackState.status !== 'ok'">
              <div class="settings-field">
                <label class="field-label" for="slack-token">
                  Bot Token
                  <a href="https://api.slack.com/apps" target="_blank" class="setup-link setup-link--inline">Create app <ExternalLink :size="10" /></a>
                </label>
                <input id="slack-token" v-model="slackToken" type="password" class="field-input" placeholder="xoxb-…" autocomplete="off" />
                <p class="conn-hint">Create a Slack app → <em>OAuth &amp; Permissions</em> → install to workspace → copy the <strong>Bot User OAuth Token</strong>.</p>
              </div>
              <div class="conn-actions">
                <button class="btn-conn btn-primary" :disabled="!slackToken || slackState.authPending" @click="saveSlack">
                  <LoaderCircle v-if="slackState.authPending" :size="13" class="spinner" /> Save
                </button>
              </div>
            </template>
            <div v-else class="conn-actions">
              <button class="btn-conn btn-danger" @click="connStore.disconnect('slack')">Disconnect</button>
            </div>
          </div>

        </div><!-- /conn-list -->
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, defineComponent, h } from 'vue'
import {
  Building2, Circle, CircleCheck, ExternalLink, Github, Globe, LoaderCircle,
  MessageSquare, Moon, RefreshCw, Settings, Sun, X,
} from 'lucide-vue-next'
import { useSettingsStore, type LLMProvider, type ModelOption } from '../stores/settingsStore'
import { useConnectionsStore, type ConnectorStatus } from '../stores/connectionsStore'
import { ACCENTS, useThemeStore } from '../stores/themeStore'
import { LANGUAGES, usePrefsStore } from '../stores/prefsStore'

defineEmits<{ (e: 'close'): void }>()

// ── LLM store ──
const llmStore = useSettingsStore()
const localProvider = ref<LLMProvider>('openai')
const localModel = ref<string>('')

const modelPlaceholder = computed(() => {
  if (localProvider.value === 'openrouter') return 'e.g. openai/gpt-oss-120b:free'
  if (localProvider.value === 'gemini') return 'e.g. gemini-2.5-flash'
  return 'e.g. gpt-4o-mini'
})
const freeModels = computed<ModelOption[]>(() => llmStore.models.filter(m => m.free))
const paidModels = computed<ModelOption[]>(() => llmStore.models.filter(m => !m.free))

onMounted(async () => {
  await llmStore.fetchConfig()
  localProvider.value = llmStore.provider
  localModel.value = llmStore.model
  await llmStore.fetchModels(localProvider.value)
})
watch(localProvider, async (p) => { localModel.value = ''; await llmStore.fetchModels(p) })

async function applyLLM() {
  const ok = await llmStore.applyConfig(localProvider.value, localModel.value)
  if (ok) setTimeout(() => { llmStore.successMessage = null }, 2000)
}

// ── Connections store ──
const connStore = useConnectionsStore()
const themeStore = useThemeStore()
const prefsStore = usePrefsStore()
const activeTab = ref<'llm' | 'connections' | 'appearance'>('llm')

const localName = ref(prefsStore.assistantName)
const localLang = ref(prefsStore.language)
const prefsSaved = ref(false)

onMounted(async () => {
  await prefsStore.fetchPrefs()
  localName.value = prefsStore.assistantName
  localLang.value = prefsStore.language
})

async function savePrefs() {
  prefsSaved.value = false
  const ok = await prefsStore.save(localName.value.trim() || 'AURA', localLang.value)
  if (ok) { prefsSaved.value = true; setTimeout(() => { prefsSaved.value = false }, 2000) }
}

const msState     = computed(() => connStore.providers.find(p => p.provider === 'microsoft')!)
const googleState = computed(() => connStore.providers.find(p => p.provider === 'google')!)
const githubState = computed(() => connStore.providers.find(p => p.provider === 'github')!)
const slackState  = computed(() => connStore.providers.find(p => p.provider === 'slack')!)

const githubToken = ref('')
const slackToken  = ref('')
const showGitHubPat = ref(false)

async function switchToConnections() {
  activeTab.value = 'connections'
  await connStore.refreshAllStatuses()
}

async function saveGitHub() {
  await connStore.saveToken('github', githubToken.value)
  if (githubState.value.status === 'ok') githubToken.value = ''
}
async function saveSlack() {
  await connStore.saveToken('slack', slackToken.value)
  if (slackState.value.status === 'ok') slackToken.value = ''
}

// ── Inline status badge component ──
const ConnStatusBadge = defineComponent({
  props: { status: { type: String as () => ConnectorStatus, required: true } },
  setup(props) {
    const labels: Record<ConnectorStatus, string> = {
      ok:              'Connected',
      unauthenticated: 'Not connected',
      unavailable:     'Unavailable',
      unknown:         'Unknown',
    }
    return () => h('span', { class: ['conn-status-badge', `conn-status--${props.status}`] }, labels[props.status])
  },
})
</script>

<style scoped>
.settings-overlay {
  position: fixed; inset: 0; z-index: 100;
  background: var(--overlay);
  display: flex; align-items: center; justify-content: center;
}
.settings-modal {
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg);
  width: 26rem; max-width: 95vw; max-height: 90vh;
  display: flex; flex-direction: column;
  box-shadow: var(--shadow-modal);
}
.settings-modal--wide { width: 32rem; }

.settings-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0.875rem 1rem; border-bottom: 1px solid var(--border); flex-shrink: 0;
}
.settings-title { font-weight: 600; font-size: 0.95rem; display: inline-flex; align-items: center; gap: 0.4rem; }
.btn-close {
  background: none; border: none; color: var(--text-muted); cursor: pointer; padding: 0.25rem 0.5rem; display: flex;
}
.btn-close:hover { color: var(--text); }

/* Tabs */
.settings-tabs {
  display: flex; border-bottom: 1px solid var(--border); flex-shrink: 0;
}
.tab-btn {
  flex: 1; padding: 0.5rem 1rem; background: none; border: none;
  color: var(--text-faint); font-size: 0.82rem; cursor: pointer; border-bottom: 2px solid transparent;
}
.tab-btn:hover { color: var(--text); }
.tab-btn--active { color: var(--text); border-bottom-color: var(--accent); }

/* LLM tab */
.settings-loading { padding: 1.5rem 1rem; color: var(--text-muted); text-align: center; font-size: 0.85rem; }
.settings-body { padding: 1rem; display: flex; flex-direction: column; gap: 0.875rem; overflow-y: auto; }
.settings-field { display: flex; flex-direction: column; gap: 0.25rem; }
.field-label { font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; display: block; }
.field-select, .field-input {
  background: var(--surface-3); border: 1px solid var(--border); border-radius: var(--radius-sm);
  color: var(--text); padding: 0.4rem 0.6rem; font-size: 0.875rem; outline: none; width: 100%; box-sizing: border-box;
}
.field-select:focus, .field-input:focus { border-color: var(--accent-border); }
.settings-badges { display: flex; flex-direction: column; gap: 0.3rem; }
.badge { font-size: 0.75rem; display: inline-flex; align-items: center; gap: 0.3rem; }
.badge-ok { color: var(--ok); }
.badge-warn { color: var(--warn); }
.settings-error { font-size: 0.8rem; color: var(--danger-text); margin: 0; }
.settings-success { font-size: 0.8rem; color: var(--ok); margin: 0; }
.settings-actions {
  display: flex; justify-content: flex-end; gap: 0.5rem;
  padding: 0.75rem 1rem; border-top: 1px solid var(--border); flex-shrink: 0;
}
.btn-cancel {
  background: none; border: 1px solid var(--border-strong); border-radius: var(--radius-sm);
  color: var(--text-muted); padding: 0.4rem 0.9rem; cursor: pointer; font-size: 0.875rem;
}
.btn-cancel:hover { border-color: var(--text-faint); color: var(--text); }
.btn-apply {
  background: var(--accent); border: none; border-radius: var(--radius-sm);
  color: var(--on-accent); padding: 0.4rem 0.9rem; cursor: pointer; font-size: 0.875rem;
}
.btn-apply:hover:not(:disabled) { background: var(--accent-hover); }
.btn-apply:disabled { opacity: 0.5; cursor: not-allowed; }

/* Appearance tab */
.theme-row { display: flex; gap: 0.5rem; align-items: center; }
.theme-btn {
  display: inline-flex; align-items: center; gap: 0.35rem;
  background: var(--surface-3); border: 1px solid var(--border); border-radius: var(--radius-sm);
  color: var(--text-muted); padding: 0.4rem 0.9rem; cursor: pointer; font-size: 0.82rem;
}
.theme-btn:hover { color: var(--text); }
.theme-btn--active { border-color: var(--accent); color: var(--text); }
.accent-swatch {
  width: 26px; height: 26px; border-radius: 50%; cursor: pointer;
  border: 2px solid transparent;
}
.accent-swatch--blue { background: #2563eb; }
.accent-swatch--green { background: #16a34a; }
.accent-swatch--purple { background: #9333ea; }
.accent-swatch--amber { background: #d97706; }
.accent-swatch--active { border-color: var(--text); }
.settings-divider { border: none; border-top: 1px solid var(--border); margin: 0.4rem 0; }

/* Connections tab */
.conn-user-row {
  display: flex; align-items: center; gap: 0.5rem;
  padding: 0.5rem 1rem; border-bottom: 1px solid var(--border); flex-shrink: 0;
}
.conn-user-input { flex: 1; font-size: 0.82rem; }
.btn-refresh {
  background: none; border: 1px solid var(--border); border-radius: var(--radius-sm);
  color: var(--text-muted); cursor: pointer; padding: 0.3rem 0.5rem; display: flex; align-items: center;
}
.btn-refresh:hover:not(:disabled) { color: var(--text); }
.btn-refresh:disabled { opacity: 0.4; }

.conn-list { overflow-y: auto; flex: 1; }
.conn-card { padding: 0.875rem 1rem; border-bottom: 1px solid var(--border); }
.conn-card:last-child { border-bottom: none; }

.conn-card-header {
  display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.4rem;
}
.conn-provider-info { display: flex; align-items: center; gap: 0.4rem; }
.conn-icon { display: flex; color: var(--text-muted); }
.conn-name { font-weight: 600; font-size: 0.88rem; }

.conn-status-badge {
  font-size: 0.7rem; padding: 0.12rem 0.45rem; border-radius: 9999px; font-weight: 500;
}
.conn-status--ok            { background: var(--ok-bg); color: var(--ok-text); }
.conn-status--unauthenticated { background: var(--surface-hover); color: var(--text-faint); }
.conn-status--unavailable   { background: var(--danger-bg); color: var(--danger-text); }
.conn-status--unknown       { background: var(--surface-2); color: var(--text-faint); }

.conn-hint { font-size: 0.75rem; color: var(--text-faint); margin: 0.3rem 0 0; }
.conn-hint code { background: var(--surface-3); padding: 0.1rem 0.25rem; border-radius: 3px; }
.conn-error { font-size: 0.78rem; color: var(--danger-text); margin: 0.2rem 0; }

.device-code-box {
  background: var(--surface-3); border: 1px solid var(--border); border-radius: var(--radius);
  padding: 0.65rem 0.85rem; margin: 0.4rem 0 0.5rem;
}
.device-code-hint { font-size: 0.78rem; color: var(--text-muted); margin: 0.15rem 0; }
.device-link { color: var(--accent-soft); text-decoration: underline; }
.device-code-value {
  font-size: 1.35rem; font-weight: 700; letter-spacing: 0.12em; color: var(--text);
  text-align: center; padding: 0.35rem 0; background: var(--surface-2); border-radius: var(--radius-sm); margin: 0.35rem 0;
}
.setup-link { color: var(--accent-soft); text-decoration: underline; }
.setup-link--inline { display: inline-flex; align-items: center; gap: 0.2rem; text-transform: none; letter-spacing: 0; margin-left: 0.4rem; }

.conn-actions { display: flex; gap: 0.4rem; margin-top: 0.4rem; flex-wrap: wrap; }
.btn-conn {
  padding: 0.3rem 0.75rem; border-radius: var(--radius-sm); font-size: 0.8rem;
  cursor: pointer; border: none; display: inline-flex; align-items: center; gap: 0.3rem;
}
.btn-conn:disabled { opacity: 0.45; cursor: not-allowed; }
.btn-primary  { background: var(--accent); color: var(--on-accent); }
.btn-primary:hover:not(:disabled) { background: var(--accent-hover); }
.btn-ghost    { background: var(--surface-2); color: var(--text-muted); border: 1px solid var(--border); }
.btn-ghost:hover { background: var(--surface-hover); color: var(--text); }
.btn-danger   { background: var(--danger-bg); color: var(--danger-text); }
.btn-danger:hover { background: var(--danger-bg-hover); }

.spinner { display: inline-block; animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.btn-small { font-size: 0.72rem; padding: 0.2rem 0.5rem; }
</style>
