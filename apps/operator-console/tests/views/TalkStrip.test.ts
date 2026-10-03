import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises, enableAutoUnmount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import TalkView from '../../src/views/TalkView.vue'
import { usePrefsStore } from '../../src/stores/prefsStore'

/** U390: the activity log under the conversation can be resized by its top
 *  edge. Reported as "i should be able to drag/resize bottom window in talk
 *  screen", with the log squeezed to two lines: it was `flex: 0 1 150px`, so
 *  it shrank whenever the conversation wanted room and could not be grown. */

const OK = (body: unknown) => Promise.resolve({
  ok: true, status: 200, json: () => Promise.resolve(body),
  text: () => Promise.resolve(JSON.stringify(body)),
  blob: () => Promise.resolve(new Blob([])),
} as unknown as Response)

enableAutoUnmount(afterEach)

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
  vi.stubGlobal('fetch', (url: string) => {
    const u = String(url)
    if (u.includes('/setup/prefs')) return OK({ voice_mode: 'off', voice_engine: 'pipeline' })
    if (u.includes('/logs/recent')) return OK({ records: [] })
    return OK({})
  })
  vi.stubGlobal('WebSocket', class {
    onopen = null; onclose = null; onerror = null; onmessage = null; readyState = 0
    close(): void { /* nothing */ } send(): void { /* nothing */ }
  })
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => setTimeout(() => cb(0), 0) as unknown as number)
  vi.stubGlobal('cancelAnimationFrame', (id: number) => clearTimeout(id))
  vi.stubGlobal('ResizeObserver', class { observe(): void {} unobserve(): void {} disconnect(): void {} })
  URL.createObjectURL = vi.fn(() => 'blob:x')
  URL.revokeObjectURL = vi.fn()
})
afterEach(() => vi.unstubAllGlobals())

async function talkAtFull() {
  usePrefsStore().density = 'full'
  const w = mount(TalkView)
  await flushPromises()
  return w
}

const basis = (el: Element) => (el as HTMLElement).style.flex

describe('U390 — the Talk screen log can be resized', () => {
  it('has a grip on its top edge that says what it is', async () => {
    const w = await talkAtFull()
    const grip = w.find('[data-activity-strip] [role="separator"]')
    expect(grip.exists()).toBe(true)
    expect(grip.attributes('aria-orientation')).toBe('horizontal')
    expect(grip.attributes('tabindex')).toBe('0')
  })

  it('dragging the grip up makes the log taller, and it stays that way', async () => {
    const w = await talkAtFull()
    const strip = w.find('[data-activity-strip]')
    const grip = strip.find('[role="separator"]')

    await grip.trigger('pointerdown', { clientY: 600, pointerId: 1 })
    await grip.trigger('pointermove', { clientY: 450, pointerId: 1 })
    await grip.trigger('pointerup', { clientY: 450, pointerId: 1 })

    expect(basis(strip.element)).toContain('300px')
    expect(localStorage.getItem('aura-talk-strip')).toBe('300')
  })

  it('does not shrink away when the conversation wants the room', async () => {
    const w = await talkAtFull()
    expect(basis(w.find('[data-activity-strip]').element)).toMatch(/^0 0 /)
  })
})

describe('U391 — the Stop button while he drives the screen', () => {
  it('appears when he takes control, and stops him when pressed', async () => {
    const calls: string[] = []
    vi.stubGlobal('fetch', (url: string, init?: RequestInit) => {
      calls.push(`${init?.method ?? 'GET'} ${String(url)}`)
      if (String(url).includes('/computeruse/status')) return OK({ active: true })
      return OK({})
    })
    const { useConversationStore } = await import('../../src/stores/conversationStore')
    const w = mount(TalkView)
    await flushPromises()
    expect(w.text()).not.toContain('Stop screen control')

    useConversationStore().applyEvent({ event_type: 'ComputerControlStarted', goal: 'x' })
    await flushPromises()
    const stop = w.findAll('button').find(b => b.text().includes('Stop screen control'))
    expect(stop).toBeTruthy()

    await stop!.trigger('click')
    await flushPromises()
    expect(calls.some(c => c.startsWith('POST') && c.includes('/orchestrator/computeruse/abort'))).toBe(true)
  })
})

