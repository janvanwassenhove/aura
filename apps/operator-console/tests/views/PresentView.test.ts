import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import PresentView from '../../src/views/PresentView.vue'

/** U266: two ways Present mode did nothing and said nothing about it.
 *
 *  1. "Start presentation is not doing anything." The builder writes a beat's
 *     cue as a STRING — "manual", "slide:4", "keyword:Java" — and the brain
 *     parses it as one. This view read it as an OBJECT, and
 *     `'keyword' in 'manual'` is not a false test but a TypeError. It threw
 *     while mapping the first beat, BEFORE the scenario was ever POSTed, so
 *     the green button produced no request, no error, and no change on screen.
 *
 *  2. "Ik kan overlay ook niet terug desactiveren." The Hide button rendered
 *     only while this view believed the overlay was up — a belief that resets
 *     every time the view is re-created, while the Electron overlay window
 *     happily stays on the beamer.
 *
 *  There is no vue-tsc step here (esbuild strips types unchecked), so the
 *  wrong annotation in (1) compiled cleanly and only failed at runtime, in a
 *  click handler, in front of a deck. Mounting is the only thing that sees it.
 */

const OK = (body: unknown) => Promise.resolve({
  ok: true, status: 200, json: () => Promise.resolve(body),
} as Response)

function stubFetch(
  opts: { status?: unknown; active?: unknown; loaded?: unknown } = {},
): { url: string; body: unknown }[] {
  const posts: { url: string; body: unknown }[] = []
  vi.stubGlobal('fetch', (url: string, init?: RequestInit) => {
    const u = String(url)
    if (init?.method === 'POST') {
      posts.push({ url: u, body: JSON.parse(String(init.body ?? '{}')) })
    }
    if (u.includes('/presentation/scenarios')) return OK({ scenarios: [] })
    if (u.includes('/presentation/scenario')) {
      // GET returns the loaded scenario (U267 Edit); POST loads a new one.
      if (init?.method !== 'POST') return OK({ scenario: opts.active ?? null })
      return OK(opts.loaded
        ?? { active: true, title: 'test', manual_pos: 0, manual_total: 1, beats_total: 1 })
    }
    if (u.includes('/presentation/status')) return OK(opts.status ?? { active: false })
    if (u.includes('/personas')) return OK({ personas: [] })
    return OK({})
  })
  return posts
}

beforeEach(() => {
  vi.unstubAllGlobals()
  setActivePinia(createPinia())
})

