import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises, enableAutoUnmount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import PeopleView from '../../src/views/PeopleView.vue'
import { useKnowledgeStore } from '../../src/stores/knowledgeStore'

/** U358: asked for as "show camera view while it's detecting, so i know it's
 *  teaching the right face".
 *
 *  Taken literally it would not help: the four photos are captured in about a
 *  second and a half, less than a first frame takes to arrive, so a picture
 *  that appears *during* detection shows up after the decision was made. The
 *  camera therefore comes FIRST — look, then press — which is the shape the
 *  setup wizard has always used and the Robot panel never did.
 */

const PERSON = {
  person: { person_id: 'jan', display_name: 'Jan', role: 'owner' },
  facts: [], signals: [],
}

function stubFetch() {
  vi.stubGlobal('fetch', async (url: string) => {
    const u = String(url)
    if (u.includes('camera/frame.jpg')) {
      return { ok: true, blob: async () => new Blob(['jpeg']) } as unknown as Response
    }
    if (u.includes('/recognition/status')) {
      return { ok: true, json: async () => ({ enabled: true, enrolled: [] }) } as unknown as Response
    }
    return { ok: true, json: async () => ({}) } as unknown as Response
  })
}

enableAutoUnmount(afterEach)

beforeEach(() => {
  vi.unstubAllGlobals()
  setActivePinia(createPinia())
  URL.createObjectURL = vi.fn(() => 'blob:frame')
  URL.revokeObjectURL = vi.fn()
  stubFetch()
})
afterEach(() => vi.unstubAllGlobals())

async function openPerson() {
  const w = mount(PeopleView)
  const knowledge = useKnowledgeStore()
  knowledge.detail = PERSON as never
  await flushPromises()
  return { w, knowledge }
}

describe('U358 — you can see whose face you are teaching', () => {
  it('keeps the camera off until it is asked for', async () => {
    const { w } = await openPerson()

    // Not shyness about pixels: mounted here it would fetch frames from the
    // robot over WiFi for as long as anybody had a person open.
    expect(w.find('[data-test="teach-box"]').exists()).toBe(false)
    expect(w.find('.cam-img').exists()).toBe(false)
  })

  it('shows the robot camera when Teach face is pressed', async () => {
    const { w } = await openPerson()

    const teach = w.findAll('button').find(b => b.text() === 'Teach face')
    expect(teach, 'no Teach face button').toBeTruthy()
    await teach!.trigger('click')
    await flushPromises()

    expect(w.find('[data-test="teach-box"]').exists()).toBe(true)
    expect(w.find('.cam-img').exists()).toBe(true)
  })

  it('names the person in the picture, so the check is possible', async () => {
    const { w } = await openPerson()
    await w.findAll('button').find(b => b.text() === 'Teach face')!.trigger('click')
    await flushPromises()

    expect(w.find('[data-test="teach-box"]').text()).toContain('Jan')
  })

  it('only takes the photos on the second, deliberate press', async () => {
    const { w, knowledge } = await openPerson()
    const teachFace = vi.spyOn(knowledge, 'teachFace').mockResolvedValue('✓ Face detected')

    await w.findAll('button').find(b => b.text() === 'Teach face')!.trigger('click')
    await flushPromises()
    expect(teachFace).not.toHaveBeenCalled()      // opening is not capturing

    await w.find('[data-test="teach-go"]').trigger('click')
    await flushPromises()
    expect(teachFace).toHaveBeenCalledWith('jan')
  })

  it('leaves the picture up with the result, not just the words', async () => {
    const { w, knowledge } = await openPerson()
    vi.spyOn(knowledge, 'teachFace').mockResolvedValue('✓ Face detected — learned Jan (4 samples).')

    await w.findAll('button').find(b => b.text() === 'Teach face')!.trigger('click')
    await flushPromises()
    await w.find('[data-test="teach-go"]').trigger('click')
    await flushPromises()

    // The message is about the face that was just in shot. Closing the camera
    // as it arrives would take away the one thing that says whether it was
    // the right person.
    expect(w.find('[data-test="teach-box"]').exists()).toBe(true)
    expect(w.find('.cam-img').exists()).toBe(true)
    expect(w.text()).toContain('learned Jan')
  })

  it('puts the camera away again on Close', async () => {
    const { w } = await openPerson()
    await w.findAll('button').find(b => b.text() === 'Teach face')!.trigger('click')
    await flushPromises()

    await w.findAll('button').find(b => b.text() === 'Close')!.trigger('click')
    await flushPromises()

    expect(w.find('[data-test="teach-box"]').exists()).toBe(false)
    expect(w.find('.cam-img').exists()).toBe(false)
  })
})
