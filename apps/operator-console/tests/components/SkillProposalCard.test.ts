import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import BrainPanel from '../../src/components/BrainPanel.vue'

/** U251: proposals the assistant raised BY ITSELF, waiting for an answer.
 *
 *  U250 made it raise them; they went out on the event bus and vanished. The
 *  tick runs every five minutes all day and the owner opens the app in the
 *  evening, so a card that only exists while the console is open is a loop
 *  nobody ever sees.
 *
 *  The case that matters most here is a NEW skill: applying a rewrite could
 *  reuse the existing skill's record, but a new one has nothing to merge with,
 *  and getting that wrong means the button does nothing.
 */

const NEW_PROPOSAL = {
  id: 'p1',
  kind: 'new' as const,
  skill: 'sport-uitslagen',
  reason: 'asked about "hockey" 3 times with no skill covering it',
  rationale: 'keeps coming up',
  description: 'Zoek een sportuitslag op',
  triggers: ['hockey', 'uitslag'],
  current_body: '',
  proposed_body: '1. open_browser_url met de zoek-URL',
}

const REWRITE_PROPOSAL = {
  id: 'p2',
  kind: 'rewrite' as const,
  skill: 'chrome',
  reason: 'stopped 2 of the last 2 times because browser was not available',
  rationale: 'use the URL tool',
  current_body: '1. use_computer',
  proposed_body: '1. open_browser_url',
}

const EXISTING_CHROME = {
  name: 'chrome', description: 'browse', triggers: ['chrome'],
  personas: [], person: '', enabled: true, body: '1. use_computer',
}

type Call = { url: string; init?: RequestInit }

function stubFetch(proposals: unknown[], skills: unknown[] = []) {
  const calls: Call[] = []
  const ok = (body: unknown) => Promise.resolve({
    ok: true, status: 200, json: () => Promise.resolve(body),
  } as Response)
  vi.stubGlobal('fetch', (url: string, init?: RequestInit) => {
    calls.push({ url, init })
    if (url.includes('/skills/proposals')) return ok({ proposals })
    if (url.includes('/skills/suggestions')) return ok({ suggestions: [] })
    if (url.includes('/metrics')) return ok({ uses: 0, new_since_optimized: 0, last_used: null })
    if (url.endsWith('/skills')) return ok({ skills })
    return ok({})
  })
  return calls
}

async function mountWithSkills(proposals: unknown[], skills: unknown[] = []) {
  const calls = stubFetch(proposals, skills)
  const w = mount(BrainPanel, { global: { stubs: { WikiText: true } } })
  await flushPromises()
  await flushPromises()
  return { w, calls }
}

beforeEach(() => {
  vi.unstubAllGlobals()
  setActivePinia(createPinia())
})

describe('raised skill proposals', () => {
  it('shows nothing when the assistant has no question', async () => {
    const { w } = await mountWithSkills([])
    expect(w.html()).not.toContain('skill-opt--raised')
  })

  it('shows what it wants and why', async () => {
    const { w } = await mountWithSkills([NEW_PROPOSAL])
    const card = w.find('.skill-opt--raised')
    expect(card.exists()).toBe(true)
    expect(card.text()).toContain('sport-uitslagen')
    expect(card.text()).toContain('3 times with no skill covering it')
    expect(card.text()).toContain('open_browser_url')
    expect(card.text()).toContain('hockey')
  })

  it('offers a new skill as an addition, not as a rewrite', async () => {
    const { w } = await mountWithSkills([NEW_PROPOSAL])
    expect(w.find('.skill-opt--raised').text()).toContain('Add this skill')
    // A new skill has nothing to compare against, so no before/after column.
    expect(w.find('.skill-opt--raised').text()).not.toContain('Current')
  })

  it('creates the skill from the draft when accepted', async () => {
    const { w, calls } = await mountWithSkills([NEW_PROPOSAL])
    await w.find('.skill-opt--raised .b-btn').trigger('click')
    await flushPromises()

    const save = calls.find(c => c.init?.method === 'POST' && c.url.endsWith('/skills'))
    expect(save, 'the skill must actually be saved').toBeTruthy()
    const body = JSON.parse(String(save!.init!.body))
    expect(body.name).toBe('sport-uitslagen')
    expect(body.triggers).toEqual(['hockey', 'uitslag'])
    expect(body.body).toBe('1. open_browser_url met de zoek-URL')
  })

  it('keeps a rewritten skill’s triggers and only changes the procedure', async () => {
    const { w, calls } = await mountWithSkills([REWRITE_PROPOSAL], [EXISTING_CHROME])
    await w.find('.skill-opt--raised .b-btn').trigger('click')
    await flushPromises()

    const save = calls.find(c => c.init?.method === 'POST' && c.url.endsWith('/skills'))
    const body = JSON.parse(String(save!.init!.body))
    expect(body.triggers).toEqual(['chrome'])
    expect(body.body).toBe('1. open_browser_url')
    expect(body.mark_optimized).toBe(true)
  })

  it('tells the brain the question is answered, so it stops asking', async () => {
    const { w, calls } = await mountWithSkills([NEW_PROPOSAL])
    await w.find('.skill-opt--raised .b-btn').trigger('click')
    await flushPromises()
    expect(calls.some(c => c.init?.method === 'DELETE' && c.url.includes('/skills/proposals/p1')))
      .toBe(true)
  })

  it('lets the owner refuse, and does not save anything', async () => {
    const { w, calls } = await mountWithSkills([NEW_PROPOSAL])
    const buttons = w.findAll('.skill-opt--raised .b-btn')
    await buttons[buttons.length - 1].trigger('click')   // "No thanks"
    await flushPromises()

    expect(calls.some(c => c.init?.method === 'POST' && c.url.endsWith('/skills'))).toBe(false)
    expect(calls.some(c => c.init?.method === 'DELETE')).toBe(true)
    expect(w.find('.skill-opt--raised').exists()).toBe(false)
  })

  it('lets the owner edit it first — a draft is a starting point', async () => {
    const { w, calls } = await mountWithSkills([NEW_PROPOSAL])
    const buttons = w.findAll('.skill-opt--raised .b-btn')
    await buttons[1].trigger('click')                    // "Edit first"
    await flushPromises()

    expect(calls.some(c => c.init?.method === 'POST' && c.url.endsWith('/skills'))).toBe(false)
    const editor = w.find('.skill-editor-inline')
    expect(editor.exists()).toBe(true)
    // v-model values live on the elements, not in the markup.
    const name = editor.find<HTMLInputElement>('input[aria-label="Skill name"]')
    const body = editor.find<HTMLTextAreaElement>('textarea[aria-label="Skill procedure"]')
    expect(name.element.value).toBe('sport-uitslagen')
    expect(body.element.value).toBe('1. open_browser_url met de zoek-URL')
  })
})