describe('U266 — Present mode does what its buttons say', () => {
  it('a manual beat starts the presentation instead of throwing', async () => {
    const posts = stubFetch()
    const w = mount(PresentView)
    await flushPromises()

    // Open the builder ("New scenario") and fill the one beat it starts with.
    const openers = w.findAll('button').filter(b => b.text().includes('New scenario'))
    expect(openers.length).toBe(1)
    await openers[0].trigger('click')
    await flushPromises()

    const text = w.find('textarea.sb-text')
    expect(text.exists()).toBe(true)
    await text.setValue('tell a joke')

    const start = w.findAll('button').filter(b => b.text() === 'Start presentation')
    expect(start.length).toBe(1)
    await start[0].trigger('click')
    await flushPromises()

    // The whole bug: before the fix this list was empty — the handler died on
    // `'keyword' in 'manual'` and the brain never heard a thing.
    const load = posts.filter(p => p.url.includes('/presentation/scenario'))
    expect(load.length).toBe(1)
    const sent = (load[0].body as { scenario: { beats: { trigger: string; text: string }[] } }).scenario
    expect(sent.beats[0].trigger).toBe('manual')
    expect(sent.beats[0].text).toBe('tell a joke')
  })

  it('slide and keyword cues survive the same mapping', async () => {
    const posts = stubFetch()
    const w = mount(PresentView)
    await flushPromises()
    await w.findAll('button').filter(b => b.text().includes('New scenario'))[0].trigger('click')
    await flushPromises()

    // Switch the beat's cue to a slide number — the other shape of the string.
    const kind = w.find('select.sb-tkind')
    await kind.setValue('slide')
    await w.find('input.sb-tnum').setValue(4)
    await w.find('textarea.sb-text').setValue('here we go')
    await w.findAll('button').filter(b => b.text() === 'Start presentation')[0].trigger('click')
    await flushPromises()

    const load = posts.filter(p => p.url.includes('/presentation/scenario'))
    expect(load.length).toBe(1)
    const sent = (load[0].body as { scenario: { beats: { trigger: string }[] } }).scenario
    expect(sent.beats[0].trigger).toBe('slide:4')
  })

  it('a hand-advanced beat is not badged as one that fires by itself', async () => {
    stubFetch()
    const w = mount(PresentView)
    await flushPromises()
    await w.findAll('button').filter(b => b.text().includes('New scenario'))[0].trigger('click')
    await flushPromises()
    await w.find('textarea.sb-text').setValue('tell a joke')
    await w.findAll('button').filter(b => b.text() === 'Start presentation')[0].trigger('click')
    await flushPromises()

    // U267: every non-keyword beat used to be labelled SLIDE, so a beat that
    // waits for the presenter promised it would fire on its own — which is
    // exactly why "should be triggered automatically" was asked about a beat
    // whose cue was "I press Next".
    const beats = w.findAll('.beat-kind')
    expect(beats.length).toBe(1)
    expect(beats[0].text()).toBe('manual')
    expect(w.find('.beat-cue').text()).toBe('You press Advance beat')
  })

  it('a slide beat says which slide it waits for', async () => {
    stubFetch()
    const w = mount(PresentView)
    await flushPromises()
    await w.findAll('button').filter(b => b.text().includes('New scenario'))[0].trigger('click')
    await flushPromises()
    await w.find('select.sb-tkind').setValue('slide')
    await w.find('input.sb-tnum').setValue(12)
    await w.find('textarea.sb-text').setValue('here we go')
    await w.findAll('button').filter(b => b.text() === 'Start presentation')[0].trigger('click')
    await flushPromises()

    expect(w.find('.beat-kind').text()).toBe('slide')
    expect(w.find('.beat-cue').text()).toBe('Slide 12')
  })

  it('the counter never walks past the end of the show', async () => {
    // The reported "beat 2 of 1": one manual beat, fired. The position came
    // from manual_pos and the total from manual_total — both describing only
    // the hand-advanced beats — so firing the only one put it past the end.
    stubFetch({
      loaded: {
        active: true, title: 'test', manual_pos: 1, manual_total: 1,
        beats_total: 1, fired: ['beat-1'],
      },
    })
    const w = mount(PresentView)
    await flushPromises()
    await w.findAll('button').filter(b => b.text().includes('New scenario'))[0].trigger('click')
    await flushPromises()
    await w.find('textarea.sb-text').setValue('tell a joke')
    await w.findAll('button').filter(b => b.text() === 'Start presentation')[0].trigger('click')
    await flushPromises()

    const hud = w.find('.hud-counter').text()
    expect(hud).not.toMatch(/beat 2 of 1/)
    expect(hud).toContain('all 1 beats done')
  })

  it('Edit opens the builder on the scenario that is loaded', async () => {
    // U267: "New scenario" opened an EMPTY builder and was the only door in,
    // so changing one line meant retyping the talk. Asked as "how to edit
    // presentation".
    stubFetch({
      status: { active: true, title: 'my talk', beats_total: 1, fired: [] },
      active: {
        title: 'my talk', pptx: 'deck.pptx',
        beats: [{ id: 'beat-1', trigger: 'slide:7', mode: 'speak', text: 'the line' }],
      },
    })
    const w = mount(PresentView)
    await flushPromises()

    const edit = w.findAll('button').filter(b => b.text() === 'Edit')
    expect(edit.length).toBe(1)
    await edit[0].trigger('click')
    await flushPromises()

    // The builder came up filled in, not blank.
    expect((w.find('input.sb-input').element as HTMLInputElement).value).toBe('my talk')
    expect((w.find('textarea.sb-text').element as HTMLTextAreaElement).value).toBe('the line')
    expect((w.find('select.sb-tkind').element as HTMLSelectElement).value).toBe('slide')
  })

  it('Hide is always reachable, even when this view thinks the overlay is off', async () => {
    stubFetch()
    const w = mount(PresentView)
    await flushPromises()

    // Freshly mounted: nothing has been shown from THIS view. The overlay may
    // still be on the beamer from a previous one, so the way out must be here.
    //
    // U320 renamed the button from "Hide" to "Take it down" — the assertion is
    // on the WAY OUT existing, not on the word, so it survives the next rename
    // and still fails if the button goes back to being conditional.
    expect(w.find('.ov-hide').exists()).toBe(true)
    // And the panel does not pretend to know whether the overlay is up: this
    // window cannot see the other one.
    expect(w.find('.ov-honest').text()).toContain('cannot see')
  })
})

