import { defineStore } from 'pinia'
import { ref } from 'vue'
import { BRAIN_URL } from '../lib/endpoints'


export type Language = 'auto' | 'en' | 'nl' | 'fr' | 'de'

export const LANGUAGES: { id: Language; label: string }[] = [
  { id: 'auto', label: 'Auto (match me)' },   // U130: also handles NL/EN code-switching
  { id: 'en', label: 'English' },
  { id: 'nl', label: 'Nederlands' },
  { id: 'fr', label: 'Français' },
  { id: 'de', label: 'Deutsch' },
]

export type VoiceMode = 'off' | 'wake_word'
export type VoiceEngine = 'pipeline' | 'realtime'  // U132

/** D2: one surface, three depths. Density changes how much of the SAME screen
 * is exposed — it never changes what the robot may do. */
export type Density = 'calm' | 'standard' | 'full'

export const DENSITY_META: Record<Density, { label: string; hint: string }> = {
  calm: { label: 'Calm', hint: 'Just the conversation. Large type, no logs, no jargon.' },
  standard: { label: 'Standard', hint: 'Adds context cards, tool results and the quick asks.' },
  full: { label: 'Full', hint: 'Everything: activity log, timings, provenance.' },
}

/** The depth a recognised person gets before anyone touches the dial:
 * kids and guests calm, family standard, the owner everything. */
export function densityForRole(role: string | null | undefined): Density {
  if (role === 'owner') return 'full'
  if (role === 'family') return 'standard'
  return 'calm'
}

export const usePrefsStore = defineStore('prefs', () => {
  const assistantName = ref('AURA')
  const language = ref<Language>('auto')
  /** U257: which language wins when a message is too short to tell. Empty =
   *  work it out from this machine's locale; `Effective` is what that became. */
  const languageFallback = ref<string>('')
  const languageFallbackEffective = ref<string>('')
  const voiceMode = ref<VoiceMode>('off')
  const voiceEngine = ref<VoiceEngine>('pipeline')
  const wakeWord = ref('AURA')
  const ttsVoice = ref('alloy')
  const saving = ref(false)
  const error = ref<string | null>(null)

  // ── D2 shell state (client-side, persisted locally) ──────────────────────
  const density = ref<Density>(
    (localStorage.getItem('aura-density') as Density) || 'standard',
  )
  // Whether the dial was set by hand this session. Untouched → density follows
  // whoever is recognised (kids get Calm without asking for it).
  const densityTouched = ref(false)
  const railCollapsed = ref(localStorage.getItem('aura-rail') === 'collapsed')

  function setDensity(d: Density): void {
    density.value = d
    densityTouched.value = true
    try { localStorage.setItem('aura-density', d) } catch { /* session-only */ }
  }
  /** A person change resets the hand-set flag so auto-density can follow. */
  function followPerson(role: string | null | undefined): void {
    if (!densityTouched.value) density.value = densityForRole(role)
  }
  function resetDensityTouch(): void { densityTouched.value = false }
  function toggleRail(): void {
    railCollapsed.value = !railCollapsed.value
    try { localStorage.setItem('aura-rail', railCollapsed.value ? 'collapsed' : 'open') } catch { /* session-only */ }
  }

  async function fetchPrefs(): Promise<void> {
    try {
      const resp = await fetch(`${BRAIN_URL}/setup/prefs`)
      if (resp.ok) {
        const data = await resp.json()
        assistantName.value = data.assistant_name ?? 'AURA'
        language.value = (data.language ?? 'auto') as Language
        languageFallback.value = data.language_fallback ?? ''
        languageFallbackEffective.value = data.language_fallback_effective ?? ''
        voiceMode.value = (data.voice_mode ?? 'off') as VoiceMode
        voiceEngine.value = (data.voice_engine ?? 'pipeline') as VoiceEngine
        wakeWord.value = data.wake_word
        ttsVoice.value = data.tts_voice ?? 'alloy'
      }
    } catch { /* keep defaults */ }
  }

  async function save(fields: {
    assistant_name?: string; language?: Language; language_fallback?: string;
    voice_mode?: VoiceMode; voice_engine?: VoiceEngine; wake_word?: string; tts_voice?: string
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
      if (typeof data.language_fallback === 'string') languageFallback.value = data.language_fallback
      if (typeof data.language_fallback_effective === 'string') {
        languageFallbackEffective.value = data.language_fallback_effective
      }
      voiceMode.value = data.voice_mode
      voiceEngine.value = data.voice_engine ?? voiceEngine.value
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

  return {
    assistantName, language, languageFallback, languageFallbackEffective,
    voiceMode, voiceEngine, wakeWord, ttsVoice, saving, error,
    density, densityTouched, railCollapsed,
    setDensity, followPerson, resetDensityTouch, toggleRail,
    fetchPrefs, save,
  }
})
