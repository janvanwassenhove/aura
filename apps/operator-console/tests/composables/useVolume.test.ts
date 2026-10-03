import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { useVolume } from '../../src/composables/useVolume'
import { playbackVolume, setPlaybackVolume } from '../../src/composables/useSpeechPlayback'
import TalkView from '../../src/views/TalkView.vue'

/** U399: "I have the impression the volume slider has no effect" (translated).
 *
 *  It had none that could be heard: his words went through this laptop, which
 *  the slider never touched, and his emotions through the robot's own mixer,
 *  which the runtime held at 100 %. And the Talk screen's slider started at 80
 *  whatever the robot was set to — a guess dressed as a reading.
 */

const OK = (body: unknown) => Promise.resolve({
  ok: true, status: 200, json: () => Promise.resolve(body),
} as Response)

function robotAt(level: number) {
  const posted: unknown[] = []
  vi.stubGlobal('fetch', (url: string, init?: RequestInit) => {
    const u = String(url)
    if (u.includes('/robot/volume')) {
      if (init?.method === 'POST') {
        const body = JSON.parse(String(init.body))
        posted.push(body)
        return OK({ volume: body.volume })
      }
      return OK({ volume: level })
    }
    return OK({})
  })
  return posted
}

describe('U399 — one volume, wherever he speaks', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    setPlaybackVolume(1)
    useVolume().level.value = 80
  })

  it("reads the robot's real level instead of showing a guess", async () => {
    robotAt(0.18)
    await useVolume().load()
    expect(useVolume().level.value).toBe(18)
    expect(playbackVolume()).toBeCloseTo(0.18)
  })

  it('sets the robot and this laptop alike', async () => {
    const posted = robotAt(0.8)
    const v = useVolume()
    v.level.value = 40
    await v.save()
    expect(posted).toEqual([{ volume: 0.4 }])
    expect(playbackVolume()).toBeCloseTo(0.4)
  })

  it('with the robot away, this laptop still follows the slider', async () => {
    vi.stubGlobal('fetch', () => Promise.reject(new Error('offline')))
    const v = useVolume()
    v.level.value = 25
    await v.save()
    expect(playbackVolume()).toBeCloseTo(0.25)
  })

  it("the Talk screen's slider shows the robot's level once mounted", async () => {
    robotAt(0.18)
    const w = mount(TalkView, { global: { stubs: { teleport: true } } })
    await flushPromises(); await flushPromises()
    const slider = w.find('input[aria-label="Volume"]').element as HTMLInputElement
    expect(slider.value).toBe('18')
  })
})
