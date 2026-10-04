import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises, enableAutoUnmount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import AppHeader from '../../src/components/shell/AppHeader.vue'
import TalkView from '../../src/views/TalkView.vue'
import { routeEvent } from '../../src/components/canvas/mindRoutes'
import { useModeStore } from '../../src/stores/modeStore'
import { useKnowledgeStore } from '../../src/stores/knowledgeStore'
import { useRobotStore } from '../../src/stores/robotStore'

/** U406: at a stand nobody on screen has a name.
 *
 *  Asked as (translated): "deal with this too — what is the impact actually,
 *  what has to happen?" — of the header's who-is-talking chip, left over from
 *  U405. It named the owner ("Jan · owner") the whole time; it switched by
 *  itself to the name of anyone the camera recognised (a colleague, a child),
 *  as did the camera tag and the Mind panel; one tap listed the household with
 *  their roles; and a visitor could switch who the brain thinks is speaking,
 *  which follows the owner back to Work. In what he SAYS at a stand none of it
 *  mattered (U397) — this is about the screen, and about what it leaves behind.
 */

enableAutoUnmount(afterEach)

const HOUSEHOLD = [
  { person_id: 'jan', display_name: 'Jan', role: 'owner' },
  { person_id: 'elke', display_name: 'Elke', role: 'family' },
]

beforeEach(() => {
  setActivePinia(createPinia())
  vi.stubGlobal('fetch', () => Promise.resolve({
    ok: true, status: 200, json: () => Promise.resolve({}),
  } as Response))
  vi.stubGlobal('WebSocket', class {
    onopen = null; onmessage = null; onclose = null; onerror = null
    close(): void {}
  })
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => setTimeout(() => cb(0), 0) as unknown as number)
  vi.stubGlobal('cancelAnimationFrame', (id: number) => clearTimeout(id))
  vi.stubGlobal('ResizeObserver', class { observe(): void {} unobserve(): void {} disconnect(): void {} })
})
afterEach(() => vi.unstubAllGlobals())

function setUp(mode: 'work' | 'stand') {
  useModeStore().mode = mode
  const knowledge = useKnowledgeStore()
  knowledge.people = HOUSEHOLD as never
  knowledge.speaker = 'jan'
  return knowledge
}

describe('U406 — the header chip at a stand', () => {
  it('names the speaker at work (the control)', () => {
    setUp('work')
    const w = mount(AppHeader, { props: { wsStatus: 'open' } })
    expect(w.find('.who-chip').text()).toContain('Jan')
  })

  it('at a stand it says visitors, not who you are', () => {
    setUp('stand')
    const w = mount(AppHeader, { props: { wsStatus: 'open' } })
    const chip = w.find('.who-chip').text()
    expect(chip).toMatch(/visitor/i)
    expect(chip).not.toContain('Jan')
  })

  it('at a stand a tap neither switches the speaker nor lists the household', async () => {
    const knowledge = setUp('stand')
    const w = mount(AppHeader, { props: { wsStatus: 'open' } })
    await w.find('.who-chip').trigger('click')
    await w.find('.who-more').trigger('click')
    await flushPromises()
    expect(knowledge.speaker).toBe('jan')
    expect(w.text()).not.toContain('Elke')
  })
})

describe('U406 — a face he knows, at a stand', () => {
  it('does not become the speaker', () => {
    const knowledge = setUp('stand')
    knowledge.setSpeaker('elke', 'face')
    expect(knowledge.speaker).toBe('jan')
  })

  it('still does at work', () => {
    const knowledge = setUp('work')
    knowledge.setSpeaker('elke', 'face')
    expect(knowledge.speaker).toBe('elke')
  })

  it('is "someone" on the camera tag', async () => {
    setUp('stand')
    const robot = useRobotStore()
    robot.connected = true
    robot.lastRecognized = { person_id: 'elke', display_name: 'Elke', known: true, confidence: 0.87 } as never
    const w = mount(TalkView)
    await flushPromises()
    expect(w.text()).toContain('someone in view')
    expect(w.text()).not.toContain('Elke')
  })

  it('is "someone" in the Mind panel', () => {
    const event = { event_type: 'PersonRecognized', display_name: 'Elke', confidence: 0.87 }
    expect(routeEvent(event, { atStand: false })?.word).toContain('Elke')
    expect(routeEvent(event, { atStand: true })?.word).not.toContain('Elke')
  })
})
