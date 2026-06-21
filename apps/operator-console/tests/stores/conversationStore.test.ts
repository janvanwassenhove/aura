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
