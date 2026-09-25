import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import App from '../../src/App.vue'
import { useNavStore, type View } from '../../src/stores/navStore'

/** U370 (audit T4): every view mounts, and a new view cannot be added
 *  without mounting.
 *
 *  Five of the ten views had never been mounted by any test — `TalkView`, the
 *  main screen among them. There is no `vue-tsc` in this project: esbuild
 *  strips types unchecked, so an undefined name in a template, a store method
 *  that no longer exists, or a missing import (U365, `App.vue`) is not a build
 *  error. It is a blank panel in front of the owner. A mount test is the only
 *  compile step this app has, which is why the working agreement says a view
 *  ships with one.
 *
 *  The list of views is not written here. It is read from `navStore.ts`, the
 *  same union `App.vue` switches on, so adding `'diary'` to that type without a
 *  mount fails this file rather than the owner's next launch.
 */

const OK = (body: unknown) => Promise.resolve({
  ok: true, status: 200, json: () => Promise.resolve(body),
  text: () => Promise.resolve(JSON.stringify(body)),
  blob: () => Promise.resolve(new Blob([])),
} as unknown as Response)

/** Route-aware on purpose. A blanket `OK({})` hands every store the wrong
 *  shape and fails for reasons that have nothing to do with the view. */
function stubFetch(): void {
  vi.stubGlobal('fetch', (url: string) => {
    const u = String(url)
    if (u.includes('/robot/status')) return OK({ connected: true, mode: 'online' })
    if (u.includes('/robot/address')) return OK({ url: 'http://127.0.0.1:8001' })
    if (u.includes('/knowledge/people')) return OK([])
    if (u.includes('/knowledge/tier')) return OK({ tier: 'benign', omk_loaded: false })
    if (u.includes('/capabilities')) return OK({ capabilities: [], allowed_apps: [] })
    if (u.includes('/orchestrator/policy')) return OK({ active_mode: 'work', modes: {}, quiet: false })
    if (u.includes('/setup/status')) return OK({ setup_done: true, robot_secret_set: false })
    if (u.includes('/setup/prefs')) return OK({ voice_mode: 'off', voice_engine: 'pipeline' })
    if (u.includes('/setup/characters')) return OK([])
    if (u.includes('/connector/health')) return OK({ status: 'ok', connectors: {} })
    if (u.includes('/identity/status/')) return OK({ connected: false })
    if (u.includes('/config/llm/models')) return OK({ models: [] })
    if (u.includes('/config/llm')) return OK({ provider: 'openai', model: 'gpt-4o-mini' })
    if (u.includes('/voice/realtime-cost')) return OK({ estimated_usd: 0 })
    if (u.includes('/skills')) return OK([])
    if (u.includes('/mcp')) return OK({ servers: [] })
    return OK({})
  })
}

/** The union in navStore.ts, read as text — the one place the views are listed. */
function declaredViews(): View[] {
  const src = readFileSync(resolve(__dirname, '../../src/stores/navStore.ts'), 'utf-8')
  const m = src.match(/export type View =([\s\S]*?)\n\n/)
  expect(m, 'the View union moved — update this reader').toBeTruthy()
  return [...m![1].matchAll(/'([a-z]+)'/g)].map(x => x[1] as View)
}

beforeEach(() => {
  vi.unstubAllGlobals()
  setActivePinia(createPinia())
  vi.stubGlobal('WebSocket', class {
    onopen: (() => void) | null = null
    onclose: (() => void) | null = null
    onerror: (() => void) | null = null
    onmessage: ((e: unknown) => void) | null = null
    readyState = 0
    close(): void { /* nothing to close */ }
    send(): void { /* nothing listens */ }
  })
  // Canvases (Mind, Knowledge graph) draw on mount; happy-dom has no 2D context.
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => setTimeout(() => cb(0), 0) as unknown as number)
  vi.stubGlobal('cancelAnimationFrame', (id: number) => clearTimeout(id))
  vi.stubGlobal('ResizeObserver', class { observe(): void {} unobserve(): void {} disconnect(): void {} })
  stubFetch()
})
afterEach(() => vi.unstubAllGlobals())

describe('every view the shell can show', () => {
  it('is a real list, read from the code that switches on it', () => {
    const views = declaredViews()
    expect(views.length).toBeGreaterThanOrEqual(10)
    expect(views).toContain('talk')
  })

  for (const view of declaredViews()) {
    it(`mounts ${view} without throwing`, async () => {
      const errors: unknown[] = []
      const warn = vi.spyOn(console, 'warn').mockImplementation(w => {
        // Vue's own "[Vue warn]" is a type error surfacing at runtime here.
        if (String(w).includes('[Vue warn]')) errors.push(w)
      })
      const err = vi.spyOn(console, 'error').mockImplementation(e => { errors.push(e) })

      const w = mount(App)
      await flushPromises()
      useNavStore().go(view)
      await flushPromises()
      await flushPromises()

      expect(errors, `${view} threw or warned while mounting`).toEqual([])
      expect(w.html().length, `${view} rendered nothing`).toBeGreaterThan(200)
      w.unmount()
      warn.mockRestore(); err.mockRestore()
    })
  }
})
