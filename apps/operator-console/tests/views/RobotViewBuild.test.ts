import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import RobotView from '../../src/views/RobotView.vue'
import { usePrefsStore } from '../../src/stores/prefsStore'

/** U371 (audit T6): the Connection card says which build the robot runs.
 *
 *  The Pi is deployed separately from the laptop, and has drifted behind it
 *  by 74 commits once (U240) and by one on the day this was written. Nothing
 *  in the app showed it; `deploy_robot.py --check` did, if you remembered it.
 *  Every "the fix did not work" that was really "the fix is not on the Pi" was
 *  found by hand.
 *
 *  Three states, three sentences — and the absent one is an absence, never a
 *  guess: a packaged app without a stamp cannot compare, and says so.
 */

const OK = (body: unknown) => Promise.resolve({
  ok: true, status: 200, json: () => Promise.resolve(body),
} as Response)

type Build = { robot: string | null; laptop: string | null; behind: boolean | null }

function stubFetch(build: Build): void {
  vi.stubGlobal('fetch', (url: string) => {
    const u = String(url)
    if (u.includes('/robot/status')) return OK({ connected: true, mode: 'online', build })
    if (u.includes('/robot/address')) return OK({ url: 'http://192.168.0.178:8001' })
    if (u.includes('/setup/status')) return OK({ robot_secret_set: false })
    return OK({})
  })
}

async function mountFull() {
  usePrefsStore().setDensity('full')          // the Connection card is full-density
  const w = mount(RobotView)
  await flushPromises()
  await flushPromises()
  return w
}

beforeEach(() => {
  vi.unstubAllGlobals()
  setActivePinia(createPinia())
})
afterEach(() => vi.unstubAllGlobals())

describe('which build the robot runs', () => {
  it('says he is behind, and by which commits', async () => {
    stubFetch({ robot: 'f145485', laptop: '8f179ce', behind: true })
    const w = await mountFull()
    const line = w.find('[data-test="robot-build"]')
    expect(line.exists(), 'no build line in the Connection card').toBe(true)
    expect(line.text()).toContain('f145485')
    expect(line.text()).toContain('8f179ce')
    expect(line.text().toLowerCase()).toContain('behind')
  })

  it('says they match when they match', async () => {
    stubFetch({ robot: '8f179ce', laptop: '8f179ce', behind: false })
    const w = await mountFull()
    const text = w.find('[data-test="robot-build"]').text().toLowerCase()
    expect(text).toContain('8f179ce')
    expect(text).not.toContain('behind')
    expect(text).toMatch(/same|in step/)
  })

  it('admits it cannot compare, rather than guessing', async () => {
    stubFetch({ robot: 'f145485', laptop: null, behind: null })
    const w = await mountFull()
    const text = w.find('[data-test="robot-build"]').text().toLowerCase()
    expect(text).toContain('f145485')
    expect(text).toMatch(/cannot compare|unknown/)
    expect(text).not.toContain('behind')
  })

  it('says nothing about a build when the robot is too old to report one', async () => {
    stubFetch({ robot: null, laptop: '8f179ce', behind: null })
    const w = await mountFull()
    const text = w.find('[data-test="robot-build"]').text().toLowerCase()
    expect(text).toMatch(/does not report|older/)
  })
})
