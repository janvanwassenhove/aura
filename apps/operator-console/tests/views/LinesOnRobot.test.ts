import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises, enableAutoUnmount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import PresentView from '../../src/views/PresentView.vue'

/** U410: a talk's lines are on the robot before their cue.
 *
 *  Asked (translated): "can we add preloading to decrease delay/latency of e.g.
 *  wifi hotspot?" Each recorded line is now sent to the robot ahead, so the cue
 *  names it instead of carrying 300 kB. The presenter sees how many he has —
 *  and, with a robot too old to keep them, that the lines still travel at
 *  their cue, rather than a count that silently stays at zero.
 */

enableAutoUnmount(afterEach)

const OK = (body: unknown) => Promise.resolve({
  ok: true, status: 200, json: () => Promise.resolve(body),
} as Response)

const TALK = {
  title: 'Devoxx',
  beats: [
    { id: 'hello', trigger: 'slide:1', mode: 'speak', text: 'Goedemorgen, Devoxx.' },
    { id: 'gag', trigger: 'slide:8', mode: 'speak', text: 'Oh, I know this one.' },
  ],
}

function brain(robot: string, onRobot: number, sending = 0) {
  vi.stubGlobal('WebSocket', class {
    onopen = null; onmessage = null; onclose = null; onerror = null
    close() { /* nothing */ }
  })
  const status = {
    active: true, title: 'Devoxx', beats_total: 2, fired: [], slides_state: 'live',
    recordings: { ready: 2, total: 2, failed: 0, rendering: 0, on_robot: onRobot,
                  robot, sending, beats: { hello: 'ready', gag: 'ready' } },
  }
  vi.stubGlobal('fetch', (url: string, init?: RequestInit) => {
    const u = String(url)
    if (u.includes('/presentation/scenarios')) return OK({ scenarios: [] })
    if (u.includes('/presentation/scenario') && init?.method !== 'POST') return OK({ scenario: TALK })
    if (u.includes('/presentation/status')) return OK(status)
    return OK({})
  })
}

beforeEach(() => {
  vi.unstubAllGlobals()
  setActivePinia(createPinia())
})

async function summary(): Promise<string> {
  const w = mount(PresentView)
  await flushPromises(); await flushPromises()
  return w.find('[data-test="recordings"]').text()
}

describe('U410 — which lines are already on the robot', () => {
  it('says how many he holds', async () => {
    brain('holds', 2)
    expect(await summary()).toContain('2 on the robot')
  })

  it('says while they are still being sent', async () => {
    brain('holds', 1, 1)
    expect(await summary()).toMatch(/sending 1 to the robot/)
  })

  it('says an older robot gets each line at its cue, instead of a zero', async () => {
    brain('older', 0)
    const text = await summary()
    expect(text).toMatch(/older/)
    expect(text).not.toContain('0 on the robot')
  })
})
