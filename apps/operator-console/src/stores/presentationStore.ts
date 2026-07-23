import { defineStore } from 'pinia'
import { ref } from 'vue'

// U206: co-presenter state for the presenter view. The subtitle comes from
// PresentationBeatFired events on the WS; slide/armed-keywords come from the
// brain's /presentation/status (polled while presenting).

const BRAIN_URL =
  import.meta.env.VITE_BRAIN_URL ??
  import.meta.env.VITE_ORCHESTRATOR_URL ??
  'http://localhost:8020'

export interface PresentationStatus {
  active: boolean
  title?: string
  current_slide?: number | null
  manual_pos?: number
  manual_total?: number
  fired?: string[]
  armed_keywords?: string[]
  powerpoint_watching?: boolean
}

export const usePresentationStore = defineStore('presentation', () => {
  const status = ref<PresentationStatus>({ active: false })
  const subtitle = ref('')           // the robot's last spoken line
  const lastBeat = ref('')           // id of the last beat that fired
  const lastMode = ref('')
  const busy = ref(false)
  const error = ref('')

  /** Applied for every WS frame; only reacts to our beat events. */
  function applyEvent(raw: Record<string, unknown>): void {
    if (raw.event_type !== 'PresentationBeatFired') return
    lastBeat.value = String(raw.beat_id ?? '')
    lastMode.value = String(raw.mode ?? '')
    const spoken = String(raw.spoken ?? '')
    // A silent beat says nothing — keep the previous subtitle rather than blank.
    if (spoken) subtitle.value = spoken
  }

  async function fetchStatus(): Promise<void> {
    try {
      const r = await fetch(`${BRAIN_URL}/presentation/status`)
      if (r.ok) status.value = await r.json()
    } catch { /* leave last known */ }
  }

  async function start(yamlText: string): Promise<boolean> {
    return _load({ yaml: yamlText })
  }

  async function startScenario(scenario: object): Promise<boolean> {
    return _load({ scenario })
  }

  async function _load(payload: Record<string, unknown>): Promise<boolean> {
    busy.value = true; error.value = ''
    try {
      const r = await fetch(`${BRAIN_URL}/presentation/scenario`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const body = await r.json().catch(() => null)
      if (!r.ok) { error.value = body?.error ?? 'Could not load the scenario.'; return false }
      status.value = { active: true, ...body }
      subtitle.value = ''; lastBeat.value = ''
      return true
    } catch {
      error.value = 'The brain did not respond.'
      return false
    } finally { busy.value = false }
  }

  async function next(): Promise<void> {
    busy.value = true
    try {
      const r = await fetch(`${BRAIN_URL}/presentation/next`, { method: 'POST' })
      if (r.ok) status.value = { active: true, ...(await r.json()).status }
    } finally { busy.value = false }
  }

  /** Manually push presenter speech (also fed automatically from the robot mic). */
  async function pushSpeech(text: string): Promise<void> {
    try {
      const r = await fetch(`${BRAIN_URL}/presentation/speech`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      })
      if (r.ok) status.value = { active: true, ...(await r.json()).status }
    } catch { /* ignore */ }
  }

  async function stop(): Promise<void> {
    busy.value = true
    try {
      await fetch(`${BRAIN_URL}/presentation/scenario`, { method: 'DELETE' })
    } catch { /* ignore */ }
    finally {
      status.value = { active: false }
      subtitle.value = ''; lastBeat.value = ''; busy.value = false
    }
  }

  return { status, subtitle, lastBeat, lastMode, busy, error,
           applyEvent, fetchStatus, start, startScenario, next, pushSpeech, stop }
})
