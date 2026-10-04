import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { BRAIN_URL } from '../lib/endpoints'
import { splitCues, timeCues, type Cue } from '../lib/subtitleCues'

/** U400: how long the last piece stays after he stops, and how long a laptop
 *  line may take to report that it started before it is shown anyway. */
const LINGER_MS = 1_500
const START_GRACE_MS = 3_000

// U206: co-presenter state for the presenter view. The subtitle comes from
// PresentationBeatFired events on the WS; slide/armed-keywords come from the
// brain's /presentation/status (polled while presenting).


export interface PresentationStatus {
  active: boolean
  title?: string
  current_slide?: number | null
  manual_pos?: number
  manual_total?: number
  /** U267: the size of the WHOLE scenario. `manual_total` counts only the
   *  hand-advanced beats, and using it as the denominator produced "beat 2
   *  of 1" the moment a single manual beat had fired. */
  beats_total?: number
  /** U267: the brain is mute for voice and motion while this is true. */
  rehearsing?: boolean
  /** U269: why the last beat was not heard, if it was not. A beat that fires
   *  into silence used to be indistinguishable from one that was spoken. */
  speech_error?: string
  /** U349: he WAS heard, but not as the scenario asked - a beat named a
   *  persona that is not a character here, so it fell back to the
   *  presentation voice. Distinct from speech_error, which means the room
   *  heard nothing at all. */
  voice_note?: string
  /** U352: whether the scenario wants the overlay on the projector right now.
   *  Polled here AND pushed via PresentationOverlayChanged, because an event
   *  only reaches a subscriber that existed when it was published and the
   *  overlay window can be opened halfway through a talk. Absent means
   *  visible — an older brain must not blank the projector. */
  overlay_visible?: boolean
  fired?: string[]
  /** U388: the beat that ran most recently. */
  last_fired?: string
  /** U389: a talk that was ended and kept, so it can run again or be removed. */
  kept?: { title: string; beats_total: number }
  armed_keywords?: string[]
  /** U263: `watching` means a watcher is running; `slides_state` says whether
   *  it has actually FOUND a slideshow. The old flag conflated the two, so
   *  "waiting for you to start your deck" looked identical to "no slide cues
   *  for you at all". */
  watching?: boolean
  slides_state?: 'off' | 'waiting' | 'live'
  /** U266: non-empty when he CANNOT read the slideshow at all (the library is
   *  missing from this build) — which is not the same as not finding one yet. */
  slides_blocker?: string
  slides_app?: string
  deck?: string
  slide?: number
  slide_total?: number
  deck_warnings?: { kind: string; message: string }[]
}

