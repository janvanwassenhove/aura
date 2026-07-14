import { defineStore } from 'pinia'
import { ref } from 'vue'

const BRAIN_URL =
  import.meta.env.VITE_BRAIN_URL ??
  import.meta.env.VITE_ORCHESTRATOR_URL ??
  'http://localhost:8000'

export type Language = 'auto' | 'en' | 'nl' | 'fr'

export const LANGUAGES: { id: Language; label: string }[] = [
  { id: 'auto', label: 'Auto (match me)' },
  { id: 'en', label: 'English' },
  { id: 'nl', label: 'Nederlands' },
  { id: 'fr', label: 'Français' },
]

export const usePrefsStore = defineStore('prefs', () => {
  const assistantName = ref('AURA')
  const language = ref<Language>('auto')
  const saving = ref(false)
  const error = ref<string | null>(null)

  async function fetchPrefs(): Promise<void> {
    try {
      const resp = await fetch(`${BRAIN_URL}/setup/prefs`)
      if (resp.ok) {
        const data = await resp.json()
        assistantName.value = data.assistant_name ?? 'AURA'
        language.value = (data.language ?? 'auto') as Language
      }
    } catch { /* keep defaults */ }
  }

  async function save(name: string, lang: Language): Promise<boolean> {
    saving.value = true
    error.value = null
    try {
      const resp = await fetch(`${BRAIN_URL}/setup/prefs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ assistant_name: name, language: lang }),
      })
      const data = await resp.json().catch(() => ({}))
      if (!resp.ok) {
        error.value = data.error ?? `Save failed (${resp.status})`
        return false
      }
      assistantName.value = data.assistant_name
      language.value = data.language
      return true
    } catch {
      error.value = 'Could not reach the brain.'
      return false
    } finally {
      saving.value = false
    }
  }

  return { assistantName, language, saving, error, fetchPrefs, save }
})
