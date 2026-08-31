import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { archetype, CHARACTERS, DEFAULT_CHARACTER, type CharacterAct } from '../lib/characters'
import { useRobotStore } from './robotStore'

/** D2: which archetype Richie presents as, console-side.
 *
 * One pick sets his look and how the mark animates. The act (idle / speak /
 * move) is derived from the same robot events every other panel reads — the
 * avatar animates because something is actually happening, never decoratively.
 */
const STORAGE_KEY = 'aura-character'

export const useCharacterStore = defineStore('character', () => {
  const selected = ref<string>(localStorage.getItem(STORAGE_KEY) || DEFAULT_CHARACTER)

  function select(id: string): void {
    if (!CHARACTERS[id]) return
    selected.value = id
    try { localStorage.setItem(STORAGE_KEY, id) } catch { /* session-only */ }
  }

  /** U286: the presentation overlay is a SEPARATE WINDOW with its own Pinia
   *  store, and this ref was read from localStorage exactly once — when that
   *  window opened. Pick a different character in the console and the overlay
   *  kept wearing the old one on the beamer, for the rest of the talk.
   *  Reported as "when changing robot character, robot overlay is not changing
   *  accordingly".
   *
   *  The browser already tells every OTHER window of the same origin when
   *  localStorage changes; nothing was listening. Same-window changes stay
   *  reactive through Pinia as before — a `storage` event never fires in the
   *  window that caused it. */
  if (typeof window !== 'undefined') {
    window.addEventListener('storage', (e: StorageEvent) => {
      if (e.key !== STORAGE_KEY) return
      const id = e.newValue || DEFAULT_CHARACTER
      if (CHARACTERS[id]) selected.value = id
    })
  }

  const current = computed(() => archetype(selected.value))

  // Demo overrides (the "Hear him" / "Try a move" preview buttons).
  const demoAct = ref<CharacterAct | null>(null)
  let demoTimer: ReturnType<typeof setTimeout> | null = null
  function demo(act: CharacterAct): void {
    demoAct.value = act
    if (demoTimer) clearTimeout(demoTimer)
    demoTimer = setTimeout(() => { demoAct.value = null }, 3200)
  }

  const robot = useRobotStore()
  const act = computed<CharacterAct>(() => {
    if (demoAct.value) return demoAct.value
    if (robot.isSpeaking) return 'speak'
    if (robot.motionLog[0]?.status === 'started') return 'move'
    return 'idle'
  })

  return { selected, current, act, demoAct, select, demo }
})
