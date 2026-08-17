import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { usePresentationStore } from './presentationStore'

/** D2: ONE beat index drives everything — the run bar, the HUD counter, the
 * saying-now line, the next cue and the highlighted row. It is derived from
 * the brain's presentation status, never counted separately per widget:
 * counters that could diverge were a prototype bug before they were a rule. */
export const usePresenterStore = defineStore('presenter', () => {
  const presentation = usePresentationStore()

  const rehearsing = ref(false)

  /** The scenario as loaded (for the beat list + next cue). */
  const beats = ref<{ id: string; cue: string; kind: string; say: string; do: string }[]>([])

  const beatIdx = computed(() => {
    const s = presentation.status
    if (!s.active) return 0
    // The brain reports the manual position; fired beats otherwise.
    if (typeof s.manual_pos === 'number') return Math.max(0, s.manual_pos)
    return Math.max(0, (s.fired?.length ?? 1) - 1)
  })

  const total = computed(() => {
    const s = presentation.status
    return s.manual_total ?? beats.value.length ?? 0
  })

  const currentBeat = computed(() => beats.value[beatIdx.value] ?? null)
  const nextBeat = computed(() => beats.value[beatIdx.value + 1] ?? null)

  function setBeats(list: { id: string; cue: string; kind: string; say: string; do: string }[]): void {
    beats.value = list
  }

  return { rehearsing, beats, beatIdx, total, currentBeat, nextBeat, setBeats }
})