describe('U320 — the Present panel reads like one thing, not a list of six', () => {
  it('groups the aside instead of flattening settings, status and actions', async () => {
    stubFetch()
    const w = mount(PresentView)
    await flushPromises()
    expect(w.findAll('.aside-group-title').map(n => n.text())).toEqual([
      'How he sounds', 'What he is following', 'On the projector',
    ])
  })

  it('says it once: no run bar above an empty state', async () => {
    stubFetch()
    const w = mount(PresentView)
    await flushPromises()
    // It read "No scenario loaded" directly above "No scenario yet", with two
    // identical primary buttons. One invitation is enough.
    expect(w.find('.run-bar').exists()).toBe(false)
    expect(w.find('.present-empty').exists()).toBe(true)
  })

  it('names the run button after what it will actually do', async () => {
    stubFetch()
    const w = mount(PresentView, { data: () => ({}) })
    await flushPromises()
    await w.find('.present-empty .d2-primary-btn').trigger('click')
    // The builder is open, so the run bar is back — and with no beats yet,
    // pressing Run opens the builder, which is what the label must say.
    expect(w.find('.run-btn').text()).toBe('Write a scenario')
  })

  it('offers the two ways in where the page is empty, not only in the corner', async () => {
    stubFetch()
    const w = mount(PresentView)
    await flushPromises()
    const empty = w.find('.present-empty')
    expect(empty.exists()).toBe(true)
    expect(empty.text()).toContain('Write a scenario')
    expect(empty.text()).toContain('Import YAML')
  })

  it('lets a presenter who knows the steps put them away', async () => {
    stubFetch()
    const w = mount(PresentView)
    await flushPromises()
    expect(w.find('.how-steps').exists()).toBe(true)
    await w.find('.how-toggle').trigger('click')
    expect(w.find('.how-steps').exists()).toBe(false)
    // Remembered, so it is not taught again before every talk.
    expect(localStorage.getItem('aura-present-how')).toBe('closed')
  })

  it('shows the audience/presenter choice as two visible options', async () => {
    stubFetch()
    const w = mount(PresentView)
    await flushPromises()
    // A <select> hides one of them behind a click, and the wrong one on a
    // beamer means projecting your private cue notes at the audience.
    const seg = w.findAll('.seg-btn').map(b => b.text())
    expect(seg).toEqual(['The room', 'Me'])
    expect(w.findAll('.seg-btn.on')).toHaveLength(1)
  })
})

/** U362: reported as "when i import a yaml, second time i import it does not
 *  seem to load? (first time after startup app it worked)".
 *
 *  A file input only fires `change` when its VALUE changes. Pick the same file
 *  twice and the second pick is not a change, so nothing fires and nothing
 *  happens — no request, no error, no scenario. SettingsView already clears
 *  the input after reading it; Present never did.
 */
