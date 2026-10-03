import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import ModesView from '../../src/views/ModesView.vue'
import AppHeader from '../../src/components/shell/AppHeader.vue'

/** U397: a Stand for a fair, and wandering as a behaviour of each mode.
 *
 *  Asked as (translated): "if I'm at a fair and want him in wander mode, how do
 *  I best do that? I'd think in work mode and activate it there? Doing it via
 *  Settings seems so strange" — and, of the new mode, "I assume a lot of
 *  capabilities are switched off / greyed out there".
 *
 *  No vue-tsc here: a wrong key or a renamed field is a runtime error in front
 *  of the owner, so these mount the real view against a policy shaped like the
 *  brain's.
 */

const OK = (body: unknown) => Promise.resolve({
  ok: true, status: 200, json: () => Promise.resolve(body),
} as Response)

function group(id: string, state: string) {
  return { id, label: id[0].toUpperCase() + id.slice(1), detail: '', state, source: 'default', tools: [] }
}

function mode(wander: string, wander_sound: string, blocked: boolean) {
  const s = blocked ? 'blocked' : 'allows'
  return {
    groups: [group('conversation', 'allows'), group('web', 'allows'), group('calendar', s), group('mail', s)],
    behaviour: { persona: 'work', voice: 'alloy', speaks_first: 'yes', memory_writing: 'on',
                 wander, wander_sound },
  }
}

const POLICY = {
  active_mode: 'work', states: ['allows', 'asks', 'blocked'], quiet: false, live_domains: null,
  modes: {
    home: mode('off', 'silent', false),
    work: mode('off', 'silent', false),
    stand: mode('on', 'talk', true),
    presentation: mode('off', 'silent', true),
  },
}

function brain() {
  const bodies: string[] = []
  vi.stubGlobal('fetch', (url: string, init?: RequestInit) => {
    if (init?.body) bodies.push(String(init.body))
    const u = String(url)
    if (u.includes('/orchestrator/policy/behaviour')) {
      return OK({ mode: 'stand', behaviour: POLICY.modes.stand.behaviour })
    }
    if (u.includes('/orchestrator/policy')) return OK(POLICY)
    if (u.includes('/robot/wander')) return OK({ note: '' })
    return OK({})
  })
  return bodies
}

async function openTab(w: ReturnType<typeof mount>, label: string) {
  const tab = w.findAll('.mode-tab').find(t => t.text().startsWith(label))
  expect(tab, `no ${label} tab`).toBeTruthy()
  await tab!.trigger('click')
  await flushPromises()
}

describe('U397 — Stand, and wandering per mode', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('puts Stand between Work and Present in the header', () => {
    brain()
    const w = mount(AppHeader, { props: { wsStatus: 'open' } })
    const labels = w.findAll('.mode-btn').map(b => b.attributes('aria-label'))
    expect(labels).toEqual(['Home', 'Work', 'Stand', 'Present'])
  })

  it('edits Stand like any other mode', async () => {
    brain()
    const w = mount(ModesView)
    await flushPromises()
    expect(w.findAll('.mode-tab').map(t => t.text().split(' ·')[0]))
      .toEqual(['Home', 'Work', 'Stand', 'Present'])
  })

  it('greys out what a mode blocks', async () => {
    brain()
    const w = mount(ModesView)
    await flushPromises()
    await openTab(w, 'Stand')
    const rows = w.findAll('.policy-row')
    const mail = rows.find(r => r.text().includes('Mail'))!
    const web = rows.find(r => r.text().includes('Web'))!
    expect(mail.classes()).toContain('blocked')
    expect(web.classes()).not.toContain('blocked')
  })

  it('shows that he wanders and talks at a Stand, and saves a change', async () => {
    const bodies = brain()
    const w = mount(ModesView)
    await flushPromises()
    await openTab(w, 'Stand')
    const wander = w.find('[data-test="mode-wander"]')
    const sound = w.find('[data-test="mode-wander-sound"]')
    expect((wander.element as HTMLSelectElement).value).toBe('on')
    expect((sound.element as HTMLSelectElement).value).toBe('talk')
    expect(sound.findAll('option').map(o => o.element.value)).toEqual(['silent', 'emotions', 'talk'])

    await sound.setValue('emotions')
    await flushPromises()
    const sent = bodies.map(b => JSON.parse(b)).find(b => b.behaviour?.wander_sound)
    expect(sent).toEqual({ mode: 'stand', behaviour: { wander_sound: 'emotions' } })
  })

  it('lets Work wander too, if you want it to', async () => {
    const bodies = brain()
    const w = mount(ModesView)
    await flushPromises()
    await openTab(w, 'Work')
    await w.find('[data-test="mode-wander"]').setValue('on')
    await flushPromises()
    expect(bodies.map(b => JSON.parse(b)))
      .toContainEqual({ mode: 'work', behaviour: { wander: 'on' } })
  })

  it('says the scenario decides in Present, instead of offering a switch it ignores', async () => {
    brain()
    const w = mount(ModesView)
    await flushPromises()
    await openTab(w, 'Present')
    expect(w.find('[data-test="mode-wander"]').exists()).toBe(false)
    expect(w.find('[data-test="mode-wander-present"]').text()).toMatch(/scenario/i)
  })
})
