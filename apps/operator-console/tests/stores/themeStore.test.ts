import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useThemeStore } from '../../src/stores/themeStore'

/** D2: two themes, ONE accent (AURA green). The four-accent picker is gone by
 * design — `--present` purple is a semantic signal for Present mode, never a
 * user preference — so the store carries a theme and nothing else. */

describe('themeStore', () => {
  beforeEach(() => {
    localStorage.clear()
    delete document.documentElement.dataset.auraTheme
    setActivePinia(createPinia())
  })

  it('defaults to light', () => {
    expect(useThemeStore().theme).toBe('light')
  })

  it('apply() stamps data-aura-theme on the root element', () => {
    const store = useThemeStore()
    store.apply()
    expect(document.documentElement.dataset.auraTheme).toBe('light')
  })

  it('changing theme re-applies and persists', async () => {
    const store = useThemeStore()
    store.apply()
    store.theme = 'dark'
    await new Promise(r => setTimeout(r))  // watcher flush
    expect(document.documentElement.dataset.auraTheme).toBe('dark')
    expect(JSON.parse(localStorage.getItem('aura-appearance')!)).toMatchObject({ theme: 'dark' })
  })

  it('restores a saved theme on a fresh store', () => {
    localStorage.setItem('aura-appearance', JSON.stringify({ theme: 'dark' }))
    setActivePinia(createPinia())
    expect(useThemeStore().theme).toBe('dark')
  })

  it('a saved accent from the old picker is ignored, not an error', () => {
    // Installs that chose purple in the pre-D2 console must still boot.
    localStorage.setItem('aura-appearance', JSON.stringify({ theme: 'dark', accent: 'purple' }))
    setActivePinia(createPinia())
    const store = useThemeStore()
    expect(store.theme).toBe('dark')
    expect('accent' in store).toBe(false)
  })

  it('corrupted storage falls back to defaults', () => {
    localStorage.setItem('aura-appearance', '{nope')
    setActivePinia(createPinia())
    expect(useThemeStore().theme).toBe('light')
  })

  it('$reset returns to light', () => {
    const store = useThemeStore()
    store.theme = 'dark'
    store.$reset()
    expect(store.theme).toBe('light')
  })
})
