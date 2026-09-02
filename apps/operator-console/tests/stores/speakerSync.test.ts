import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useKnowledgeStore } from '../../src/stores/knowledgeStore'

/** U290: "Nothing is being remembered right now" — while it was.
 *
 *  Reported with a screenshot: the header reading "Jan · owner · tap to
 *  switch" and, directly below it, the banner claiming he did not know who he
 *  was talking to. Asking the brain settled it — it answered
 *  `{"person_id":"jan","remembering":true}`. The console was showing a
 *  SNAPSHOT: `remembering` was fetched once when the view mounted and never
 *  again, so a person recognised a moment later never reached the banner.
 *
 *  And the disagreement ran both ways: a restarted brain forgets who is there
 *  while this tab still shows them in the header.
 */

const OK = (body: unknown) => Promise.resolve({
  ok: true, status: 200, json: () => Promise.resolve(body),
} as Response)

beforeEach(() => {
  vi.unstubAllGlobals()
  setActivePinia(createPinia())
})

describe('U290 — the console and the brain agree about who is here', () => {
  it('picks up a person the brain learned after this view mounted', async () => {
    const store = useKnowledgeStore()
    expect(store.remembering).toBe(false)

    vi.stubGlobal('fetch', () => OK({ person_id: 'jan', display_name: 'Jan', remembering: true }))
    await store.fetchSpeaker()

    expect(store.remembering).toBe(true)
    expect(store.speaker).toBe('jan')
  })

  it('tells the brain again when it has forgotten but the owner has not', async () => {
    // A restarted brain: the header still says Jan, the brain knows nobody.
    const posts: string[] = []
    const store = useKnowledgeStore()
    vi.stubGlobal('fetch', (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        posts.push(String(init.body))
        return OK({ person_id: 'jan', display_name: 'Jan', remembering: true })
      }
      return OK({ person_id: null, remembering: false })
    })
    store.setSpeaker('jan', 'manual')
    posts.length = 0            // ignore the write that the pick itself made

    await store.fetchSpeaker()

    expect(posts).toHaveLength(1)
    expect(posts[0]).toContain('jan')
  })

  it('does not re-assert a guest, who is nobody to remember against', async () => {
    const posts: string[] = []
    const store = useKnowledgeStore()
    vi.stubGlobal('fetch', (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') { posts.push(String(init.body)); return OK({ remembering: false }) }
      return OK({ person_id: null, remembering: false })
    })
    store.setSpeaker('guest', 'manual')
    posts.length = 0

    await store.fetchSpeaker()

    expect(posts).toHaveLength(0)
    expect(store.remembering).toBe(false)
  })

  it('leaves everything alone when the brain cannot be reached', async () => {
    const store = useKnowledgeStore()
    vi.stubGlobal('fetch', () => Promise.reject(new Error('offline')))
    store.setSpeaker('jan', 'manual')

    await store.fetchSpeaker()

    // The owner's pick survives a dead brain.
    expect(store.speaker).toBe('jan')
  })
})
