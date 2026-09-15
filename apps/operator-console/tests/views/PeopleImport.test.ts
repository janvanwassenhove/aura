import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises, enableAutoUnmount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import PeopleView from '../../src/views/PeopleView.vue'
import { useKnowledgeStore } from '../../src/stores/knowledgeStore'

/** U362, second instance: the same file, picked twice, does nothing.
 *
 *  A file input only fires `change` when its VALUE changes, so re-picking the
 *  file you just picked is not a change and the handler never runs. Reported
 *  against Present; People had it too. SettingsView is the one that got it
 *  right, and it got it right by accident of being written later.
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
    // The view re-fetches the person it is showing. Answering {} overwrites
    // `detail` mid-render and throws inside the template - which vitest
    // reports as an unhandled rejection and warns can cause false positives.
    if (u.includes('/knowledge/people/jan')) {
      return { ok: true, json: async () => PERSON } as unknown as Response
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

/** jsdom reports a file input's value as '' and refuses to be set, so
 *  `expect(el.value).toBe('')` passes with or without the fix. Watch the write. */
function watchClear(el: HTMLInputElement, text: string): string[] {
  const writes: string[] = []
  Object.defineProperty(el, 'files', {
    value: [{ name: 'chats.json', text: async () => text } as unknown as File],
    configurable: true,
  })
  Object.defineProperty(el, 'value', {
    get: () => '', set: (v: string) => { writes.push(v) }, configurable: true,
  })
  return writes
}

describe('U362 — importing the same chat export twice', () => {
  it('clears the file input after a successful import', async () => {
    const w = mount(PeopleView)
    const knowledge = useKnowledgeStore()
    knowledge.detail = PERSON as never
    knowledge.personTab = 'Sources'      // where import lives
    await flushPromises()

    const el = w.find('input[type="file"]').element as HTMLInputElement
    const writes = watchClear(el, '[]')

    await (w.vm as unknown as { doImport: (e: Event) => Promise<void> })
      .doImport({ target: el } as unknown as Event)
    await flushPromises()

    expect(writes).toContain('')
  })

  it('clears it after a bad file too', async () => {
    // The one time you are certain to pick the same name again is straight
    // after a rejected file, having just fixed it.
    const w = mount(PeopleView)
    const knowledge = useKnowledgeStore()
    knowledge.detail = PERSON as never
    knowledge.personTab = 'Sources'      // where import lives
    await flushPromises()

    const el = w.find('input[type="file"]').element as HTMLInputElement
    const writes = watchClear(el, 'not json at all')

    await (w.vm as unknown as { doImport: (e: Event) => Promise<void> })
      .doImport({ target: el } as unknown as Event)
    await flushPromises()

    expect(writes).toContain('')
    expect(w.text()).toContain('not valid JSON')
  })
})
