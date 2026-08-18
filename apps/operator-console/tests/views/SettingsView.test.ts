import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import SettingsView from '../../src/views/SettingsView.vue'

/** U252e: Settings loaded nothing, and said "unknown" about everything.
 *
 *  The D2 rewrite called `connections.fetchStatus()` / `fetchIdentityStatus()`
 *  — two functions the store keeps PRIVATE; only `refreshAllStatuses()` is
 *  exported. That is a TypeError on the first of them, and they sat in one
 *  `onMounted` arrow with five other loads behind them, so capabilities,
 *  remembered decisions, the vault state and the voice prefs never loaded
 *  either. On screen it read as "the backend is down" — every connector row
 *  said `unknown` — while those endpoints were answering 200 the whole time.
 *
 *  This app has no vue-tsc config (esbuild strips types unchecked) and nothing
 *  mounted this view, so neither the compiler nor the suite could see it. The
 *  test exists so a wrong store method is a red test, not a grey UI.
 */

const OK = (body: unknown) => Promise.resolve({
  ok: true, status: 200, json: () => Promise.resolve(body),
} as Response)

function stubFetch(): string[] {
  const calls: string[] = []
  vi.stubGlobal('fetch', (url: string) => {
    const u = String(url)
    calls.push(u)
    if (u.includes('/connector/health')) {
      return OK({ status: 'ok', connectors: { m365: 'mock', music: 'mock' } })
    }
    if (u.includes('/identity/status/')) return OK({ connected: false })
    if (u.includes('/capabilities')) return OK({ capabilities: [], allowed_apps: [] })
    if (u.includes('/config/llm/models')) return OK({ models: [] })
    if (u.includes('/config/llm')) return OK({ provider: 'openai', model: 'gpt-4o-mini' })
    return OK({})
  })
  return calls
}

beforeEach(() => {
  vi.unstubAllGlobals()
  setActivePinia(createPinia())
})
afterEach(() => vi.unstubAllGlobals())

describe('Settings loads its sections', () => {
  it('mounts without throwing and asks the backend for every section', async () => {
    const errors: unknown[] = []
    const spy = vi.spyOn(console, 'error').mockImplementation(e => { errors.push(e) })

    const calls = stubFetch()
    const w = mount(SettingsView)
    await flushPromises()
    await flushPromises()

    expect(errors, 'onMounted must not throw').toEqual([])
    spy.mockRestore()

    // The regression: everything from `connections` onward never happened,
    // because the call before it threw. Each of these is its own section.
    const asked = (frag: string) => calls.some(u => u.includes(frag))
    expect(asked('/connector/health'), 'connector health (Connections)').toBe(true)
    expect(asked('/capabilities'), 'capabilities').toBe(true)
    expect(asked('/knowledge/tier'), 'vault state (Privacy)').toBe(true)
    expect(asked('/setup/prefs'), 'voice prefs').toBe(true)
    w.unmount()
  })

  it('shows a real connector state instead of "unknown"', async () => {
    stubFetch()
    const w = mount(SettingsView)
    await flushPromises()
    await flushPromises()
    // m365 reports "mock" → the row must say so, not sit at the initial value.
    expect(w.text()).toContain('canned data')
    w.unmount()
  })
})
