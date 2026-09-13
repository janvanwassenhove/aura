import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import RobotView from '../../src/views/RobotView.vue'
import { usePrefsStore } from '../../src/stores/prefsStore'

/** U341: send him to sleep from the same place you ask him to wave.
 *
 *  Asked as: "for robot gestures ask -> add sleep and awake (so i can easily
 *  take him along when going to travel)".
 *
 *  Sleep already existed — as a toggle in the body strip, next to Mic, Follow
 *  and Proactive, which is where you look when you are configuring him and not
 *  where you look when you are about to put him in a bag. "Ask him to…" is the
 *  list of things you tell him to do, and going to sleep is one of them.
 *
 *  These are NOT motions: they go to /robot/sleep and /robot/wake, not through
 *  the motion vocabulary. A "sleep" motion would put the head down and leave
 *  the motors live, which is the opposite of what travelling needs.
 */

const OK = (body: unknown) => Promise.resolve({
  ok: true, status: 200, json: () => Promise.resolve(body),
} as Response)

type Call = { url: string; method: string }

function stubFetch(calls: Call[], asleep = false): void {
  vi.stubGlobal('fetch', (url: string, init?: RequestInit) => {
    const u = String(url)
    calls.push({ url: u, method: init?.method ?? 'GET' })
    if (u.includes('/robot/sleep') && (init?.method ?? 'GET') === 'GET') return OK({ asleep })
    if (u.includes('/robot/status')) return OK({ connected: true })
    return OK({})
  })
}

function chip(w: ReturnType<typeof mount>, label: string) {
  return w.findAll('.ask-chip').find(b => b.text() === label)
}

beforeEach(() => {
  vi.unstubAllGlobals()
  setActivePinia(createPinia())
})
afterEach(() => vi.unstubAllGlobals())

describe('sleep and wake, where you ask him for things', () => {
  it('offers both, at every density — you pack him at any zoom level', async () => {
    for (const density of ['calm', 'standard', 'full'] as const) {
      setActivePinia(createPinia())
      stubFetch([])
      usePrefsStore().setDensity(density)
      const w = mount(RobotView)
      await flushPromises()

      expect(chip(w, 'go to sleep')?.exists(), `missing at ${density}`).toBe(true)
      expect(chip(w, 'wake up')?.exists(), `missing at ${density}`).toBe(true)
    }
  })

  it('sends him to sleep instead of playing a motion called sleep', async () => {
    const calls: Call[] = []
    stubFetch(calls)
    usePrefsStore().setDensity('full')
    const w = mount(RobotView)
    await flushPromises()

    await chip(w, 'go to sleep')!.trigger('click')
    await flushPromises()

    const posts = calls.filter(c => c.method === 'POST')
    expect(posts.some(c => c.url.includes('/robot/sleep'))).toBe(true)
    expect(posts.some(c => c.url.includes('/robot/motion') || c.url.includes('/robot/say')),
      'a motion would leave the motors live').toBe(false)
  })

  it('wakes him again', async () => {
    const calls: Call[] = []
    stubFetch(calls, true)
    usePrefsStore().setDensity('full')
    const w = mount(RobotView)
    await flushPromises()

    await chip(w, 'wake up')!.trigger('click')
    await flushPromises()

    expect(calls.some(c => c.method === 'POST' && c.url.includes('/robot/wake'))).toBe(true)
  })

  it('shows which of the two he is in right now', async () => {
    stubFetch([], true)          // he is asleep
    usePrefsStore().setDensity('full')
    const w = mount(RobotView)
    await flushPromises()

    expect(chip(w, 'go to sleep')!.attributes('aria-pressed')).toBe('true')
    expect(chip(w, 'wake up')!.attributes('aria-pressed')).toBe('false')
  })
})
