import { describe, it, expect, beforeEach } from 'vitest'
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
