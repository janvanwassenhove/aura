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
export const useCharacterStore = defineStore('character', () => {
  const selected = ref<string>(localStorage.getItem('aura-character') || DEFAULT_CHARACTER)

  function select(id: string): void {
    if (!CHARACTERS[id]) return
    selected.value = id
    try { localStorage.setItem('aura-character', id) } catch { /* session-only */ }
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
