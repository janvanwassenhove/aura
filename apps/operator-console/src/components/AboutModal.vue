<template>
  <div class="about-overlay" @click.self="$emit('close')">
    <div class="about-modal">
      <div class="about-header">
        <span class="about-title"><Info :size="16" /> About</span>
        <button class="btn-close" aria-label="Close" @click="$emit('close')"><X :size="15" /></button>
      </div>

      <div class="about-body">
        <div class="about-hero">
          <Bot :size="42" class="about-logo" />
          <div>
            <div class="about-name">AURA</div>
            <div class="about-sub">Adaptive Unified Robotic Assistant</div>
            <div class="about-version">version {{ version }}</div>
            <button v-if="isElectron" class="about-check" :disabled="checking" @click="checkUpdates">
              {{ checking ? 'Checking…' : 'Check for updates' }}
            </button>
          </div>
        </div>

        <p v-if="updateMsg" :class="['about-update', `about-update--${updateKind}`]">{{ updateMsg }}</p>

        <p class="about-text">
          An embodied AI assistant living in a Reachy Mini robot — voice
          conversations, face recognition, a personal knowledge graph and a
          self-optimizing skills library.
        </p>

        <dl class="about-acronym">
          <div><dt>Adaptive</dt><dd>Adapts behaviour and interaction to the person, the context and the situation.</dd></div>
          <div><dt>Unified</dt><dd>Brings conversation, mail, Teams, calendar, todos, memory and agents together.</dd></div>
          <div><dt>Robotic</dt><dd>Physically embodied through Reachy Mini.</dd></div>
          <div><dt>Assistant</dt><dd>A personal assistant and copilot, not just another chatbot.</dd></div>
        </dl>

        <div class="about-links">
          <a class="about-link" href="https://mityjohn.com/" target="_blank" rel="noopener noreferrer">
            <Globe :size="14" /> mityjohn.com
            <span class="about-link-sub">blog &amp; projects by mITy.John</span>
          </a>
          <a class="about-link" href="https://github.com/janvanwassenhove/aura" target="_blank" rel="noopener noreferrer">
            <Github :size="14" /> GitHub
            <span class="about-link-sub">source &amp; releases</span>
          </a>
        </div>

        <p class="about-credit">
          Made by <a href="https://mityjohn.com/" target="_blank" rel="noopener noreferrer">Jan Van Wassenhove</a>
          · built with the Reachy Mini SDK
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Bot, Github, Globe, Info, X } from 'lucide-vue-next'

defineEmits<{ close: [] }>()

// Packaged builds get their real version from Electron (stamped per release);
// a plain browser/dev run shows "dev" rather than pretending.
const auraWindow = (window as any).aura
const isElectron = Boolean(auraWindow?.isElectron)

const version = ref('dev')
onMounted(async () => {
  try {
    const v = await auraWindow?.appVersion?.()
    if (v) version.value = v
  } catch { /* dev / browser — keep "dev" */ }
})

// U178: the background check is deliberately silent, which made update
// checking look broken while this repo is private (GitHub answers 404 without
// a token). A manual check must always say what happened.
const checking = ref(false)
const updateMsg = ref('')
const updateKind = ref<'ok' | 'new' | 'warn'>('ok')

async function checkUpdates(): Promise<void> {
  checking.value = true
  updateMsg.value = ''
  try {
    const r = await auraWindow?.checkUpdate?.()
    if (!r) { updateKind.value = 'warn'; updateMsg.value = 'Update checking is unavailable here.'; return }
    if (r.status === 'update') {
      updateKind.value = 'new'
      updateMsg.value = `Version ${r.update.version} is available — the install prompt opens next.`
    } else if (r.status === 'current') {
      updateKind.value = 'ok'
      updateMsg.value = `You're up to date (${r.latest ?? version.value}).`
    } else if (r.status === 'unauthorized') {
      updateKind.value = 'warn'
      updateMsg.value = 'Could not check: the release repository is private. '
        + 'Add GITHUB_TOKEN to your settings, or make the repository public.'
    } else if (r.status === 'dev') {
      updateKind.value = 'ok'
      updateMsg.value = 'Development build — updates are not checked.'
    } else {
      updateKind.value = 'warn'
      updateMsg.value = `Could not check for updates (${r.reason ?? 'unknown'}).`
    }
  } finally {
    checking.value = false
  }
}
</script>

