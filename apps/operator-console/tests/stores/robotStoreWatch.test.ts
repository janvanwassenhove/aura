import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useRobotStore } from '../../src/stores/robotStore'

/** U365: a wrong "offline" has to be able to correct itself.
 *
 *  Reported as (translated): *"why is it taking so long for Richie to come
 *  online? also at some point we see video moving (together with Richie
 *  moving) but AURA still says robot offline"*.
 *
 *  The brain was right the whole time — asked directly while the header said
 *  offline it answered `{"connected": true}`. The console was not asking. Since
 *  U297 it asks exactly twice: once on mount, and again whenever the event
 *  WebSocket (re)opens. Everything after that arrives as events, so a single
 *  wrong or missed `RobotDisconnected` stayed on screen until the app was
 *  restarted — with the camera happily streaming beside it.
 *
 *  The repository's own rule says how this ends: *state that must survive a
 *  late subscriber is polled, not awaited* (CLAUDE.md, Events drive state).
 *  Events stay the fast path; the poll is what makes being wrong temporary.
 */

const OK = (body: unknown) => Promise.resolve({
  ok: true, status: 200, json: () => Promise.resolve(body),
} as Response)

beforeEach(() => {
  vi.unstubAllGlobals()
  setActivePinia(createPinia())
})
afterEach(() => vi.unstubAllGlobals())

const settle = () => new Promise(r => setTimeout(r, 30))

describe('the header stops believing a stale disconnect', () => {
  it('asks again on its own, and corrects itself', async () => {
    vi.stubGlobal('fetch', () => OK({ connected: true, mode: 'online' }))
    const robot = useRobotStore()

    robot.applyEvent({ event_type: 'RobotDisconnected' })   // the wrong news
    expect(robot.connected).toBe(false)

    const stop = robot.watchStatus(10)
    await settle()
    stop()

    expect(robot.connected, 'it never asked again').toBe(true)
  })

  it('a blip in the brain does not read as a disconnect', async () => {
    /** U297 already made this call forgiving; polling must not undo that.
     *  One failed request is a network hiccup, not the robot leaving. */
    vi.stubGlobal('fetch', () => Promise.reject(new Error('ECONNRESET')))
    const robot = useRobotStore()
    robot.syncFromStatus({ connected: true })

    const stop = robot.watchStatus(10)
    await settle()
    stop()

    expect(robot.connected).toBe(true)
  })

  it('stops when told to — a second window must not double the traffic', async () => {
    let calls = 0
    vi.stubGlobal('fetch', () => { calls += 1; return OK({ connected: true }) })
    const robot = useRobotStore()

    const stop = robot.watchStatus(10)
    await settle()
    stop()
    const afterStop = calls
    await settle()

    expect(calls).toBe(afterStop)
  })

  it('starting twice does not leave a timer behind', async () => {
    let calls = 0
    vi.stubGlobal('fetch', () => { calls += 1; return OK({ connected: true }) })
    const robot = useRobotStore()

    robot.watchStatus(10)
    const stop = robot.watchStatus(10)     // e.g. a hot reload, or a remount
    await settle()
    stop()
    const afterStop = calls
    await settle()

    expect(calls, 'the first timer is still running').toBe(afterStop)
  })
})
