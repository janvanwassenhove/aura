import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useConversationStore } from '../../src/stores/conversationStore'

/** U391: when he drives the mouse or keyboard, the owner sees it and can stop
 *  it. The cursor ring, the banner and the Stop button follow
 *  ComputerControlStarted / Ended — which until U391 never reached the console.
 *
 *  The overlay also captures Esc system-wide while it is up, so it must never
 *  outlive the action: the console checks the brain while it believes he is
 *  driving, and keeps confirming to the desktop shell that the warning is
 *  still wanted. A missed "ended" can no longer leave Esc taken — which in a
 *  PowerPoint slideshow is the key that ends the show. */

let brainSays = { active: false }
const shown: boolean[] = []

beforeEach(() => {
  vi.useFakeTimers()
  setActivePinia(createPinia())
  brainSays = { active: false }
  shown.length = 0
  vi.stubGlobal('fetch', vi.fn(async (url: string) => ({
    ok: true,
    json: async () => (String(url).includes('/computeruse/status') ? brainSays : {}),
  }) as Response))
  ;(window as unknown as { aura: unknown }).aura = {
    screenControl: (on: boolean) => { shown.push(on) },
  }
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  delete (window as unknown as { aura?: unknown }).aura
})

describe('U391 — the screen-control warning', () => {
  it('comes up when he starts driving and comes down when he stops', () => {
    const c = useConversationStore()
    c.applyEvent({ event_type: 'ComputerControlStarted', goal: 'open the mail' })
    expect(c.screenControl).toBe(true)
    expect(shown.at(-1)).toBe(true)

    c.applyEvent({ event_type: 'ComputerControlEnded' })
    expect(c.screenControl).toBe(false)
    expect(shown.at(-1)).toBe(false)
  })

  it('comes down by itself when the "ended" event was missed', async () => {
    const c = useConversationStore()
    brainSays = { active: true }
    c.applyEvent({ event_type: 'ComputerControlStarted', goal: 'x' })

    brainSays = { active: false }          // it ended; the event never arrived
    await vi.advanceTimersByTimeAsync(3500)

    expect(c.screenControl).toBe(false)
    expect(shown.at(-1)).toBe(false)
  })

  it('keeps telling the desktop it is still wanted while he is still driving', async () => {
    const c = useConversationStore()
    brainSays = { active: true }
    c.applyEvent({ event_type: 'ComputerControlStarted', goal: 'x' })
    const before = shown.length

    await vi.advanceTimersByTimeAsync(9500)

    expect(c.screenControl).toBe(true)
    expect(shown.length - before).toBeGreaterThanOrEqual(3)
    expect(shown.slice(before).every(Boolean)).toBe(true)
  })

  it('asks the brain when it (re)connects, and clears a leftover warning', async () => {
    const c = useConversationStore()
    brainSays = { active: false }
    await c.syncScreenControl()
    expect(c.screenControl).toBe(false)
    expect(shown).toEqual([false])        // a stale overlay from before is taken down
  })

  it('picks up a run that started before it connected', async () => {
    const c = useConversationStore()
    brainSays = { active: true }
    await c.syncScreenControl()
    expect(c.screenControl).toBe(true)
    expect(shown.at(-1)).toBe(true)
  })

  it('stops checking once he is done', async () => {
    const c = useConversationStore()
    brainSays = { active: true }
    c.applyEvent({ event_type: 'ComputerControlStarted', goal: 'x' })
    c.applyEvent({ event_type: 'ComputerControlEnded' })
    const calls = (fetch as unknown as { mock: { calls: unknown[] } }).mock.calls.length
    await vi.advanceTimersByTimeAsync(10000)
    expect((fetch as unknown as { mock: { calls: unknown[] } }).mock.calls.length).toBe(calls)
  })
})
