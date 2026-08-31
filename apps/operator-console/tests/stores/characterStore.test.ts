import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useCharacterStore } from '../../src/stores/characterStore'
import { DEFAULT_CHARACTER } from '../../src/lib/characters'

/** U286: "when changing robot character, robot overlay is not changing
 *  accordingly."
 *
 *  The presentation overlay is a SEPARATE WINDOW with its own Pinia store, and
 *  the chosen character was read out of localStorage exactly once — when that
 *  window opened. Pick a different character in the console and the overlay
 *  kept wearing the old one on the beamer for the rest of the talk.
 *
 *  Same family as U269 (the overlay could not see the beats) and U276 (the
 *  header's speaker never left the browser): a second window holding its own
 *  copy of something the first window changes.
 */

function storageEvent(key: string, newValue: string | null): StorageEvent {
  return new StorageEvent('storage', { key, newValue })
}

beforeEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
  setActivePinia(createPinia())
})

describe('U286 — every window follows the character that was picked', () => {
  it('adopts a character chosen in another window', () => {
    const store = useCharacterStore()
    expect(store.selected).toBe(DEFAULT_CHARACTER)

    // What the console's pick looks like from inside the overlay window.
    window.dispatchEvent(storageEvent('aura-character', 'buddy'))

    expect(store.selected).toBe('buddy')
    expect(store.current.tag).toBe('Buddy')
  })

  it('ignores other keys, so unrelated settings cannot change his face', () => {
    const store = useCharacterStore()
    window.dispatchEvent(storageEvent('aura-overlay', 'buddy'))
    expect(store.selected).toBe(DEFAULT_CHARACTER)
  })

  it('ignores a character it does not have', () => {
    const store = useCharacterStore()
    store.select('buddy')
    window.dispatchEvent(storageEvent('aura-character', 'not-a-character'))
    // A bad value must never blank the beamer mid-talk.
    expect(store.selected).toBe('buddy')
  })

  it('falls back to the default when the key is cleared', () => {
    const store = useCharacterStore()
    store.select('buddy')
    window.dispatchEvent(storageEvent('aura-character', null))
    expect(store.selected).toBe(DEFAULT_CHARACTER)
  })

  it('still writes the pick so a window opening later starts on it', () => {
    const store = useCharacterStore()
    store.select('sentinel')
    expect(localStorage.getItem('aura-character')).toBe('sentinel')
    expect(store.current.tag).toBe('Sentinel')
  })
})
