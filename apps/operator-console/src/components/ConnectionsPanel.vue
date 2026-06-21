<template>
  <div class="settings-overlay" @click.self="$emit('close')">
    <div class="settings-modal connections-modal">

      <!-- Header -->
      <div class="settings-header">
        <span class="settings-title">🔗 Connections</span>
        <button class="btn-close" @click="$emit('close')">✕</button>
      </div>

      <!-- User ID row -->
      <div class="conn-user-row">
        <label class="field-label" for="conn-user-id">User ID</label>
        <input
          id="conn-user-id"
          v-model="store.userId"
          class="field-input conn-user-input"
          placeholder="default"
          @change="store.fetchStatus()"
        />
        <button class="btn-refresh" title="Refresh status" @click="store.fetchStatus()">⟳</button>
      </div>

      <!-- Provider cards -->
      <div class="conn-list">

        <!-- ── Microsoft M365 ── -->
        <div class="conn-card">
          <div class="conn-card-header">
            <div class="conn-provider-info">
              <span class="conn-icon">🏢</span>
              <span class="conn-name">Microsoft M365</span>
            </div>
            <StatusBadge :status="msState.status" />
          </div>

          <p v-if="msState.error" class="conn-error">{{ msState.error }}</p>

          <!-- Device Code wizard -->
          <template v-if="msState.deviceCode">
            <div class="device-code-box">
              <p class="device-code-instructions">
                1. Go to
                <a :href="msState.verificationUri" target="_blank" class="device-link">
                  {{ msState.verificationUri }}
                </a>
              </p>
              <p class="device-code-instructions">2. Enter the code:</p>
              <div class="device-code-value">{{ msState.deviceCode }}</div>
              <p class="device-code-instructions">3. Sign in, then click <strong>Done</strong>.</p>
            </div>
            <div class="conn-actions">
              <button class="btn-conn btn-primary" :disabled="msState.authPending" @click="pollMs">
                <span v-if="msState.authPending" class="spinner">⟳</span>
                Done — I've signed in
              </button>
              <button class="btn-conn btn-secondary" @click="store.cancelMicrosoftAuth()">Cancel</button>
            </div>
          </template>

          <div v-else class="conn-actions">
            <button
              v-if="msState.status !== 'ok'"
              class="btn-conn btn-primary"
              :disabled="msState.authPending"
              @click="store.startMicrosoftAuth()"
            >
              <span v-if="msState.authPending" class="spinner">⟳</span>
              Connect
            </button>
            <button
              v-if="msState.status === 'ok'"
              class="btn-conn btn-danger"
              @click="store.disconnect('microsoft')"
            >
              Disconnect
            </button>
          </div>
        </div>

        <!-- ── Google Workspace ── -->
        <div class="conn-card">
          <div class="conn-card-header">
            <div class="conn-provider-info">
              <span class="conn-icon">🔵</span>
              <span class="conn-name">Google Workspace</span>
            </div>
            <StatusBadge :status="googleState.status" />
          </div>
          <p v-if="googleState.error" class="conn-error">{{ googleState.error }}</p>
          <p class="conn-hint">
            Opens an OAuth window on the Reachy device. Make sure
            <code>GOOGLE_CLIENT_SECRETS_FILE</code> is configured.
          </p>
          <div class="conn-actions">
            <button
              v-if="googleState.status !== 'ok'"
              class="btn-conn btn-primary"
              :disabled="googleState.authPending"
              @click="store.startGoogleAuth()"
            >
              <span v-if="googleState.authPending" class="spinner">⟳</span>
              Connect
            </button>
            <button
              v-if="googleState.status === 'ok'"
              class="btn-conn btn-danger"
              @click="store.disconnect('google')"
            >
              Disconnect
            </button>
          </div>
        </div>

        <!-- ── GitHub ── -->
        <div class="conn-card">
          <div class="conn-card-header">
            <div class="conn-provider-info">
              <span class="conn-icon">🐙</span>
              <span class="conn-name">GitHub</span>
            </div>
            <StatusBadge :status="githubState.status" />
          </div>
          <p v-if="githubState.error" class="conn-error">{{ githubState.error }}</p>
          <template v-if="githubState.status !== 'ok'">
            <div class="settings-field">
              <label class="field-label" for="gh-token">Personal Access Token</label>
              <input
                id="gh-token"
                v-model="githubToken"
                type="password"
                class="field-input"
                placeholder="ghp_…"
                autocomplete="off"
              />
            </div>
            <div class="conn-actions">
              <button
                class="btn-conn btn-primary"
                :disabled="!githubToken || githubState.authPending"
                @click="saveGitHub"
              >
                <span v-if="githubState.authPending" class="spinner">⟳</span>
                Save token
              </button>
            </div>
          </template>
          <div v-else class="conn-actions">
            <button class="btn-conn btn-danger" @click="store.disconnect('github')">Disconnect</button>
          </div>
        </div>

        <!-- ── Slack ── -->
        <div class="conn-card">
          <div class="conn-card-header">
            <div class="conn-provider-info">
              <span class="conn-icon">💬</span>
              <span class="conn-name">Slack</span>
            </div>
            <StatusBadge :status="slackState.status" />
          </div>
          <p v-if="slackState.error" class="conn-error">{{ slackState.error }}</p>
          <template v-if="slackState.status !== 'ok'">
            <div class="settings-field">
              <label class="field-label" for="slack-token">Bot Token</label>
              <input
                id="slack-token"
                v-model="slackToken"
                type="password"
                class="field-input"
                placeholder="xoxb-…"
                autocomplete="off"
              />
            </div>
            <div class="conn-actions">
              <button
                class="btn-conn btn-primary"
                :disabled="!slackToken || slackState.authPending"
                @click="saveSlack"
              >
                <span v-if="slackState.authPending" class="spinner">⟳</span>
                Save token
              </button>
            </div>
          </template>
          <div v-else class="conn-actions">
            <button class="btn-conn btn-danger" @click="store.disconnect('slack')">Disconnect</button>
          </div>
        </div>

      </div><!-- /conn-list -->
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useConnectionsStore } from '../stores/connectionsStore'

