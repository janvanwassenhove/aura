import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export type Theme = 'dark' | 'light'
export type Accent = 'blue' | 'green' | 'purple' | 'amber'

const STORAGE_KEY = 'aura-appearance'

export const ACCENTS: { id: Accent; label: string }[] = [
  { id: 'blue', label: 'Blue' },
  { id: 'green', label: 'Green' },
  { id: 'purple', label: 'Purple' },
  { id: 'amber', label: 'Amber' },
]

function loadSaved(): { theme: Theme; accent: Accent } {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      return {
        theme: parsed.theme === 'dark' ? 'dark' : 'light',
        accent: ACCENTS.some(a => a.id === parsed.accent) ? parsed.accent : 'green',
      }
    }
  } catch { /* corrupted storage → defaults */ }
  // U193: light + green is the default appearance. Anyone who already picked
  // something keeps it — this only decides what a fresh install opens with.
  return { theme: 'light', accent: 'green' }
}

export const useThemeStore = defineStore('theme', () => {
  const saved = loadSaved()
  const theme = ref<Theme>(saved.theme)
  const accent = ref<Accent>(saved.accent)

  function apply() {
    const root = document.documentElement
    root.dataset.theme = theme.value
    root.dataset.accent = accent.value
  }

  function persist() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ theme: theme.value, accent: accent.value }))
    } catch { /* storage full/blocked — theme still applies for this session */ }
  }

  watch([theme, accent], () => { apply(); persist() })

  function $reset() {
    theme.value = 'light'
    accent.value = 'green'
  }

  return { theme, accent, apply, $reset }
})
