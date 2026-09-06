import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import PickerMenu, { type PickerItem } from '../../src/components/shell/PickerMenu.vue'
import AppHeader from '../../src/components/shell/AppHeader.vue'
import { useKnowledgeStore } from '../../src/stores/knowledgeStore'
import { useCharacterStore } from '../../src/stores/characterStore'
import { CHARACTERS } from '../../src/lib/characters'

/** U319: "tapping will cycle, but via arrow we should be able to choose
 *  directly".
 *
 *  The identity chip drew a chevron and behaved like a step button — the worst
 *  of both, because the affordance promises a list and the click gives you the
 *  next one. With ten characters and a household of five, reaching the last
 *  option meant pressing nine times without ever seeing what the options were.
 *
 *  This app has no vue-tsc, so a wrong prop or a renamed store method is a
 *  runtime error in front of the owner. These tests mount the real components.
 */

const ITEMS: PickerItem[] = [
  { id: 'a', label: 'Ada', sub: 'owner', initials: 'AD', active: true },
  { id: 'b', label: 'Bo', sub: 'family', initials: 'BO' },
]

describe('PickerMenu', () => {
  it('renders nothing until it is opened', () => {
    const w = mount(PickerMenu, { props: { open: false, items: ITEMS } })
    expect(w.find('.picker').exists()).toBe(false)
  })

  it('lists every option at once — that is the whole point', () => {
    const w = mount(PickerMenu, { props: { open: true, items: ITEMS } })
    expect(w.findAll('.picker-row')).toHaveLength(2)
    expect(w.text()).toContain('Ada')
    expect(w.text()).toContain('Bo')
  })

  it('marks the current one instead of making you count', () => {
    const w = mount(PickerMenu, { props: { open: true, items: ITEMS } })
    expect(w.findAll('.picker-row')[0].classes()).toContain('active')
    expect(w.findAll('.picker-row')[1].classes()).not.toContain('active')
  })

  it('emits the id that was chosen', async () => {
    const w = mount(PickerMenu, { props: { open: true, items: ITEMS } })
    await w.findAll('.picker-row')[1].trigger('click')
    expect(w.emitted('pick')?.[0]).toEqual(['b'])
  })

  it('does not claim the list is empty while showing a list', () => {
    // It did: "Nobody is in the brain yet." printed directly under a person's
    // name, which is the console asserting something it could see was false.
    const w = mount(PickerMenu, {
      props: { open: true, items: ITEMS, empty: 'Nobody yet.' },
    })
    expect(w.text()).not.toContain('Nobody yet.')
  })

  it('says so when there is nothing to choose from', () => {
    const w = mount(PickerMenu, {
      props: { open: true, items: [], empty: 'Nobody yet.' },
    })
    // An empty menu explains nothing; this state has an obvious next step.
    expect(w.text()).toContain('Nobody yet.')
  })

  it('offers the way out when the list is not enough', async () => {
    const w = mount(PickerMenu, {
      props: { open: true, items: ITEMS, footer: 'Add a person →' },
    })
    await w.find('.picker-footer').trigger('click')
    expect(w.emitted('footer')).toBeTruthy()
  })

  it('closes on Escape', async () => {
    const w = mount(PickerMenu, {
      props: { open: true, items: ITEMS }, attachTo: document.body,
    })
    await flushPromises()
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(w.emitted('close')).toBeTruthy()
    w.unmount()
  })

  it('closes on a click outside, and not on one inside', async () => {
    const w = mount(PickerMenu, {
      props: { open: true, items: ITEMS }, attachTo: document.body,
    })
    await flushPromises()

    w.find('.picker-row').element.dispatchEvent(
      new MouseEvent('click', { bubbles: true }))
    expect(w.emitted('close')).toBeFalsy()

    document.body.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(w.emitted('close')).toBeTruthy()
    w.unmount()
  })
})

describe('U319 — the identity chevron opens the list', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.stubGlobal('fetch', () => Promise.resolve({
      ok: true, status: 200, json: () => Promise.resolve({}),
    } as Response))
  })

  function header() {
    const knowledge = useKnowledgeStore()
    knowledge.people = [
      { person_id: 'ada', display_name: 'Ada', role: 'owner' },
      { person_id: 'bo', display_name: 'Bo', role: 'family' },
    ] as never
    return mount(AppHeader, { props: { wsStatus: 'open' } })
  }

  it('has a chevron that is a button, not decoration', () => {
    const w = header()
    const more = w.find('.who-more')
    expect(more.exists()).toBe(true)
    expect(more.attributes('aria-haspopup')).toBe('menu')
  })

  it('lists everyone plus Guest when the chevron is pressed', async () => {
    const w = header()
    expect(w.find('.picker').exists()).toBe(false)
    await w.find('.who-more').trigger('click')
    const labels = w.findAll('.picker-label').map(n => n.text())
    expect(labels).toEqual(['Ada', 'Bo', 'Guest'])
  })

  it('picking one sets the speaker directly — no counting', async () => {
    const w = header()
    const knowledge = useKnowledgeStore()
    await w.find('.who-more').trigger('click')
    await w.findAll('.picker-row')[1].trigger('click')
    expect(knowledge.speaker).toBe('bo')
  })

  it('the chip body still steps to the next person', async () => {
    const w = header()
    const knowledge = useKnowledgeStore()
    await w.find('.who-chip').trigger('click')
    expect(knowledge.speaker).toBe('ada')
    await w.find('.who-chip').trigger('click')
    expect(knowledge.speaker).toBe('bo')
  })
})

describe('U319 — the robot on the Talk screen is the character picker', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('every shipped character is offered', () => {
    const store = useCharacterStore()
    const items = Object.entries(CHARACTERS).map(([id, c]) => ({
      id, label: c.tag, active: id === store.selected,
    }))
    expect(items.length).toBeGreaterThanOrEqual(10)
    expect(items.filter(i => i.active)).toHaveLength(1)
  })

  it('choosing one selects it', () => {
    const store = useCharacterStore()
    const other = Object.keys(CHARACTERS).find(id => id !== store.selected)!
    store.select(other)
    expect(store.selected).toBe(other)
  })
})
