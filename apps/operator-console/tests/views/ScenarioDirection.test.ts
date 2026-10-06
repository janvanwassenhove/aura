import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises, enableAutoUnmount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import ScenarioBuilder from '../../src/components/ScenarioBuilder.vue'
import RobotView from '../../src/views/RobotView.vue'
import PresentView from '../../src/views/PresentView.vue'

/** U409: a scenario directs HOW a line is spoken, and a directed line sounds
 *  the same every time.
 *
 *  Reported (translated): "In the presentation scenario I want to define not
 *  only the persona and the voice, but also the direction: powerful, short,
 *  emotional, …" — and the same line on the same slide sounded different on
 *  every run, and started late. The brain now records each fixed line once and
 *  plays the recording; these are the places the presenter writes a direction,
 *  sees which lines are ready, and asks for another take.
 *
 *  No vue-tsc here: a field the template reads and the brain does not send is
 *  a blank in front of the owner, so each is mounted against brain-shaped data.
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
      learned_traits: '', voice_direction: 'dry, unhurried, understated' },
  ],
}

function brain(status: unknown = { active: false }, scenario: unknown = null) {
  const posted: { url: string; body: Record<string, unknown> }[] = []
  vi.stubGlobal('WebSocket', class {
    onopen = null; onmessage = null; onclose = null; onerror = null
    close() { /* nothing */ }
  })
  vi.stubGlobal('fetch', (url: string, init?: RequestInit) => {
    const u = String(url)
    if (init?.method === 'POST') posted.push({ url: u, body: JSON.parse(String(init.body ?? '{}')) })
    if (u.includes('/setup/characters')) return OK(CHARACTERS)
    if (u.includes('/presentation/scenarios')) return OK({ scenarios: [] })
    if (u.includes('/presentation/scenario') && init?.method !== 'POST') return OK({ scenario })
    if (u.includes('/presentation/rerecord')) return OK(status)
    if (u.includes('/presentation/status')) return OK(status)
    return OK({})
  })
  return posted
}

beforeEach(() => {
  vi.unstubAllGlobals()
  setActivePinia(createPinia())
})

describe('U409 — the builder writes how a line is delivered', () => {
  async function built() {
    brain()
    const w = mount(ScenarioBuilder)
    await flushPromises()
    return w
  }
  async function started(w: ReturnType<typeof mount>) {
    await w.find('button.sb-btn--go').trigger('click')
    return w.emitted('start')![0][0] as Record<string, any>
  }

  it('offers a direction for the whole talk and for each beat, as a short note', async () => {
    const w = await built()
    for (const sel of ['input.sb-scenario-direction', 'input.sb-direction']) {
      const input = w.find(sel)
      expect(input.exists(), sel).toBe(true)
      expect(input.attributes('maxlength')).toBe('300')
    }
  })

  it('sends both when written', async () => {
    const w = await built()
    await w.find('textarea.sb-text').setValue('Oh, I know this one.')
    await w.find('input.sb-scenario-direction').setValue('warm, unhurried')
    await w.find('input.sb-direction').setValue('powerful, short')
    const out = await started(w)
    expect(out.direction).toBe('warm, unhurried')
    expect(out.beats[0].direction).toBe('powerful, short')
  })

  it('leaves both out when nothing is written', async () => {
    const w = await built()
    await w.find('textarea.sb-text').setValue('Hi.')
    const out = await started(w)
    expect('direction' in out).toBe(false)
    expect('direction' in out.beats[0]).toBe(false)
  })

  it('keeps them through a load and a save', async () => {
    const w = await built()
    ;(w.vm as any).loadScenario({
      title: 'T', direction: 'warm',
      beats: [{ id: 'gag', trigger: 'manual', mode: 'speak', text: 'Ta.', direction: 'whispered' }],
    })
    await w.vm.$nextTick()
    expect((w.find('input.sb-scenario-direction').element as HTMLInputElement).value).toBe('warm')
    const out = await started(w)
    expect(out.direction).toBe('warm')
    expect(out.beats[0].direction).toBe('whispered')
  })
})

describe('U409 — a persona has its own way of speaking', () => {
  it('is shown and saved in its editor', async () => {
    const posted = brain()
    const w = mount(RobotView)
    await flushPromises(); await flushPromises()
    await w.find('button[title="Edit this persona"]').trigger('click')
    const field = w.find('[aria-label="Voice direction"]')
    expect((field.element as HTMLInputElement).value).toBe('dry, unhurried, understated')
    expect(field.attributes('maxlength')).toBe('300')
    await field.setValue('dry, very slow')
    const save = w.findAll('button').find(b => b.text().startsWith('Save persona'))!
    await save.trigger('click')
    await flushPromises()
    const sent = posted.find(p => p.url.includes('/setup/characters/dry_tech_butler'))
    expect(sent?.body.voice_direction).toBe('dry, very slow')
  })
})

describe('U409 — the Present view says which lines are recorded', () => {
  const TALK = {
    title: 'Devoxx',
    beats: [
      { id: 'hello', trigger: 'slide:1', mode: 'speak', text: 'Goedemorgen, Devoxx.' },
      { id: 'gag', trigger: 'slide:8', mode: 'speak', text: 'Oh, I know this one.' },
      { id: 'riff', trigger: 'keyword:Java', mode: 'chime_in', topic: 'kids' },
    ],
  }
  const STATUS = {
    active: true, title: 'Devoxx', beats_total: 3, fired: [], slides_state: 'live',
    recordings: { ready: 1, total: 2, failed: 1, rendering: 0,
                  beats: { hello: 'ready', gag: 'failed' } },
  }

  async function present() {
    const posted = brain(STATUS, TALK)
    const w = mount(PresentView)
    await flushPromises(); await flushPromises()
    return { w, posted }
  }

  it('says how many lines are ready, and how many failed', async () => {
    const { w } = await present()
    const summary = w.find('[data-test="recordings"]')
    expect(summary.exists()).toBe(true)
    expect(summary.text()).toContain('1 of 2')
    expect(summary.text()).toMatch(/1 failed/)
  })

  it('marks each spoken line, and not the improvised one', async () => {
    const { w } = await present()
    const marks = w.findAll('[data-test="beat-recording"]')
    expect(marks.map(m => m.attributes('data-state'))).toEqual(['ready', 'failed'])
  })

  it('asks for another take of one line', async () => {
    const { w, posted } = await present()
    const again = w.findAll('[data-test="rerecord"]')
    expect(again.length).toBe(2)
    await again[1].trigger('click')
    await flushPromises()
    const sent = posted.find(p => p.url.includes('/presentation/rerecord'))
    expect(sent?.body).toEqual({ beat_id: 'gag' })
  })
})
