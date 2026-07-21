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
          </div>
        </div>

        <p class="about-text">
          An embodied AI assistant living in a Reachy Mini robot — voice
          conversations, face recognition, a personal knowledge graph and a
          self-optimizing skills library.
        </p>

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
const version = ref('dev')
onMounted(async () => {
  try {
    const v = await (window as any).aura?.appVersion?.()
    if (v) version.value = v
  } catch { /* dev / browser — keep "dev" */ }
})
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

.about-text { font-size: 0.78rem; color: var(--text-muted); line-height: 1.5; margin: 0.9rem 0; }

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
