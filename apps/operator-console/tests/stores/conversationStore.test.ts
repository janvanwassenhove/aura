import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useConversationStore } from '../../src/stores/conversationStore'

describe('conversationStore', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('starts empty', () => {
    const store = useConversationStore()
    expect(store.turns).toHaveLength(0)
    expect(store.isProcessing).toBe(false)
  })

  it('addTurn appends a turn', () => {
    const store = useConversationStore()
    store.addTurn({ id: '1', role: 'user', text: 'Hello', timestamp: new Date().toISOString() })
    expect(store.turns).toHaveLength(1)
    expect(store.turns[0].text).toBe('Hello')
  })

  it('applyEvent ResponseDrafted adds assistant turn', () => {
    const store = useConversationStore()
    store.applyEvent({ event_type: 'ResponseDrafted', response_text: 'Hi there', timestamp: new Date().toISOString() })
    expect(store.turns).toHaveLength(1)
    expect(store.turns[0].role).toBe('assistant')
    expect(store.turns[0].text).toBe('Hi there')
  })

  it('dedupes an identical ResponseDrafted arriving twice (HTTP + WS echo)', () => {
    const store = useConversationStore()
    const ts = new Date().toISOString()
    // Local HTTP add first, then the same text echoes back over the WS — twice.
    store.addTurn({ id: 'local', role: 'assistant', text: 'Same answer', timestamp: ts })
    store.applyEvent({ event_type: 'ResponseDrafted', response_text: 'Same answer', timestamp: ts })
    store.applyEvent({ event_type: 'ResponseDrafted', response_text: 'Same answer', timestamp: ts })
    expect(store.turns).toHaveLength(1)
  })

  it('dedupes the user turn echoed as TranscriptUpdated', () => {
    const store = useConversationStore()
    const ts = new Date().toISOString()
    store.addTurn({ id: 'local-user', role: 'user', text: 'hello robot', timestamp: ts })
    store.applyEvent({ event_type: 'TranscriptUpdated', is_final: true, transcript: 'hello robot', session_id: 's1', timestamp: ts })
    expect(store.turns).toHaveLength(1)
  })

  it('still allows repeating the same text in a LATER exchange', () => {
    const store = useConversationStore()
    const old = new Date(Date.now() - 60_000).toISOString()  // > dedupe window
    store.addTurn({ id: 'old', role: 'assistant', text: 'Sure!', timestamp: old })
    store.applyEvent({ event_type: 'ResponseDrafted', response_text: 'Sure!', timestamp: new Date().toISOString() })
    expect(store.turns).toHaveLength(2)
  })

  it('applyEvent ToolCallRequested marks last assistant turn', () => {
    const store = useConversationStore()
    store.addTurn({ id: '2', role: 'assistant', text: 'Let me check...', timestamp: new Date().toISOString() })
    store.applyEvent({ event_type: 'ToolCallRequested', tool_name: 'list_todos' })
    expect(store.turns[0].toolCall?.name).toBe('list_todos')
    expect(store.turns[0].toolCall?.status).toBe('pending')
  })

  it('applyEvent ToolCallSucceeded updates tool status', () => {
    const store = useConversationStore()
    store.addTurn({ id: '3', role: 'assistant', text: 'Working...', timestamp: new Date().toISOString(), toolCall: { name: 'list_todos', status: 'pending' } })
    store.applyEvent({ event_type: 'ToolCallSucceeded', tool_name: 'list_todos' })
    expect(store.turns[0].toolCall?.status).toBe('succeeded')
  })

  it('$reset clears turns', () => {
    const store = useConversationStore()
    store.addTurn({ id: '4', role: 'user', text: 'x', timestamp: new Date().toISOString() })
    store.$reset()
    expect(store.turns).toHaveLength(0)
  })
})

describe('conversationStore — clear (U187)', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('clears the visible transcript but keeps the session', () => {
    const store = useConversationStore()
    store.applyEvent({ event_type: 'TranscriptUpdated', transcript: 'hoi', is_final: true })
    store.sessionId = 'sess-1'
    expect(store.turns.length).toBeGreaterThan(0)

    store.clearTurns()

    expect(store.turns).toEqual([])
    expect(store.lastLatency).toBeNull()
    expect(store.sessionId).toBe('sess-1')   // the assistant still remembers
  })
})

describe('U296 — teach leaves a visible trace, always', () => {
  beforeEach(() => setActivePinia(createPinia()))

  /** Reported as "werkt teach nog? lijkt niks te doen". The route answered
   *  fine; the console threw the answer away and waited for a WebSocket event
   *  that may never come. */
  it('shows the reply the route already returned', async () => {
    const store = useConversationStore()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true, json: async () => ({ reply: 'Saved as a skill.' }),
    }))
    await store.teach('always answer in Dutch')
    expect(store.turns.map(t => t.text)).toEqual([
      '🎓 always answer in Dutch', 'Saved as a skill.',
    ])
  })

  it('does not repeat a reply the WebSocket already delivered', async () => {
    const store = useConversationStore()
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => {
      // The event beats the response back, which is the normal race.
      store.applyEvent({ event_type: 'ResponseDrafted', response_text: 'Got it.' })
      return { ok: true, json: async () => ({ reply: 'Got it.' }) }
    }))
    await store.teach('be brief')
    expect(store.turns.filter(t => t.text === 'Got it.')).toHaveLength(1)
  })

  it('says so when the brain refuses — fetch does not throw on a 503', async () => {
    const store = useConversationStore()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false, status: 503, json: async () => ({ error: 'pipeline not ready' }),
    }))
    await store.teach('remember this')
    expect(store.turns).toHaveLength(2)
    expect(store.turns[1].text).toContain('pipeline not ready')
  })

  it('says so when the brain is unreachable', async () => {
    const store = useConversationStore()
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
    await store.teach('remember this')
    expect(store.turns[1].text).toContain('did not answer')
    expect(store.isProcessing).toBe(false)
  })

  it('an empty lesson is not sent at all', async () => {
    const store = useConversationStore()
    const f = vi.fn()
    vi.stubGlobal('fetch', f)
    await store.teach('   ')
    expect(f).not.toHaveBeenCalled()
    expect(store.turns).toHaveLength(0)
  })
})
