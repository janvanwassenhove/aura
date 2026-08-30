import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'
import { setActivePinia, createPinia } from 'pinia'
import OverlayView from '../../src/views/OverlayView.vue'

// A camera that is always producing a frame, so "is it shown?" tests the FLAG
// and not whether a robot happens to be plugged in.
vi.mock('../../src/composables/useCameraFeed', () => ({
  useCameraFeed: () => ({ frameSrc: ref('data:image/jpeg;base64,AAAA'),
                          state: ref('live'), bump: () => {} }),
}))

/** U269: the overlay showed no cues, ever.
 *
 *  It is a SEPARATE WINDOW with its own Pinia store, and the beat list it read
 *  was only ever filled by `PresentView.startScenario` — in the console window.
 *  So `presenter.beats` was permanently empty on the projector, `nextCue`
 *  computed to '' and the row it belongs to never rendered. Reported as "nor
 *  for the overlay did i see cues, warnings, subtitles or anything".
 *
 *  It now asks the brain, which is the one thing both windows share.
 */

const OK = (body: unknown) => Promise.resolve({
  ok: true, status: 200, json: () => Promise.resolve(body),
} as Response)

const SCENARIO = {
  title: 'my talk',
  beats: [
    { id: 'b1', trigger: 'slide:7', mode: 'speak', text: 'the opening line' },
    { id: 'b2', trigger: 'keyword:Java', mode: 'speak', text: 'the java remark' },
  ],
}

function stubFetch(status: Record<string, unknown> = {}) {
  vi.stubGlobal('WebSocket', class {
    onopen: (() => void) | null = null
    onmessage: (() => void) | null = null
    onclose: (() => void) | null = null
    onerror: (() => void) | null = null
    close() { /* nothing to close */ }
  })
  vi.stubGlobal('fetch', (url: string) => {
    const u = String(url)
    if (u.includes('/presentation/scenario')) return OK({ scenario: SCENARIO })
    if (u.includes('/presentation/status')) {
      return OK({ active: true, title: 'my talk', slides_state: 'live',
                  deck: 'deck.pptx', slide: 7, slide_total: 40, fired: [], ...status })
    }
    return OK({})
  })
}

beforeEach(() => {
  vi.unstubAllGlobals()
  setActivePinia(createPinia())
  window.location.hash = '#overlay?mode=presenter'
})

describe('U269 — the overlay knows the show it is drawn over', () => {
  it('renders the next cue, which it could never do before', async () => {
    stubFetch()
    const w = mount(OverlayView)
    await flushPromises()
    await flushPromises()

    const text = w.text()
    expect(text).toContain('Slide 7')            // the cue, from the brain
    expect(text).toContain('the opening line')
  })

  it('says when a beat fired but nobody heard it', async () => {
    // U269: the console filled in "all beats done" while the room heard
    // silence, and nothing anywhere said why.
    stubFetch({ speech_error: 'no robot is connected' })
    const w = mount(OverlayView)
    await flushPromises()
    await flushPromises()

    expect(w.text()).toContain('could not be heard')
    expect(w.text()).toContain('no robot is connected')
  })

  it('shows his camera only when the overlay was asked for it', async () => {
    stubFetch()
    const off = mount(OverlayView)
    await flushPromises()
    expect(off.find('.ov-cam').exists()).toBe(false)

    // Pointing a live camera at a room and projecting it back is a decision,
    // so it takes an explicit flag — never a default. The frame is always
    // available here (the composable is mocked), so this tests the FLAG.
    window.location.hash = '#overlay?mode=presenter&camera=1'
    const on = mount(OverlayView)
    await flushPromises()
    expect(on.find('.ov-cam').exists()).toBe(true)
    expect(on.find('.ov-cam-img').attributes('src')).toContain('base64')
  })

  it('keeps the presenter strip off the audience layer', async () => {
    stubFetch()
    window.location.hash = '#overlay?mode=audience'
    const w = mount(OverlayView)
    await flushPromises()
    await flushPromises()

    // Cues, warnings and "he was not heard" are the presenter's business —
    // a room must never read the machinery of the talk it is watching.
    expect(w.find('.ov-cues').exists()).toBe(false)
    expect(w.text()).not.toContain('Slide 7')
  })
})
