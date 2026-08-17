import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export type Theme = 'dark' | 'light'

const STORAGE_KEY = 'aura-appearance'

// D2: one accent (AURA green). The four-accent picker is gone by design —
// `--present` purple is a semantic signal for Present mode, not a preference.
function loadSaved(): { theme: Theme } {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      return { theme: parsed.theme === 'dark' ? 'dark' : 'light' }
    }
  } catch { /* corrupted storage → defaults */ }
  // Light is the default appearance; this only decides what a fresh install
  // opens with — anyone who already picked something keeps it.
  return { theme: 'light' }
}

export const useThemeStore = defineStore('theme', () => {
  const saved = loadSaved()
  const theme = ref<Theme>(saved.theme)

  function apply() {
    document.documentElement.dataset.auraTheme = theme.value
  }

  function persist() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ theme: theme.value }))
    } catch { /* storage full/blocked — theme still applies for this session */ }
  }

  watch(theme, () => { apply(); persist() })

  function $reset() {
    theme.value = 'light'
  }

  return { theme, apply, $reset }
})
