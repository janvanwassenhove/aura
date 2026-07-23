<template>
  <!-- U197: the update is already downloaded by the time this appears, so the
       owner is interrupted once and installing costs one click and a few
       seconds — not a modal that shows up first and downloads afterwards. -->
  <div v-if="ready" class="upd-bar" role="status">
    <span class="upd-text">Versie {{ ready.version }} staat klaar om te installeren.</span>
    <button class="upd-btn upd-btn--go" :disabled="installing" @click="install">
      {{ installing ? 'AURA sluit af en komt terug…' : 'Herstarten &amp; installeren' }}
    </button>
    <button class="upd-btn" :disabled="installing" @click="later">Later</button>
    <span v-if="error" class="upd-err">{{ error }}</span>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'

const aura = (window as any).aura
const ready = ref<{ version: string; tag: string } | null>(null)
const installing = ref(false)
const error = ref('')
let off: (() => void) | undefined

onMounted(() => {
  // Only Electron can stage an installer; in a browser this stays silent.
  if (!aura?.onUpdateReady) return
  off = aura.onUpdateReady((info: { version: string; tag: string }) => {
    ready.value = info
  })
})
onUnmounted(() => { off?.() })

async function install() {
  if (installing.value) return
  installing.value = true
  error.value = ''
  const r = await aura.installUpdate()
  // On success the app is replaced and quits; only a failure gets this far.
  if (!r?.ok) {
    error.value = r?.error || 'Installeren is niet gelukt.'
    installing.value = false
  }
}

function later() {
  void aura.dismissUpdate?.(ready.value?.tag)
  ready.value = null
}
</script>

<style scoped>
.upd-bar {
  display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap;
  padding: 0.45rem 0.9rem;
  background: var(--surface); border-bottom: 1px solid var(--border-strong);
  font-size: 0.8rem; color: var(--text);
}
.upd-text { flex: 1 1 auto; }
.upd-btn {
  background: transparent; color: var(--text-muted);
  border: 1px solid var(--border-strong); border-radius: var(--radius-md);
  padding: 0.25rem 0.7rem; font-size: 0.78rem; cursor: pointer;
}
.upd-btn:hover:not(:disabled) { color: var(--text); }
.upd-btn--go {
  background: var(--accent); color: var(--accent-contrast, #fff); border-color: var(--accent);
}
.upd-btn--go:hover:not(:disabled) { filter: brightness(1.07); }
.upd-btn:disabled { opacity: 0.6; cursor: default; }
.upd-err { color: var(--danger, #e5484d); font-size: 0.75rem; flex-basis: 100%; }
</style>