export const usePresentationStore = defineStore('presentation', () => {
  const status = ref<PresentationStatus>({ active: false })
  const subtitle = ref('')           // the robot's last spoken line
  const lastBeat = ref('')           // id of the last beat that fired
  const lastMode = ref('')
  const lastPersona = ref('')   // U349: which character said it
  const busy = ref(false)
  const error = ref('')

  /** U400: the line on the projector, timed to his voice. `end` is when he
   *  stops; the last piece lingers a moment after so the room can finish it. */
  const timeline = ref<{ cues: Cue[]; end: number } | null>(null)
  let waiting: { id: string; text: string; ms: number; timer: ReturnType<typeof setTimeout> } | null = null

  function startLine(text: string, ms: number): void {
    const now = Date.now()
    const length = ms > 0 ? ms : Math.min(20_000, 1_500 + text.length * 66)
    const cues = timeCues(splitCues(text), now, length)
    timeline.value = cues.length ? { cues, end: now + length } : null
  }

  /** The piece to show at `t` — '' when he is not saying anything. */
  function cueAt(t: number): string {
    const tl = timeline.value
    if (!tl || t > tl.end + LINGER_MS) return ''
    const cue = tl.cues.find(c => t >= c.from && t < c.to)
    return cue ? cue.text : (t >= tl.end ? tl.cues[tl.cues.length - 1].text : '')
  }

  /** When he stops talking, for the avatar's mouth. 0 when he is not. */
  const speakingUntil = computed(() => timeline.value?.end ?? 0)

  /** Applied for every WS frame; only reacts to our beat events. */
  function applyEvent(raw: Record<string, unknown>): void {
    // U400: a talk's line, as he starts to say it — on the robot at once, on
    // the laptop when the playing window says so (it may be another window,
    // so the start comes back through the brain). If no window says so within
    // a few seconds the line shows anyway: late, never missing.
    if (raw.event_type === 'PresentationSubtitle') {
      const text = String(raw.text ?? '')
      const ms = Math.max(0, Number(raw.duration_s ?? 0) * 1000)
      if (!text) return
      subtitle.value = text
      lastPersona.value = String(raw.persona ?? '')
      if (waiting) { clearTimeout(waiting.timer); waiting = null }
      const id = String(raw.utterance_id ?? '')
      if (!id) { startLine(text, ms); return }
      waiting = { id, text, ms, timer: setTimeout(() => {
        if (waiting && waiting.id === id) { waiting = null; startLine(text, ms) }
      }, START_GRACE_MS) }
      return
    }
    if (raw.event_type === 'SpeechLineStarted') {
      if (!waiting || waiting.id !== String(raw.utterance_id ?? '')) return
      clearTimeout(waiting.timer)
      const measured = Number(raw.duration_s ?? 0) * 1000
      const { text, ms } = waiting
      waiting = null
      startLine(text, measured > 0 ? measured : ms)
      return
    }
    // U352: a beat moved the overlay. Written onto the SAME field the status
    // poll fills, so there is one answer to "should it be on screen" rather
    // than two that can disagree — this one just arrives 1.5 s sooner, which
    // on a beamer is the difference between a cut and a lag.
    if (raw.event_type === 'PresentationOverlayChanged') {
      status.value = { ...status.value, overlay_visible: raw.visible !== false }
      return
    }
    if (raw.event_type !== 'PresentationBeatFired') return
    lastBeat.value = String(raw.beat_id ?? '')
    lastMode.value = String(raw.mode ?? '')
    // U349: with two characters in one show, a subtitle that does not say
    // who is talking is worse than no attribution at all.
    lastPersona.value = String(raw.persona ?? '')
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
      subtitle.value = ''; timeline.value = null; lastBeat.value = ''
      return true
    } catch {
      error.value = 'The brain did not respond.'
      return false
    } finally { busy.value = false }
  }

  /** U267: rehearsal now reaches the brain, which is the only thing that can
   *  actually keep the robot quiet. */
  async function setRehearsing(on: boolean): Promise<void> {
    try {
      const r = await fetch(`${BRAIN_URL}/presentation/rehearse`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ on }),
      })
      const body = await r.json().catch(() => null)
      if (r.ok && body) status.value = body
      else error.value = body?.error ?? 'Could not switch rehearsal.'
    } catch { error.value = 'The brain did not respond.' }
  }

  /** U267: the scenario that is loaded, so the builder can EDIT it instead of
   *  making you retype a talk to change one line.
   *
   *  U269: and so the OVERLAY can know the show at all. The beat list used to
   *  live only in the Pinia store of the window that pressed Start — and the
   *  overlay is a separate window with a separate store, so its "next cue"
   *  row was reading an array that is always empty there and never rendered.
   *  Reported as "nor for the overlay did i see cues". The brain is the one
   *  thing both windows can agree on. */
  async function fetchScenario(): Promise<Record<string, unknown> | null> {
    try {
      const r = await fetch(`${BRAIN_URL}/presentation/scenario`)
      if (!r.ok) return null
      return (await r.json()).scenario ?? null
    } catch { return null }
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

  /** End the show. U389: the brain KEEPS the talk — End used to be the same
   *  call as Remove, so the scenario was gone the moment the talk ended. */
  async function stop(): Promise<void> {
    busy.value = true
    try {
      const r = await fetch(`${BRAIN_URL}/presentation/end`, { method: 'POST' })
      status.value = r.ok ? await r.json() : { active: false }
    } catch {
      status.value = { active: false }
    } finally {
      subtitle.value = ''; timeline.value = null; lastBeat.value = ''; busy.value = false
    }
  }

  /** U389: forget the talk — what End used to do. */
  async function remove(): Promise<void> {
    busy.value = true
    try {
      await fetch(`${BRAIN_URL}/presentation/scenario`, { method: 'DELETE' })
    } catch { /* ignore */ }
    finally {
      status.value = { active: false }
      subtitle.value = ''; timeline.value = null; lastBeat.value = ''; busy.value = false
    }
  }

  return { status, subtitle, lastBeat, lastMode, lastPersona, busy, error,
    timeline, cueAt, speakingUntil,
           applyEvent, fetchStatus, start, startScenario, next, pushSpeech, stop,
           setRehearsing, fetchScenario, remove }
})
