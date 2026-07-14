import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useThemeStore, ACCENTS } from '../../src/stores/themeStore'

describe('themeStore', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
    document.documentElement.removeAttribute('data-accent')
    setActivePinia(createPinia())
  })

  it('defaults to dark theme with blue accent', () => {
    const store = useThemeStore()
    expect(store.theme).toBe('dark')
    expect(store.accent).toBe('blue')
  })

  it('apply() stamps data attributes on the root element', () => {
    const store = useThemeStore()
    store.apply()
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(document.documentElement.dataset.accent).toBe('blue')
  })

  it('changing theme re-applies and persists', async () => {
    const store = useThemeStore()
    store.apply()
    store.theme = 'light'
    await new Promise(r => setTimeout(r))  // watcher flush
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(JSON.parse(localStorage.getItem('aura-appearance')!)).toMatchObject({ theme: 'light' })
  })

  it('changing accent re-applies and persists', async () => {
    const store = useThemeStore()
    store.apply()
    store.accent = 'purple'
    await new Promise(r => setTimeout(r))
    expect(document.documentElement.dataset.accent).toBe('purple')
    expect(JSON.parse(localStorage.getItem('aura-appearance')!)).toMatchObject({ accent: 'purple' })
  })

  it('restores saved appearance on a fresh store (new session)', () => {
    localStorage.setItem('aura-appearance', JSON.stringify({ theme: 'light', accent: 'amber' }))
    setActivePinia(createPinia())
    const store = useThemeStore()
    expect(store.theme).toBe('light')
    expect(store.accent).toBe('amber')
  })

  it('falls back to defaults on corrupted storage', () => {
    localStorage.setItem('aura-appearance', '{not json')
    setActivePinia(createPinia())
    const store = useThemeStore()
    expect(store.theme).toBe('dark')
    expect(store.accent).toBe('blue')
  })

  it('rejects unknown accent values from storage', () => {
    localStorage.setItem('aura-appearance', JSON.stringify({ theme: 'dark', accent: 'hotpink' }))
    setActivePinia(createPinia())
    expect(useThemeStore().accent).toBe('blue')
  })

  it('exposes the four accents for the picker', () => {
    expect(ACCENTS.map(a => a.id)).toEqual(['blue', 'green', 'purple', 'amber'])
  })
})
