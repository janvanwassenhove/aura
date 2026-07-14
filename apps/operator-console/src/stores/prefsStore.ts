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

export type VoiceMode = 'off' | 'wake_word'

export const usePrefsStore = defineStore('prefs', () => {
  const assistantName = ref('AURA')
  const language = ref<Language>('auto')
  const voiceMode = ref<VoiceMode>('off')
  const wakeWord = ref('AURA')
  const ttsVoice = ref('alloy')
  const saving = ref(false)
  const error = ref<string | null>(null)

  async function fetchPrefs(): Promise<void> {
    try {
      const resp = await fetch(`${BRAIN_URL}/setup/prefs`)
      if (resp.ok) {
        const data = await resp.json()
        assistantName.value = data.assistant_name ?? 'AURA'
        language.value = (data.language ?? 'auto') as Language
        voiceMode.value = (data.voice_mode ?? 'off') as VoiceMode
        wakeWord.value = data.wake_word
      ttsVoice.value = data.tts_voice ?? ttsVoice.value ?? assistantName.value
        ttsVoice.value = data.tts_voice ?? 'alloy'
      }
    } catch { /* keep defaults */ }
  }

  async function save(fields: {
    assistant_name?: string; language?: Language;
    voice_mode?: VoiceMode; wake_word?: string; tts_voice?: string
  }): Promise<boolean> {
    saving.value = true
    error.value = null
    try {
      const resp = await fetch(`${BRAIN_URL}/setup/prefs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(fields),
      })
      const data = await resp.json().catch(() => ({}))
      if (!resp.ok) {
        error.value = data.error ?? `Save failed (${resp.status})`
        return false
      }
      assistantName.value = data.assistant_name
      language.value = data.language
      voiceMode.value = data.voice_mode
      wakeWord.value = data.wake_word
      ttsVoice.value = data.tts_voice ?? ttsVoice.value
      return true
    } catch {
      error.value = 'Could not reach the brain.'
      return false
    } finally {
      saving.value = false
    }
  }

  return { assistantName, language, voiceMode, wakeWord, ttsVoice, saving, error, fetchPrefs, save }
})
