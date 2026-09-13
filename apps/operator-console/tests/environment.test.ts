import { describe, it, expect, beforeEach } from 'vitest'

/** U350: the test environment itself, asserted.
 *
 *  Nine of the console's test files open with `localStorage.clear()`, and on a
 *  Node that carries its own inert `localStorage` global they all died on that
 *  line before reaching a single assertion about the product. The failure was
 *  indistinguishable from a broken store, so the environment gets its own
 *  test: if Web Storage ever stops being real again, exactly one file says so,
 *  and it says why.
 */
describe('U350 — the DOM environment hands the console a real Web Storage', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
  })

  it.each(['localStorage', 'sessionStorage'] as const)('%s carries the full Storage surface', name => {
    const storage = (globalThis as unknown as Record<string, Storage>)[name]
    for (const method of ['getItem', 'setItem', 'removeItem', 'clear', 'key'] as const) {
      expect(typeof storage[method], `${name}.${method}`).toBe('function')
    }
    expect(typeof storage.length).toBe('number')
  })

  it('keeps browser semantics — a miss is null, a value is a string', () => {
    expect(localStorage.getItem('aura-never-written')).toBeNull()
    localStorage.setItem('aura-probe', String(42))
    expect(localStorage.getItem('aura-probe')).toBe('42')
    expect(localStorage.length).toBe(1)
    localStorage.removeItem('aura-probe')
    expect(localStorage.getItem('aura-probe')).toBeNull()
  })

  it('is the same object the app reaches through window', () => {
    expect(window.localStorage).toBe(localStorage)
    expect(window.sessionStorage).toBe(sessionStorage)
  })

  it('the two storages are separate, so one clear cannot empty the other', () => {
    localStorage.setItem('aura-k', 'local')
    sessionStorage.setItem('aura-k', 'session')
    localStorage.clear()
    expect(sessionStorage.getItem('aura-k')).toBe('session')
  })

  it('starts empty in every file, so one test cannot seed the next', () => {
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
  })
})