describe('U362 — importing the same YAML twice', () => {
  function fakeFile(text: string) {
    return { name: 'talk.yaml', text: async () => text } as unknown as File
  }

  /** jsdom reports a file input's value as '' and refuses to be set, so
   *  asserting `el.value === ''` passes with or without the fix — it did, the
   *  first time these were written. Watch the WRITE instead. */
  function watchClear(el: HTMLInputElement, file: File): string[] {
    const writes: string[] = []
    Object.defineProperty(el, 'files', { value: [file], configurable: true })
    Object.defineProperty(el, 'value', {
      get: () => '', set: (v: string) => { writes.push(v) }, configurable: true,
    })
    return writes
  }

  async function importInto(w: ReturnType<typeof mount>, el: HTMLInputElement) {
    await (w.vm as unknown as { importYaml: (e: Event) => Promise<void> })
      .importYaml({ target: el } as unknown as Event)
    await flushPromises()
  }

  it('clears the file input, so the same file can be picked again', async () => {
    stubFetch()
    const w = mount(PresentView)
    await flushPromises()

    const input = w.find('input[type="file"]')
    expect(input.exists()).toBe(true)
    const el = input.element as HTMLInputElement
    const writes = watchClear(el, fakeFile('title: T\nbeats: []\n'))

    await importInto(w, el)

    expect(writes).toContain('')
  })

  it('posts the scenario it was given', async () => {
    const posts = stubFetch()
    const w = mount(PresentView)
    await flushPromises()

    const el = w.find('input[type="file"]').element as HTMLInputElement
    watchClear(el, fakeFile('title: Second\nbeats: []\n'))

    await importInto(w, el)

    const loaded = posts.filter(p => p.url.includes('/presentation/scenario'))
    expect(loaded.length).toBe(1)
    expect(JSON.stringify(loaded[0].body)).toContain('Second')
  })

  it('still clears the input when the import fails', async () => {
    // Otherwise a rejected file could never be re-picked after fixing it —
    // which is the one time you WILL pick the same name twice.
    stubFetch({ loaded: null })
    const w = mount(PresentView)
    await flushPromises()

    const el = w.find('input[type="file"]').element as HTMLInputElement
    const writes = watchClear(el, fakeFile('nonsense: ['))

    await importInto(w, el)

    expect(writes).toContain('')
  })
})

describe('U388 — the HUD describes the show that is running', () => {
  /** Reported with a screenshot: on slide 8, where the gag plays, the HUD said
   *  "Saying now —" and "Next cue: the end — he bows and hands back to you".
   *  Its beat list was filled only when Start was pressed in this window; the
   *  owner loaded the talk from the saved list, so it was empty, and both
   *  lines fell back to their defaults. */
  const DEVOXX = {
    title: 'I Hired a Real Robot as My Junior Dev',
    beats: [
      { id: 'sound-check', trigger: 'slide:1', mode: 'silent' },
      { id: 'screen-1-clear', trigger: 'slide:7', mode: 'silent', overlay: 'hide' },
      { id: 'screen-1-back', trigger: 'slide:8', mode: 'silent', overlay: 'show' },
      { id: 'screen-2-clear', trigger: 'slide:55', mode: 'silent', overlay: 'hide' },
      { id: 'the-gag', trigger: 'slide:8', mode: 'speak', text: 'Oh, I know this one.' },
      { id: 'the-disclaimer', trigger: 'slide:8', mode: 'speak', text: 'I am not allowed to do the next bit.' },
      { id: 'chime-java', trigger: 'keyword:Java', mode: 'chime_in', topic: 'kids' },
      { id: 'chapter-1', trigger: 'slide:27', mode: 'silent' },
      { id: 'last-word', trigger: 'slide:98', mode: 'speak', text: 'I will type the rest.' },
    ],
  }
  const ON_SLIDE_8 = {
    active: true, title: DEVOXX.title, current_slide: 8, slide: 8, slides_state: 'live',
    beats_total: DEVOXX.beats.length, armed_keywords: ['Java'],
    fired: ['screen-1-back', 'screen-1-clear', 'the-disclaimer', 'the-gag'],
    last_fired: 'the-disclaimer',
  }

  it('loads the running show from the brain, without Start being pressed here', async () => {
    stubFetch({ status: ON_SLIDE_8, active: DEVOXX })
    const w = mount(PresentView)
    await flushPromises(); await flushPromises()

    const hud = w.text()
    expect(hud).not.toContain('the end — he bows')
    expect(hud).toContain('I am not allowed to do the next bit.')
  })

  it('names the next slide that does something, from the slide you are on', async () => {
    // File order puts the overlay pairs and slide 55 BEFORE chapter-1 on
    // slide 27, and sound-check on slide 1 never ran. Neither may decide.
    stubFetch({ status: ON_SLIDE_8, active: DEVOXX })
    const w = mount(PresentView)
    await flushPromises(); await flushPromises()

    expect(w.text()).toContain('Slide 27')
    expect(w.text()).toContain('chapter-1')
  })

  it('says the end only when nothing is left ahead', async () => {
    stubFetch({ status: { ...ON_SLIDE_8, current_slide: 98, slide: 98, last_fired: 'last-word' },
                active: DEVOXX })
    const w = mount(PresentView)
    await flushPromises(); await flushPromises()

    expect(w.text()).toContain('the end — he bows')
  })
})

