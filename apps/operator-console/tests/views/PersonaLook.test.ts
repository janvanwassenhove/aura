import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises, enableAutoUnmount } from '@vue/test-utils'
import { afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import RobotView from '../../src/views/RobotView.vue'
import OverlayView from '../../src/views/OverlayView.vue'
import { usePresentationStore } from '../../src/stores/presentationStore'

/** U404: asked for as (translated) "make it possible" — the projector's avatar
 *  changing with a beat's `persona:`. The subtitle said who was speaking
 *  (U349); the picture stayed the header's character. A persona now carries a
 *  look, set in its editor, and the overlay shows the look of whoever speaks.
 */

vi.mock('../../src/composables/useCameraFeed', async () => {
  const { ref } = await import('vue')
  return { useCameraFeed: () => ({ frameSrc: ref(''), state: ref('off'), bump: () => {} }) }
})

enableAutoUnmount(afterEach)

const OK = (body: unknown) => Promise.resolve({
  ok: true, status: 200, json: () => Promise.resolve(body),
} as Response)

const CHARACTERS = {
  active: 'dry_tech_butler',
  characters: [
    { id: 'dry_tech_butler', display_name: 'Dry Tech Butler', look: 'slab', character_prompt: '',
      verbosity: 'brief', humor_level: 'low', voice_id: 'ash', interruptibility: 'wake_word',
      learned_traits: '' },
    { id: 'kids_companion', display_name: 'Kids Companion', look: 'buddy', character_prompt: '',
      verbosity: 'brief', humor_level: 'high', voice_id: 'nova', interruptibility: 'vad',
      learned_traits: '' },
  ],
}

function brain() {
  const posted: { url: string; body: Record<string, unknown> }[] = []
  vi.stubGlobal('WebSocket', class {
    onopen = null; onmessage = null; onclose = null; onerror = null
    close() { /* nothing */ }
  })
  vi.stubGlobal('fetch', (url: string, init?: RequestInit) => {
    const u = String(url)
    if (init?.method === 'POST') posted.push({ url: u, body: JSON.parse(String(init.body ?? '{}')) })
    if (u.includes('/setup/characters')) return OK(CHARACTERS)
    if (u.includes('/presentation/status')) return OK({ active: true })
    return OK({})
  })
  return posted
}

describe('U404 — the projector shows who is speaking', () => {
  beforeEach(() => {
    vi.unstubAllGlobals()
    setActivePinia(createPinia())
    window.location.hash = '#overlay?mode=audience'
  })

  it("shows the speaking persona's look, and the header's character otherwise", async () => {
    brain()
    const w = mount(OverlayView)
    await flushPromises(); await flushPromises()
    const look = () => w.find('.ov-avatar').attributes('data-look')
    expect(look()).toBe('scout')                       // the header's default

    usePresentationStore().applyEvent({
      event_type: 'PresentationSubtitle', text: 'Goedendag. U wenst?', duration_s: 2,
      persona: 'dry_tech_butler' })
    await flushPromises()
    expect(look()).toBe('slab')

    usePresentationStore().applyEvent({
      event_type: 'PresentationSubtitle', text: 'Hoi hoi!', duration_s: 1, persona: 'kids_companion' })
    await flushPromises()
    expect(look()).toBe('buddy')

    usePresentationStore().applyEvent({
      event_type: 'PresentationSubtitle', text: 'Back to me.', duration_s: 1, persona: '' })
    await flushPromises()
    expect(look()).toBe('scout'), 'a line in the talk\'s own voice is the header character'
  })

  it('a persona is given its look in its editor', async () => {
    const posted = brain()
    const w = mount(RobotView)
    await flushPromises(); await flushPromises()
    await w.find('button[title="Edit this persona"]').trigger('click')
    const select = w.find('select[aria-label="Look"]')
    expect((select.element as HTMLSelectElement).value).toBe('slab')
    await select.setValue('grump')
    const save = w.findAll('button').find(b => b.text().startsWith('Save persona'))!
    await save.trigger('click')
    await flushPromises()
    const sent = posted.find(p => p.url.includes('/setup/characters/dry_tech_butler'))
    expect(sent?.body.look).toBe('grump')
  })
})