<style scoped>
.about-overlay {
  position: fixed; inset: 0; background: var(--overlay);
  display: flex; align-items: center; justify-content: center; z-index: 60;
}
.about-modal {
  width: min(430px, 92vw);
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius-lg, 12px); box-shadow: var(--shadow-modal);
  display: flex; flex-direction: column;
}
.about-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0.7rem 0.9rem; border-bottom: 1px solid var(--border);
}
.about-title { display: inline-flex; align-items: center; gap: 0.4rem; font-weight: 600; font-size: 0.85rem; }
.btn-close {
  background: none; border: none; color: var(--text-muted); cursor: pointer;
  display: flex; padding: 0.2rem; border-radius: 4px;
}
.btn-close:hover { color: var(--text); background: var(--surface-hover); }

.about-body { padding: 1rem 1.1rem 1.1rem; }
.about-hero { display: flex; align-items: center; gap: 0.9rem; }
.about-logo { color: var(--accent-soft); flex-shrink: 0; }
.about-name { font-size: 1.15rem; font-weight: 700; letter-spacing: 0.04em; }
.about-sub { font-size: 0.72rem; color: var(--text-muted); }
.about-version { font-size: 0.7rem; color: var(--text-faint); font-family: ui-monospace, monospace; margin-top: 0.15rem; }

.about-check {
  margin-top: 0.35rem; padding: 0.15rem 0.5rem; cursor: pointer;
  font-size: 0.68rem; border-radius: 5px;
  background: none; border: 1px solid var(--border); color: var(--text-muted);
}
.about-check:hover:not(:disabled) { color: var(--text); border-color: var(--accent); }
.about-check:disabled { opacity: 0.6; cursor: default; }

.about-update {
  font-size: 0.72rem; line-height: 1.45; margin: 0.9rem 0 0;
  padding: 0.5rem 0.6rem; border-radius: 6px; border: 1px solid var(--border);
}
.about-update--ok { color: var(--text-muted); }
.about-update--new { color: var(--ok-text, #2f9e6e); border-color: currentColor; }
.about-update--warn { color: var(--warn, #d9a441); border-color: currentColor; }

.about-text { font-size: 0.78rem; color: var(--text-muted); line-height: 1.5; margin: 0.9rem 0; }
.about-acronym { margin: 0 0 0.9rem; display: grid; gap: 0.35rem; }
.about-acronym > div { display: grid; grid-template-columns: 5.2rem 1fr; gap: 0.5rem; align-items: baseline; }
.about-acronym dt { font-size: 0.75rem; font-weight: 600; color: var(--text); }
.about-acronym dd { margin: 0; font-size: 0.72rem; color: var(--text-muted); line-height: 1.4; }

.about-links { display: flex; flex-direction: column; gap: 0.4rem; }
.about-link {
  display: flex; align-items: center; gap: 0.45rem;
  padding: 0.5rem 0.6rem; border: 1px solid var(--border);
  border-radius: 8px; text-decoration: none; color: var(--text);
  font-size: 0.78rem; font-weight: 600;
}
.about-link:hover { border-color: var(--accent); background: var(--surface-hover); }
.about-link-sub { margin-left: auto; font-weight: 400; font-size: 0.7rem; color: var(--text-faint); }

.about-credit { font-size: 0.7rem; color: var(--text-faint); margin: 0.9rem 0 0; text-align: center; }
.about-credit a { color: var(--accent); text-decoration: none; }
.about-credit a:hover { text-decoration: underline; }
</style>
