import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { usePresentationStore } from './presentationStore'

/** D2: ONE beat index drives everything — the run bar, the HUD counter, the
 * saying-now line, the next cue and the highlighted row. It is derived from
 * the brain's presentation status, never counted separately per widget:
 * counters that could diverge were a prototype bug before they were a rule. */
export const usePresenterStore = defineStore('presenter', () => {
  const presentation = usePresentationStore()

  /** U267: rehearsal is the BRAIN's state now, not a label in this tab.
   *  The button used to flip a local boolean while the robot said every line
   *  out loud — the view promised "nothing is sent" and everything was. */
  const rehearsing = computed(() => !!presentation.status.rehearsing)

  /** The scenario as loaded (for the beat list + next cue). */
  const beats = ref<{ id: string; cue: string; kind: string; say: string; do: string }[]>([])

  /** U267: which beats have actually run, by id.
   *
   *  The position used to come from `manual_pos` / `manual_total`, which
   *  describe only the HAND-ADVANCED beats — not the show. One manual beat,
   *  fire it, and the HUD read "beat 2 of 1"; add three slide beats and the
   *  denominator still said 1. What a presenter wants to know is how much of
   *  the whole scenario has happened, and `fired` says exactly that for every
   *  kind of cue at once. */
  const firedIds = computed(() => new Set(presentation.status.fired ?? []))

  const total = computed(() =>
    beats.value.length || presentation.status.beats_total || 0)

  /** How many beats have run — never more than there are. */
  const done = computed(() =>
    beats.value.length
      ? beats.value.filter(b => firedIds.value.has(b.id)).length
      : Math.min(firedIds.value.size, total.value))

  const finished = computed(() => total.value > 0 && done.value >= total.value)

  /** The last beat that ran; -1 before anything has. Drives the highlight. */
  const beatIdx = computed(() => {
    for (let i = beats.value.length - 1; i >= 0; i--) {
      if (firedIds.value.has(beats.value[i].id)) return i
    }
    return -1
  })

  const currentBeat = computed(() => beats.value[beatIdx.value] ?? null)
  /** The first beat still waiting — which is what "next cue" means, and is
   *  NOT simply the one after the last fired: slide cues fire out of order
   *  whenever the presenter jumps ahead in the deck. */
  const nextBeat = computed(() =>
    beats.value.find(b => !firedIds.value.has(b.id)) ?? null)

  function setBeats(list: { id: string; cue: string; kind: string; say: string; do: string }[]): void {
    beats.value = list
  }

  return { rehearsing, beats, beatIdx, total, done, finished,
           currentBeat, nextBeat, setBeats }
})
