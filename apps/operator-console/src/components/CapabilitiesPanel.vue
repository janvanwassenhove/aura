<template>
  <div class="cap-overlay" @click.self="$emit('close')">
    <div class="cap-modal">
      <div class="cap-header">
        <span class="cap-title"><ShieldCheck :size="16" /> Capabilities &amp; permissions</span>
        <button class="btn-close" @click="$emit('close')"><X :size="15" /></button>
      </div>

      <p class="cap-intro">
        Decide what {{ prefsStore.assistantName }} may do on this laptop. Turning
        something on only lets it <em>attempt</em> the action — anything sensitive
        (sending mail, writing files, launching an app) still asks you first.
      </p>

      <div v-if="store.error" class="cap-error">{{ store.error }}</div>
      <div v-if="store.notice" class="cap-notice">{{ store.notice }}</div>

      <div class="cap-body">
        <div v-for="cap in store.capabilities" :key="cap.key" class="cap-row">
          <div class="cap-info">
            <div class="cap-label">
              {{ cap.label }}
              <span v-if="store.pending.includes(cap.key)" class="cap-badge" title="Restart to apply this change">restart to apply</span>
            </div>
            <div class="cap-desc">{{ cap.description }}</div>
          </div>
          <button
            :class="['toggle', cap.enabled && 'toggle--on']"
            :title="cap.enabled ? 'Enabled' : 'Disabled'"
            @click="store.toggle(cap.key, !cap.enabled)"
          ><span class="toggle-knob" /></button>
        </div>

        <div v-if="store.autoApproved.length > 0" class="cap-apps">
          <div class="cap-label">Always-allowed actions</div>
          <div class="cap-desc">
            Actions you chose to auto-approve — they no longer ask each time.
            Revoke any to go back to asking.
          </div>
          <div class="cap-app-list">
            <span v-for="a in store.autoApproved" :key="a" class="cap-auto">
              {{ a }}
              <button class="cap-auto-x" title="Revoke — ask again next time" @click="store.revokeAuto(a)"><X :size="11" /></button>
            </span>
          </div>
        </div>

        <div class="cap-apps">
          <div class="cap-label">Allowed apps</div>
          <div class="cap-desc">
            Apps {{ prefsStore.assistantName }} may launch on request (each launch asks for
            approval). Register them in <code>ALLOWED_APPS</code> in your <code>.env</code>
            as <code>name=command</code> pairs, e.g.
            <code>vscode=code;spotify=spotify</code>.
          </div>
          <div class="cap-app-list">
            <span v-for="a in store.allowedApps" :key="a" class="cap-app">{{ a }}</span>
            <span v-if="store.allowedApps.length === 0" class="cap-desc">None registered yet.</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { ShieldCheck, X } from 'lucide-vue-next'
import { useCapabilitiesStore } from '../stores/capabilitiesStore'
import { usePrefsStore } from '../stores/prefsStore'

defineEmits<{ close: [] }>()

const store = useCapabilitiesStore()
const prefsStore = usePrefsStore()

onMounted(() => {
  store.fetchCapabilities()
  store.fetchAutoApprovals()
  prefsStore.fetchPrefs()
})
</script>

<style scoped>
.cap-overlay {
  position: fixed; inset: 0; background: var(--overlay);
  display: flex; align-items: center; justify-content: center; z-index: 60;
}
.cap-modal {
  background: var(--surface); border: 1px solid var(--border-strong);
  border-radius: var(--radius-xl); width: 34rem; max-width: 95vw; max-height: 88vh;
  display: flex; flex-direction: column; box-shadow: var(--shadow-modal);
}
.cap-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0.85rem 1rem; border-bottom: 1px solid var(--border);
}
.cap-title { font-weight: 600; font-size: 0.95rem; display: inline-flex; align-items: center; gap: 0.4rem; }
.btn-close { background: none; border: none; color: var(--text-muted); cursor: pointer; display: flex; }
.btn-close:hover { color: var(--text); }
.cap-intro { font-size: 0.8rem; color: var(--text-muted); margin: 0.75rem 1rem 0; }
.cap-error { margin: 0.6rem 1rem 0; padding: 0.4rem 0.6rem; border-radius: var(--radius); background: var(--danger-bg); color: var(--danger-text); font-size: 0.78rem; }
.cap-notice { margin: 0.6rem 1rem 0; padding: 0.4rem 0.6rem; border-radius: var(--radius); background: var(--warn-bg); color: var(--warn-text); font-size: 0.78rem; }
.cap-body { padding: 0.75rem 1rem 1rem; overflow-y: auto; }
.cap-row {
  display: flex; align-items: center; justify-content: space-between; gap: 1rem;
  padding: 0.6rem 0; border-bottom: 1px solid var(--border);
}
.cap-info { min-width: 0; }
.cap-label { font-weight: 600; font-size: 0.85rem; display: flex; align-items: center; gap: 0.4rem; }
.cap-desc { font-size: 0.75rem; color: var(--text-faint); margin-top: 0.15rem; }
.cap-desc code { background: var(--surface-3); padding: 0.05rem 0.25rem; border-radius: 3px; }
.cap-badge { font-size: 0.6rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--warn-text); background: var(--warn-bg); border-radius: 999px; padding: 0.05rem 0.4rem; }
.cap-apps { padding-top: 0.7rem; }
.cap-app-list { display: flex; flex-wrap: wrap; gap: 0.35rem; margin-top: 0.4rem; }
.cap-app { font-size: 0.72rem; background: var(--surface-3); border: 1px solid var(--border); border-radius: 999px; padding: 0.15rem 0.6rem; }
.cap-auto { display: inline-flex; align-items: center; gap: 0.25rem; font-size: 0.72rem; background: var(--ok-bg); color: var(--ok-text); border-radius: 999px; padding: 0.15rem 0.3rem 0.15rem 0.6rem; }
.cap-auto-x { display: inline-flex; background: none; border: none; color: var(--ok-text); cursor: pointer; opacity: 0.7; }
.cap-auto-x:hover { opacity: 1; }

.toggle {
  width: 40px; height: 22px; border-radius: 999px; border: 1px solid var(--border);
  background: var(--surface-3); cursor: pointer; position: relative; padding: 0; flex-shrink: 0;
}
.toggle-knob {
  position: absolute; top: 2px; left: 2px; width: 16px; height: 16px;
  border-radius: 50%; background: var(--text-faint); transition: all 0.15s;
}
.toggle--on { background: var(--accent); border-color: var(--accent); }
.toggle--on .toggle-knob { left: 20px; background: #fff; }
</style>