describe('U389 — ending a talk keeps it', () => {
  /** Reported as "when we click end presentation, we loose the scneario again,
   *  we should be able to keep it (reload it, remove it) afterwards". End sent
   *  DELETE, so the brain forgot the talk; "run again" then rebuilt it from the
   *  HUD rows, which turns every slide and keyword cue into a hand press. */
  const TALK = {
    title: 'I Hired a Real Robot as My Junior Dev',
    beats: [
      { id: 'the-gag', trigger: 'slide:8', mode: 'speak', text: 'Oh, I know this one.' },
      { id: 'chime-java', trigger: 'keyword:Java', mode: 'chime_in', topic: 'kids' },
    ],
  }

  function brain(state: { status: unknown; scenario: unknown }) {
    const calls: { method: string; url: string; body: unknown }[] = []
    vi.stubGlobal('fetch', (url: string, init?: RequestInit) => {
      const u = String(url)
      const method = init?.method ?? 'GET'
      calls.push({ method, url: u, body: init?.body ? JSON.parse(String(init.body)) : null })
      if (u.includes('/presentation/end')) {
        state.status = { active: false, kept: { title: TALK.title, beats_total: 2 } }
        return OK(state.status)
      }
      if (u.includes('/presentation/scenarios')) return OK({ scenarios: [] })
      if (u.includes('/presentation/scenario')) {
        if (method === 'DELETE') {
          state.status = { active: false }; state.scenario = null
          return OK({ active: false })
        }
        if (method === 'POST') {
          state.status = { active: true, title: TALK.title, beats_total: 2, fired: [] }
          return OK(state.status)
        }
        return state.scenario
          ? OK({ scenario: state.scenario, running: false })
          : Promise.resolve({ ok: false, status: 409, json: () => Promise.resolve({}) } as Response)
      }
      if (u.includes('/presentation/status')) return OK(state.status)
      if (u.includes('/personas')) return OK({ personas: [] })
      return OK({})
    })
    return calls
  }
  const KEPT = { active: false, kept: { title: TALK.title, beats_total: 2 } }

  it('End stops the show without throwing the talk away', async () => {
    const calls = brain({ status: { active: true, title: TALK.title, beats_total: 2, fired: [] },
                          scenario: TALK })
    const w = mount(PresentView)
    await flushPromises(); await flushPromises()

    await w.find('.run-btn').trigger('click')
    await flushPromises(); await flushPromises()

    expect(calls.some(c => c.method === 'POST' && c.url.includes('/presentation/end'))).toBe(true)
    expect(calls.some(c => c.method === 'DELETE')).toBe(false)
    expect(w.text()).toContain(TALK.title)
    expect(w.text()).not.toContain('No scenario yet')
  })

  it('a kept talk offers Run again and Remove, in any window', async () => {
    brain({ status: KEPT, scenario: TALK })
    const w = mount(PresentView)
    await flushPromises(); await flushPromises()

    expect(w.text()).toContain(TALK.title)
    expect(w.find('.run-btn').text()).toBe('Run again')
    expect(w.find('[data-test="remove-scenario"]').exists()).toBe(true)
  })

  it('Run again runs the same talk, cues and all', async () => {
    const calls = brain({ status: KEPT, scenario: TALK })
    const w = mount(PresentView)
    await flushPromises(); await flushPromises()

    await w.find('.run-btn').trigger('click')
    await flushPromises(); await flushPromises()

    const post = calls.find(c => c.method === 'POST' && c.url.endsWith('/presentation/scenario'))
    const beats = (post?.body as { scenario: { beats: { trigger: string }[] } }).scenario.beats
    expect(beats.map(b => b.trigger)).toEqual(['slide:8', 'keyword:Java'])
  })

  it('Remove forgets it, and the page says there is nothing loaded', async () => {
    const calls = brain({ status: KEPT, scenario: TALK })
    const w = mount(PresentView)
    await flushPromises(); await flushPromises()

    await w.find('[data-test="remove-scenario"]').trigger('click')
    await flushPromises(); await flushPromises()

    expect(calls.some(c => c.method === 'DELETE' && c.url.includes('/presentation/scenario'))).toBe(true)
    expect(w.text()).toContain('No scenario yet')
  })
})

