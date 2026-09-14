import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises, enableAutoUnmount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import CameraPreview from '../../src/components/CameraPreview.vue'

/** U358: the robot's live view as something you can switch off.
 *
 *  `useCameraFeed` starts its frame loop on mount and stops it on unmount, so
 *  where it is called decides how long the robot is polled over WiFi. Wrapping
 *  it in a component makes a `v-if` the on/off switch — which is the whole
 *  reason this exists rather than another inlined `<img>`.
 */

let frames = 0

function stubFetch(ok = true) {
  frames = 0
  vi.stubGlobal('fetch', async (url: string) => {
    if (!String(url).includes('camera/frame.jpg')) {
      return { ok: true, json: async () => ({}) } as unknown as Response
    }
    frames += 1
    if (!ok) throw new Error('robot down')
    return { ok: true, blob: async () => new Blob(['jpeg-bytes']) } as unknown as Response
  })
}

// Every mounted preview keeps polling until it is unmounted - which is the
// behaviour under test, so a leaked one from an earlier case would count
// its frames into the next.
enableAutoUnmount(afterEach)

beforeEach(() => {
  vi.unstubAllGlobals()
  setActivePinia(createPinia())
  URL.createObjectURL = vi.fn(() => 'blob:frame')
  URL.revokeObjectURL = vi.fn()
})
afterEach(() => vi.unstubAllGlobals())

describe('CameraPreview', () => {
  it('shows what the robot sees', async () => {
    stubFetch()
    const w = mount(CameraPreview)
    await flushPromises()

    expect(w.find('.cam-img').exists()).toBe(true)
    expect(w.find('.cam-img').attributes('src')).toBe('blob:frame')
  })

  it('says it is looking rather than showing an empty grey box', async () => {
    stubFetch(false)
    const w = mount(CameraPreview)
    await flushPromises()

    expect(w.find('.cam-img').exists()).toBe(false)
    expect(w.text()).toContain('Looking')
  })

  it('stops polling the robot when it is taken off screen', async () => {
    stubFetch()
    const w = mount(CameraPreview)
    await flushPromises()
    expect(frames).toBeGreaterThan(0)

    w.unmount()
    const after = frames
    await new Promise(r => setTimeout(r, 250))

    // The point of the component: no window on screen, no WiFi traffic.
    expect(frames).toBe(after)
  })

  it('takes an alt that names who is being looked at', async () => {
    stubFetch()
    const w = mount(CameraPreview, { props: { alt: 'What he sees while learning Jan' } })
    await flushPromises()

    expect(w.find('.cam-img').attributes('alt')).toBe('What he sees while learning Jan')
  })
})