defineEmits<{ close: [] }>()

const store = useConnectionsStore()

const msState     = computed(() => store.providers.find(p => p.provider === 'microsoft')!)
const googleState = computed(() => store.providers.find(p => p.provider === 'google')!)
const githubState = computed(() => store.providers.find(p => p.provider === 'github')!)
const slackState  = computed(() => store.providers.find(p => p.provider === 'slack')!)

const githubToken = ref('')
const slackToken  = ref('')

onMounted(() => store.fetchStatus())

async function pollMs() {
  await store.pollMicrosoftAuth()
}

async function saveGitHub() {
  await store.saveToken('github', githubToken.value)
  if (githubState.value.status === 'ok') githubToken.value = ''
}

async function saveSlack() {
  await store.saveToken('slack', slackToken.value)
  if (slackState.value.status === 'ok') slackToken.value = ''
}

// ── Status badge sub-component (inline, no separate file needed) ──
const StatusBadge = {
  props: { status: String },
  template: `
    <span :class="['status-badge', 'status-' + status]">
      {{ status === 'ok' ? '● Connected' : status === 'unauthenticated' ? '○ Not connected' : status === 'unavailable' ? '✕ Unavailable' : '? Unknown' }}
    </span>
  `,
}
</script>

<style scoped>
/* Re-use styles from SettingsPanel via globals; add connection-specific bits */
.connections-modal { width: 520px; max-height: 85vh; overflow-y: auto; }

.conn-user-row {
  display: flex; align-items: center; gap: 0.5rem;
  padding: 0.5rem 1rem;
  background: #1e293b;
  border-bottom: 1px solid #334155;
}
.conn-user-input { flex: 1; }
.btn-refresh {
  background: none; border: 1px solid #475569; border-radius: 0.25rem;
  color: #94a3b8; cursor: pointer; font-size: 0.9rem; padding: 0.2rem 0.5rem;
}
.btn-refresh:hover { color: #e2e8f0; }

.conn-list { display: flex; flex-direction: column; gap: 0; }

.conn-card {
  padding: 1rem;
  border-bottom: 1px solid #1e293b;
}
.conn-card:last-child { border-bottom: none; }

.conn-card-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 0.5rem;
}
.conn-provider-info { display: flex; align-items: center; gap: 0.5rem; }
.conn-icon { font-size: 1.2rem; }
.conn-name { font-weight: 600; font-size: 0.95rem; }

.status-badge {
  font-size: 0.75rem; padding: 0.15rem 0.55rem; border-radius: 9999px; font-weight: 500;
}
.status-ok          { background: #14532d; color: #86efac; }
.status-unauthenticated { background: #1c1917; color: #78716c; }
.status-unavailable { background: #450a0a; color: #fca5a5; }
.status-unknown     { background: #1e293b; color: #64748b; }

.conn-hint { font-size: 0.78rem; color: #64748b; margin: 0.25rem 0 0.5rem; }
.conn-hint code { background: #1e293b; padding: 0.1rem 0.3rem; border-radius: 3px; font-size: 0.75rem; }
.conn-error { font-size: 0.8rem; color: #f87171; margin: 0.25rem 0; }

.device-code-box {
  background: #0f172a; border: 1px solid #334155; border-radius: 0.375rem;
  padding: 0.75rem 1rem; margin-bottom: 0.75rem;
}
.device-code-instructions { font-size: 0.82rem; color: #94a3b8; margin: 0.2rem 0; }
.device-link { color: #60a5fa; text-decoration: underline; }
.device-code-value {
  font-size: 1.5rem; font-weight: 700; letter-spacing: 0.15em;
  color: #e2e8f0; text-align: center; padding: 0.4rem 0;
  background: #1e293b; border-radius: 0.25rem; margin: 0.4rem 0;
}

.conn-actions { display: flex; gap: 0.5rem; margin-top: 0.5rem; }
.btn-conn {
  padding: 0.35rem 0.85rem; border-radius: 0.3rem; font-size: 0.82rem;
  cursor: pointer; border: none; display: flex; align-items: center; gap: 0.35rem;
}
.btn-conn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary   { background: #2563eb; color: #fff; }
.btn-primary:hover:not(:disabled)  { background: #1d4ed8; }
.btn-secondary { background: #334155; color: #e2e8f0; }
.btn-secondary:hover { background: #475569; }
.btn-danger    { background: #7f1d1d; color: #fca5a5; }
.btn-danger:hover { background: #991b1b; }

.spinner { display: inline-block; animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.settings-field { margin-bottom: 0.5rem; }
.field-label { display: block; font-size: 0.78rem; color: #94a3b8; margin-bottom: 0.25rem; }
.field-input {
  width: 100%; background: #0f172a; border: 1px solid #334155;
  border-radius: 0.25rem; color: #e2e8f0; font-size: 0.85rem;
  padding: 0.35rem 0.6rem; box-sizing: border-box;
}
.field-input:focus { outline: none; border-color: #2563eb; }
</style>
