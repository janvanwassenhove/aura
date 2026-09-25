import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import App from '../../src/App.vue'
import { useRobotStore } from '../../src/stores/robotStore'

/** U365: nothing had ever mounted the shell.
 *
 *  Two things this locks down, both found the hard way.
 *
 *  **The shell must survive mount and unmount.** Writing the status watch into
 *  `App.vue` used `onUnmounted` without importing it. There is no `vue-tsc`
 *  here — esbuild strips types unchecked — so that is not a build error: it is
 *  a blank window in front of the owner the next time the app starts. The store
 *  test beside this one passed cheerfully while the shell was broken, because
 *  it never mounted anything.
 *
 *  **The shell must keep asking how the robot is.** That is the fix for the
 *  reported defect — video moving, header saying "robot offline" — and a fix
 *  nothing tests is a fix that gets deleted by the next refactor that finds an
 *  unexplained timer.
 */

const OK = (body: unknown) => Promise.resolve({
  ok: true, status: 200, json: () => Promise.resolve(body),
} as Response)

/** Route-aware on purpose: a blanket `OK({})` hands every store the wrong
 *  shape and produces failures that have nothing to do with the test. */
function stubFetch(seen?: string[]): void {
  vi.stubGlobal('fetch', (url: string) => {
    const u = String(url)
    seen?.push(u)
    if (u.includes('/robot/status')) return OK({ connected: true, mode: 'online' })
    if (u.includes('/knowledge/people')) return OK([])
    if (u.includes('/setup/status')) return OK({ setup_done: true })
    return OK({})
  })
}

beforeEach(() => {
  vi.unstubAllGlobals()
  setActivePinia(createPinia())
  // The shell opens the event stream on mount; jsdom has no WebSocket worth
  // the name, and this test is about the shell, not the transport.
  vi.stubGlobal('WebSocket', class {
    onopen: (() => void) | null = null
    onclose: (() => void) | null = null
    onerror: (() => void) | null = null
    onmessage: ((e: unknown) => void) | null = null
    readyState = 0
    close(): void { /* no socket to close */ }
    send(): void { /* nothing listens */ }
  })
  stubFetch()
})
afterEach(() => vi.unstubAllGlobals())

describe('the app shell', () => {
  it('mounts and unmounts without throwing', async () => {
    const errors: unknown[] = []
    const spy = vi.spyOn(console, 'error').mockImplementation(e => { errors.push(e) })

    const w = mount(App)
    await flushPromises()
    w.unmount()                      // where a missing onUnmounted import lands
    await flushPromises()

    expect(errors, 'the shell threw').toEqual([])
    spy.mockRestore()
  })

  it('asks the brain how the robot is, on mount', async () => {
    const seen: string[] = []
    stubFetch(seen)

    const w = mount(App)
    await flushPromises()

    expect(seen.some(u => u.includes('/robot/status')), 'it never asked').toBe(true)
    w.unmount()
  })

  it('keeps asking, and stops when the window goes away', async () => {
    /** The reported defect in one line: the console asked twice in its life and
     *  then believed whatever the last event said. */
    const robot = useRobotStore()
    const stop = vi.fn()
    const watch = vi.spyOn(robot, 'watchStatus').mockReturnValue(stop)

    const w = mount(App)
    await flushPromises()
    expect(watch, 'nothing keeps the header honest').toHaveBeenCalled()

    w.unmount()
    await flushPromises()
    expect(stop, 'the timer outlived the window').toHaveBeenCalled()
  })
})
