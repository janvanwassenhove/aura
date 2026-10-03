import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { toRows, type BeatRow, type RawBeat } from '../lib/beats'
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
  const beats = ref<BeatRow[]>([])

  /** U388: the list comes from the BRAIN, whichever way the show was loaded.
   *  It was filled only when Start was pressed in this window, so a talk
   *  loaded from the saved list — or this window reloaded mid-talk — left it
   *  empty, and the HUD read "Saying now —" and "Next cue: the end" on the
   *  slide where the gag plays. Keyed on a string so a status poll that
   *  changes nothing does not refetch. */
  async function syncFromBrain(): Promise<void> {
    const sc = await presentation.fetchScenario()
    if (sc) beats.value = toRows((sc as { beats?: RawBeat[] }).beats)
  }
  // U389: a talk that was ended and kept is loaded too, so Run again and the
  // beat list survive End; removing it empties the list.
  watch(
    () => (presentation.status.active
      ? 'run:' + String(presentation.status.title ?? '')
      : presentation.status.kept ? 'kept:' + presentation.status.kept.title : ''),
    (key, before) => {
      if (key) void syncFromBrain()
      else if (before) beats.value = []
    },
    { immediate: true },
  )

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

  /** The last beat that ran; -1 before anything has. Drives the highlight.
   *  U388: the brain says which one, now that a beat can run more than once;
   *  an older brain that does not say falls back to the old guess. */
  const beatIdx = computed(() => {
    const last = presentation.status.last_fired
    if (last) return beats.value.findIndex(b => b.id === last)
    for (let i = beats.value.length - 1; i >= 0; i--) {
      if (firedIds.value.has(beats.value[i].id)) return i
    }
    return -1
  })

  const currentBeat = computed(() => beats.value[beatIdx.value] ?? null)

  /** U388: the next thing the presenter will REACH. A scenario is written in
   *  whatever order its author liked — the real one lists every overlay pair
   *  before the chapters — so file order says nothing about what comes next,
   *  and "the first beat not yet fired" was stuck forever on a slide-1 beat
   *  the presenter had walked past. Slides ahead of the current one, in slide
   *  order; then a hand-advanced beat still waiting; then the end. Keyword
   *  beats are not "next": they are armed, and the HUD says so separately. */
  const nextBeat = computed<BeatRow | null>(() => {
    const here = presentation.status.current_slide ?? null
    const ahead = beats.value
      .map((b, i) => ({ b, i }))
      .filter(x => x.b.slide != null && (here == null || (x.b.slide as number) > here))
      .sort((x, y) => ((x.b.slide as number) - (y.b.slide as number)) || (x.i - y.i))
    if (ahead.length) return ahead[0].b
    return beats.value.find(b => b.kind === 'manual' && !firedIds.value.has(b.id)) ?? null
  })

  function setBeats(list: BeatRow[]): void {
    beats.value = list
  }

  return { rehearsing, beats, beatIdx, total, done, finished,
           currentBeat, nextBeat, setBeats }
})
