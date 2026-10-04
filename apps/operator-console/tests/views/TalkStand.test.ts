import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises, enableAutoUnmount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import TalkView from '../../src/views/TalkView.vue'
import { useModeStore } from '../../src/stores/modeStore'
import { useConversationStore } from '../../src/stores/conversationStore'
import { useKnowledgeStore } from '../../src/stores/knowledgeStore'

/** U405: at a stand the laptop's screen is in view too.
 *
 *  Asked for as (translated): "the laptop screen still shows personal things
 *  in Stand: the Next up card and the Today's agenda button — change this, with
 *  a notification (stand mode)". U397 kept all of it out of what he is told;
 *  the screen still showed the agenda, the briefing buttons, the household by
 *  name, and the whole conversation from Work. */

enableAutoUnmount(afterEach)

let fetched: string[] = []

beforeEach(() => {
  setActivePinia(createPinia())
  fetched = []
  vi.stubGlobal('fetch', (url: string) => {
    fetched.push(String(url))
    return Promise.resolve({
      ok: true, status: 200,
      json: () => Promise.resolve({ result: '09:30 Dentist\n14:00 Board meeting' }),
    } as Response)
  })
  vi.stubGlobal('WebSocket', class {
    onopen = null; onmessage = null; onclose = null; onerror = null
    close(): void {}
  })
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => setTimeout(() => cb(0), 0) as unknown as number)
  vi.stubGlobal('cancelAnimationFrame', (id: number) => clearTimeout(id))
  vi.stubGlobal('ResizeObserver', class { observe(): void {} unobserve(): void {} disconnect(): void {} })
})
afterEach(() => vi.unstubAllGlobals())

async function talkIn(mode: 'work' | 'stand') {
  useModeStore().mode = mode
  const knowledge = useKnowledgeStore()
  knowledge.people = [{ person_id: 'elke', display_name: 'Elke', role: 'family' }] as never
  knowledge.speaker = null
  const w = mount(TalkView)
  await flushPromises(); await flushPromises()
  return w
}

describe('U405 — the screen at a stand', () => {
  it('at work the agenda, briefings and household are there (the control)', async () => {
    const w = await talkIn('work')
    expect(w.text()).toContain('Next up')
    expect(w.text()).toContain('Today’s agenda')
    expect(w.text()).toContain('Elke')
  })

  it('at a stand there is no agenda — not shown, not even fetched', async () => {
    const w = await talkIn('stand')
    expect(w.text()).not.toContain('Next up')
    expect(w.text()).not.toContain('Dentist')
    expect(fetched.some(u => u.includes('/connector/calendar'))).toBe(false)
  })

  it('at a stand the buttons are for visitors, not for you', async () => {
    const w = await talkIn('stand')
    const text = w.text()
    for (const mine of ['Brief me', 'What did I miss?', 'Today’s agenda']) expect(text).not.toContain(mine)
    expect(text).toContain('Introduce yourself')
  })

  it('at a stand the household is not listed', async () => {
    const w = await talkIn('stand')
    expect(w.text()).not.toContain('Elke')
  })

  it('says it is a stand, and what is kept off the screen', async () => {
    const w = await talkIn('stand')
    const notice = w.find('[data-test="stand-notice"]')
    expect(notice.exists()).toBe(true)
    expect(notice.text()).toMatch(/stand/i)
    expect(notice.text()).toMatch(/agenda/i)
    const work = await talkIn('work')
    expect(work.find('[data-test="stand-notice"]').exists()).toBe(false)
  })

  it("what was said at work is not on the stand's screen, and comes back after", async () => {
    const modes = useModeStore()
    const convo = useConversationStore()
    modes.mode = 'work'
    convo.addTurn({ id: '1', role: 'user', text: 'the Acme merger closes Friday', timestamp: '' })
    modes.mode = 'stand'
    convo.addTurn({ id: '2', role: 'user', text: 'hello robot', timestamp: '' })
    const w = mount(TalkView)
    await flushPromises()
    expect(w.text()).not.toContain('Acme')
    expect(w.text()).toContain('hello robot')
    modes.mode = 'work'
    await flushPromises()
    expect(w.text()).toContain('Acme')
    expect(w.text()).not.toContain('hello robot')
  })
})
