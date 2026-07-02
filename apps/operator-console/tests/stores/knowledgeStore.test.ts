import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useKnowledgeStore } from '../../src/stores/knowledgeStore'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('knowledgeStore', () => {
  beforeEach(() => setActivePinia(createPinia()))
  afterEach(() => vi.unstubAllGlobals())

  it('starts empty, benign, and unlocked', () => {
    const store = useKnowledgeStore()
    expect(store.people).toEqual([])
    expect(store.detail).toBeNull()
    expect(store.tier).toBe('benign')
    expect(store.locked).toBe(false)
    expect(store.error).toBeNull()
  })

  it('fetchTier updates tier and omkLoaded', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ tier: 'sensitive', omk_loaded: true })))
    const store = useKnowledgeStore()
    await store.fetchTier()
    expect(store.tier).toBe('sensitive')
    expect(store.omkLoaded).toBe(true)
  })

  it('fetchPeople populates the people list', async () => {
    const people = [{ person_id: 'jan', display_name: 'Jan', role: 'owner' }]
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(people)))
    const store = useKnowledgeStore()
    await store.fetchPeople()
    expect(store.people).toEqual(people)
    expect(store.loading).toBe(false)
  })

  it('inspectPerson stores person detail with facts and signals', async () => {
    const detail = {
      person: { person_id: 'jan', display_name: 'Jan', role: 'owner' },
      facts: [{ fact_id: 'f1', person_id: 'jan', key: 'likes', value: 'coffee', source: 'stated' }],
      signals: [{ signal_id: 's1', person_id: 'jan', kind: 'topic', value: 'robots', confidence: 0.8, evidence_count: 3 }],
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(detail)))
    const store = useKnowledgeStore()
    await store.inspectPerson('jan')
    expect(store.detail?.person.person_id).toBe('jan')
    expect(store.detail?.facts).toHaveLength(1)
    expect(store.detail?.signals).toHaveLength(1)
  })

  it('sets locked and a clear error on 403 (encrypted store locked)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ detail: 'locked' }, 403)))
    const store = useKnowledgeStore()
    await store.fetchPeople()
    expect(store.locked).toBe(true)
    expect(store.error).toContain('locked')
    expect(store.people).toEqual([])
  })

  it('clears locked once a request succeeds again', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ detail: 'locked' }, 403))
      .mockResolvedValueOnce(jsonResponse([]))
    vi.stubGlobal('fetch', fetchMock)
    const store = useKnowledgeStore()
    await store.fetchPeople()
    expect(store.locked).toBe(true)
    await store.fetchPeople()
    expect(store.locked).toBe(false)
  })

  it('surfaces API error detail on non-403 failures', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ detail: 'unknown person' }, 404)))
    const store = useKnowledgeStore()
    await store.inspectPerson('ghost')
    expect(store.error).toBe('unknown person')
    expect(store.detail).toBeNull()
  })

  it('sets a network error when the brain is unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('fetch failed')))
    const store = useKnowledgeStore()
    await store.fetchPeople()
    expect(store.error).toContain('Could not reach')
  })

  it('upsertPerson PUTs the person and refreshes the list', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ person_id: 'ada', display_name: 'Ada', role: 'family' }))
      .mockResolvedValueOnce(jsonResponse([{ person_id: 'ada', display_name: 'Ada', role: 'family' }]))
    vi.stubGlobal('fetch', fetchMock)
    const store = useKnowledgeStore()
    const ok = await store.upsertPerson('ada', 'Ada', 'family')
    expect(ok).toBe(true)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toContain('/knowledge/people/ada')
    expect(init.method).toBe('PUT')
    expect(JSON.parse(init.body)).toEqual({ display_name: 'Ada', role: 'family' })
    expect(store.people).toHaveLength(1)
  })

  it('addFact POSTs the fact and re-inspects the person', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ fact_id: 'f2' }))
      .mockResolvedValueOnce(jsonResponse({ person: { person_id: 'jan', display_name: 'Jan', role: 'owner' }, facts: [], signals: [] }))
    vi.stubGlobal('fetch', fetchMock)
    const store = useKnowledgeStore()
    const ok = await store.addFact('jan', 'likes', 'coffee')
    expect(ok).toBe(true)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toContain('/knowledge/people/jan/facts')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({ key: 'likes', value: 'coffee' })
  })

  it('deleteFact DELETEs by fact id', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ deleted: true }))
      .mockResolvedValueOnce(jsonResponse({ person: { person_id: 'jan', display_name: 'Jan', role: 'owner' }, facts: [], signals: [] }))
    vi.stubGlobal('fetch', fetchMock)
    const store = useKnowledgeStore()
    const ok = await store.deleteFact('f1', 'jan')
    expect(ok).toBe(true)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toContain('/knowledge/facts/f1')
    expect(init.method).toBe('DELETE')
  })

  it('forgetPerson clears detail for the erased person and refreshes the list', async () => {
    const detail = {
      person: { person_id: 'guest1', display_name: 'Guest', role: 'guest' },
      facts: [],
      signals: [],
    }
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(detail)) // inspect
      .mockResolvedValueOnce(jsonResponse({ erased: true })) // delete
      .mockResolvedValueOnce(jsonResponse([])) // refreshed people list
    vi.stubGlobal('fetch', fetchMock)
    const store = useKnowledgeStore()
    await store.inspectPerson('guest1')
    expect(store.detail).not.toBeNull()
    const ok = await store.forgetPerson('guest1')
    expect(ok).toBe(true)
    expect(store.detail).toBeNull()
    expect(fetchMock.mock.calls[1][1].method).toBe('DELETE')
  })

  it('setConsent POSTs owner-granted consent scope', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ granted: true }))
    vi.stubGlobal('fetch', fetchMock)
    const store = useKnowledgeStore()
    const ok = await store.setConsent('kid1', 'observed_signals')
    expect(ok).toBe(true)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toContain('/knowledge/people/kid1/consent')
    expect(JSON.parse(init.body)).toEqual({ granted_by: 'owner', scope: 'observed_signals' })
  })

  it('lock drops tier to benign and marks locked when store is encrypted', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ tier: 'benign', locked: true })))
    const store = useKnowledgeStore()
    store.tier = 'sensitive'
    store.omkLoaded = true
    await store.lock()
    expect(store.tier).toBe('benign')
    expect(store.locked).toBe(true)
  })

  it('lock leaves an unencrypted dev store accessible', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ tier: 'benign', locked: false })))
    const store = useKnowledgeStore()
    store.tier = 'sensitive'
    store.omkLoaded = false
    await store.lock()
    expect(store.tier).toBe('benign')
    expect(store.locked).toBe(false)
  })

  it('$reset restores defaults', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ tier: 'sensitive', omk_loaded: true })))
    const store = useKnowledgeStore()
    await store.fetchTier()
    store.$reset()
    expect(store.tier).toBe('benign')
    expect(store.omkLoaded).toBe(false)
    expect(store.people).toEqual([])
    expect(store.detail).toBeNull()
  })
})
