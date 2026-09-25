import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { readdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { useModeStore } from '../../src/stores/modeStore'

/** U370 (audit T4): every store constructs, and the Quiet switch is wired.
 *
 *  Seven stores had no test importing them — among them `modeStore`, which
 *  owns the Quiet switch that U256, U332 and U366 were all about. A store is
 *  a function; if its setup body references a name that no longer exists, the
 *  first component to `useXStore()` throws inside `setup()`, and that reads as
 *  a blank view. Constructing each one is the cheapest compile step there is.
 *
 *  The list is the directory: a new store file without a test is at least
 *  constructed here.
 */

const OK = (body: unknown) => Promise.resolve({
  ok: true, status: 200, json: () => Promise.resolve(body),
} as Response)

const modules = import.meta.glob('../../src/stores/*.ts')

beforeEach(() => {
  vi.unstubAllGlobals()
  setActivePinia(createPinia())
  // Storage is per FILE (tests/setup.ts), and modeStore reads 'aura-quiet' at
  // construction — a toggle in one test would seed the next.
  localStorage.clear()
  vi.stubGlobal('fetch', () => OK({}))
})
afterEach(() => vi.unstubAllGlobals())

describe('every store under src/stores', () => {
  const files = readdirSync(resolve(__dirname, '../../src/stores'))
    .filter(f => f.endsWith('.ts') && !f.endsWith('.d.ts')).sort()

  it('is a real list, read from the directory', () => {
    expect(files.length).toBeGreaterThanOrEqual(7)
  })

  for (const file of files) {
    it(`constructs ${file}`, async () => {
      const mod = await modules[`../../src/stores/${file}`]() as Record<string, unknown>
      const factories = Object.entries(mod).filter(([k, v]) => k.startsWith('use') && typeof v === 'function')
      expect(factories.length, `${file} exports no use*Store`).toBeGreaterThan(0)
      for (const [, use] of factories) {
        const store = (use as () => Record<string, unknown>)()
        expect(store).toBeTruthy()
      }
    })
  }
})

describe('the Quiet switch (modeStore)', () => {
  it('tells the brain, not only the browser', async () => {
    const posted: { url: string; body: unknown }[] = []
    vi.stubGlobal('fetch', (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') posted.push({ url: String(url), body: JSON.parse(String(init.body)) })
      return OK({ quiet: true })
    })
    const mode = useModeStore()
    expect(mode.quiet).toBe(false)

    await mode.toggleQuiet()

    const call = posted.find(p => p.url.includes('/orchestrator/policy/quiet'))
    expect(call, 'Quiet stayed in the browser — the brain never heard').toBeTruthy()
    expect((call!.body as { quiet: boolean }).quiet).toBe(true)
    expect(mode.quiet).toBe(true)
  })

  it('snaps back when the brain refuses, rather than lying in the other direction', async () => {
    vi.stubGlobal('fetch', () => Promise.resolve({ ok: false, status: 503, json: () => Promise.resolve({}) } as Response))
    const mode = useModeStore()

    const okay = await mode.toggleQuiet()

    expect(okay).toBe(false)
    expect(mode.quiet, 'the chip says HUSHED while the brain is not').toBe(false)
  })
})
