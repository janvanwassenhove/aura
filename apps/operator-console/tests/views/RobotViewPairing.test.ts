import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import RobotView from '../../src/views/RobotView.vue'
import { usePrefsStore } from '../../src/stores/prefsStore'

/** U339: pairing a second laptop with the robot, from the app.
 *
 *  Reported from a fresh install on another laptop: every call to the robot
 *  comes back 401, because the robot has a shared secret (U220) and that
 *  machine does not. `ROBOT_SHARED_SECRET` was read in two places and written
 *  by nothing — no endpoint, no field. The only way to pair a second machine
 *  was to find `%APPDATA%\aura-desktop\.env` and type it in by hand, which is
 *  exactly the "advice with nowhere to act on it" U199 called worse than
 *  saying nothing.
 *
 *  The field belongs in the Connection card, because that is where the
 *  diagnosis appears. This app has no vue-tsc, so a mount test is the only
 *  thing standing between a typo here and a grey panel in front of the owner.
 */

const OK = (body: unknown) => Promise.resolve({
  ok: true, status: 200, json: () => Promise.resolve(body),
} as Response)

type Posted = { url: string; body: unknown }

function stubFetch(posted: Posted[], secretSet = { value: false }): void {
  vi.stubGlobal('fetch', (url: string, init?: RequestInit) => {
    const u = String(url)
    if (init?.method === 'POST') {
      posted.push({ url: u, body: JSON.parse(String(init.body ?? '{}')) })
    }
    if (u.includes('/setup/status')) return OK({ robot_secret_set: secretSet.value })
    if (u.includes('/robot/address')) return OK({ url: 'http://192.168.0.178:8001' })
    if (u.includes('/robot/status')) return OK({ connected: false })
    return OK({})
  })
}

function mountFull() {
  usePrefsStore().setDensity('full')     // the Connection card is full-density
  return mount(RobotView)
}

beforeEach(() => {
  vi.unstubAllGlobals()
  setActivePinia(createPinia())
})
afterEach(() => vi.unstubAllGlobals())

describe('the robot pairing key', () => {
  it('mounts and offers somewhere to type the key', async () => {
    const errors: unknown[] = []
    const spy = vi.spyOn(console, 'error').mockImplementation(e => { errors.push(e) })
    stubFetch([])

    const w = mountFull()
    await flushPromises()

    expect(errors, 'onMounted must not throw').toEqual([])
    spy.mockRestore()

    const field = w.find('input[aria-label="Robot pairing key"]')
    expect(field.exists(), 'no field to pair a second machine with').toBe(true)
    expect(field.attributes('type'), 'a credential must not sit on screen in clear text')
      .toBe('password')
  })

  it('sends the key to the brain, and never keeps it in the page', async () => {
    const posted: Posted[] = []
    stubFetch(posted)

    const w = mountFull()
    await flushPromises()

    await w.find('input[aria-label="Robot pairing key"]').setValue('pair-me-42')
    await w.find('[data-test="pair"]').trigger('click')
    await flushPromises()

    const call = posted.find(p => p.url.includes('/setup/config'))
    expect(call, 'the key went nowhere').toBeTruthy()
    expect((call!.body as Record<string, string>).robot_shared_secret).toBe('pair-me-42')
    expect(w.html(), 'the key stayed in the DOM').not.toContain('pair-me-42')
  })

  it('says whether this machine is paired, without showing the key', async () => {
    stubFetch([], { value: true })

    const w = mountFull()
    await flushPromises()

    expect(w.text().toLowerCase()).toContain('paired')
  })

  it('can forget the key, for a robot that has none', async () => {
    const posted: Posted[] = []
    stubFetch(posted, { value: true })

    const w = mountFull()
    await flushPromises()

    const forget = w.find('[data-test="forget-pairing"]')
    expect(forget.exists(), 'no way back off a key that is wrong').toBe(true)
    await forget.trigger('click')
    await flushPromises()

    const call = posted.find(p => p.url.includes('/setup/config'))
    expect((call!.body as Record<string, unknown>).clear_robot_secret).toBe(true)
  })

  it('offers no Forget button when there is nothing to forget', async () => {
    stubFetch([], { value: false })

    const w = mountFull()
    await flushPromises()

    expect(w.find('[data-test="forget-pairing"]').exists()).toBe(false)
  })
})
