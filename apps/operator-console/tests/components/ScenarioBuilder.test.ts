import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ScenarioBuilder from '../../src/components/ScenarioBuilder.vue'

/** U349: a beat can be handed to another character, and the builder is where
 *  the presenter says so. The persona list comes from the brain — the console
 *  invents no characters of its own. */

const CHARACTERS = [
  { id: 'dry_tech_butler', display_name: 'Dry Tech Butler' },
  { id: 'kids_companion', display_name: 'Kids Companion' },
]

function stubFetch(characters = CHARACTERS) {
  const fetchMock = vi.fn(async (url: string) => {
    if (String(url).includes('/setup/characters')) {
      return { ok: true, json: async () => ({ characters }) } as unknown as Response
    }
    return { ok: true, json: async () => ({ scenarios: [] }) } as unknown as Response
  })
  ;(globalThis as any).fetch = fetchMock
  return fetchMock
}

async function settled(w: any) {
  await new Promise(r => setTimeout(r, 0))
  await w.vm.$nextTick()
}

beforeEach(() => { stubFetch() })

describe('ScenarioBuilder — per-beat persona', () => {
  it('offers the brain characters, and its own voice as the default', async () => {
    const w = mount(ScenarioBuilder)
    await settled(w)

    const select = w.find('select.sb-persona')
    expect(select.exists()).toBe(true)
    const options = select.findAll('option').map(o => o.text())
    expect(options[0]).toMatch(/presentation voice/i)
    expect(options).toContain('Dry Tech Butler')
    expect(select.element.value).toBe('')      // nothing is imposed
  })

  it('sends the chosen persona with the beat', async () => {
    const w = mount(ScenarioBuilder)
    await settled(w)

    await w.find('textarea.sb-text').setValue('Goedendag.')
    await w.find('select.sb-persona').setValue('dry_tech_butler')
    await w.find('button.sb-btn--go').trigger('click')

    const beats = (w.emitted('start')![0][0] as any).beats
    expect(beats[0].persona).toBe('dry_tech_butler')
  })

  it('leaves persona out entirely when none is chosen', async () => {
    const w = mount(ScenarioBuilder)
    await settled(w)

    await w.find('textarea.sb-text').setValue('Goedendag.')
    await w.find('button.sb-btn--go').trigger('click')

    const beats = (w.emitted('start')![0][0] as any).beats
    expect('persona' in beats[0]).toBe(false)
  })

  it('hydrates the persona when an existing scenario is loaded', async () => {
    const w = mount(ScenarioBuilder)
    await settled(w)

    ;(w.vm as any).loadScenario({
      title: 'T',
      beats: [{ id: 'a', trigger: 'manual', mode: 'speak', text: 'hi', persona: 'kids_companion' }],
    })
    await w.vm.$nextTick()

    expect((w.find('select.sb-persona').element as HTMLSelectElement).value)
      .toBe('kids_companion')
  })
})

describe('ScenarioBuilder — inline persona markers', () => {
  it('says nothing while every marker names a real character', async () => {
    const w = mount(ScenarioBuilder)
    await settled(w)

    await w.find('textarea.sb-text').setValue('a [persona:kids_companion] b')
    expect(w.find('.sb-persona-warn').exists()).toBe(false)
  })

  it('names an inline persona that does not exist, before the talk does', async () => {
    const w = mount(ScenarioBuilder)
    await settled(w)

    await w.find('textarea.sb-text').setValue('a [persona:kids_companionn] b')
    await w.vm.$nextTick()

    const warning = w.find('.sb-persona-warn')
    expect(warning.exists()).toBe(true)
    expect(warning.text()).toContain('kids_companionn')
  })

  it('warns without blocking — the scenario still starts', async () => {
    const w = mount(ScenarioBuilder)
    await settled(w)

    await w.find('textarea.sb-text').setValue('a [persona:nobody] b')
    await w.vm.$nextTick()
    await w.find('button.sb-btn--go').trigger('click')

    expect(w.emitted('start')).toBeTruthy()
  })

  it('keeps quiet when the character list could not be fetched', async () => {
    ;(globalThis as any).fetch = vi.fn(async () => { throw new Error('offline') })
    const w = mount(ScenarioBuilder)
    await settled(w)

    await w.find('textarea.sb-text').setValue('a [persona:kids_companion] b')
    await w.vm.$nextTick()

    // Everything would look wrong; a warning on every line would be noise.
    expect(w.find('.sb-persona-warn').exists()).toBe(false)
  })
})

/** U352: when the overlay is on the projector, said in the scenario. */
describe('ScenarioBuilder — the projector', () => {
  it('leaves the overlay alone unless a beat says otherwise', async () => {
    const w = mount(ScenarioBuilder)
    await settled(w)

    await w.find('textarea.sb-text').setValue('Hallo.')
    await w.find('button.sb-btn--go').trigger('click')

    const scenario = w.emitted('start')![0][0] as any
    expect('overlay' in scenario).toBe(false)
    expect('overlay' in scenario.beats[0]).toBe(false)
  })

  it('sends a beat that takes the overlay off', async () => {
    const w = mount(ScenarioBuilder)
    await settled(w)

    await w.find('textarea.sb-text').setValue('Hallo.')
    await w.find('select.sb-overlay').setValue('hide')
    await w.find('button.sb-btn--go').trigger('click')

    expect((w.emitted('start')![0][0] as any).beats[0].overlay).toBe('hide')
  })

  it('offers the control on a silent beat, which is the likeliest one to want it', async () => {
    const w = mount(ScenarioBuilder)
    await settled(w)

    // A beat whose whole purpose is to clear the screen for a live demo says
    // nothing and does nothing else — so it must not lose the control that
    // the speaking beats get.
    await w.find('select.sb-mode').setValue('silent')
    await w.vm.$nextTick()
    expect(w.find('select.sb-overlay').exists()).toBe(true)
  })

  it('can start the whole talk with the overlay off', async () => {
    const w = mount(ScenarioBuilder)
    await settled(w)

    await w.find('textarea.sb-text').setValue('Hallo.')
    await w.find('select.sb-scenario-overlay').setValue('hidden')
    await w.find('button.sb-btn--go').trigger('click')

    expect((w.emitted('start')![0][0] as any).overlay).toBe('hidden')
  })

  it('hydrates both when an existing scenario is loaded', async () => {
    const w = mount(ScenarioBuilder)
    await settled(w)

    ;(w.vm as any).loadScenario({
      title: 'T', overlay: 'hidden',
      beats: [{ id: 'a', trigger: 'manual', mode: 'silent', overlay: 'hide' }],
    })
    await w.vm.$nextTick()

    expect((w.find('select.sb-scenario-overlay').element as HTMLSelectElement).value)
      .toBe('hidden')
    expect((w.find('select.sb-overlay').element as HTMLSelectElement).value).toBe('hide')
  })
})
