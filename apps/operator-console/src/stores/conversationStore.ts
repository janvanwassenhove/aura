import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface ConversationTurn {
  id: string
  role: 'user' | 'assistant'
  text: string
  timestamp: string
  toolCall?: { name: string; status: 'pending' | 'approved' | 'denied' | 'succeeded' | 'failed' }
}

export const useConversationStore = defineStore('conversation', () => {
  const turns = ref<ConversationTurn[]>([])
  const pendingText = ref('')
  const isProcessing = ref(false)
  const sessionId = ref<string | null>(null)

  const conversationUrl = import.meta.env.VITE_CONVERSATION_URL ?? 'http://localhost:8002'

  function addTurn(turn: ConversationTurn) {
    turns.value.push(turn)
  }

  function applyEvent(event: Record<string, unknown>) {
    const type = event.event_type as string
    if (type === 'TranscriptUpdated' && event.is_final) {
      const existing = turns.value.find(t => t.id === (event.session_id as string) + '-user-latest')
      if (!existing) {
        addTurn({
          id: (event.session_id as string) + '-user-latest',
          role: 'user',
          text: event.transcript as string,
          timestamp: (event.timestamp as string) ?? new Date().toISOString(),
        })
      }
    } else if (type === 'ResponseDrafted') {
      addTurn({
        id: crypto.randomUUID(),
        role: 'assistant',
        text: event.response_text as string,
        timestamp: (event.timestamp as string) ?? new Date().toISOString(),
      })
    } else if (type === 'ToolCallRequested') {
      const last = turns.value.at(-1)
      if (last?.role === 'assistant') {
        last.toolCall = { name: event.tool_name as string, status: 'pending' }
      }
    } else if (type === 'ToolCallSucceeded') {
      const turn = turns.value.findLast(t => t.toolCall?.name === event.tool_name)
      if (turn?.toolCall) turn.toolCall.status = 'succeeded'
    } else if (type === 'ToolCallFailed') {
      const turn = turns.value.findLast(t => t.toolCall?.name === event.tool_name)
      if (turn?.toolCall) turn.toolCall.status = 'failed'
    }
  }

  async function submitTurn(text: string): Promise<void> {
    if (isProcessing.value || !text.trim()) return
    isProcessing.value = true

    addTurn({ id: crypto.randomUUID(), role: 'user', text, timestamp: new Date().toISOString() })

    try {
      const response = await fetch(`${conversationUrl}/conversation/turn`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, session_id: sessionId.value ?? 'console' }),
      })
      if (response.ok) {
        const data = await response.json()
        if (!sessionId.value) sessionId.value = data.session_id
        addTurn({ id: crypto.randomUUID(), role: 'assistant', text: data.reply, timestamp: new Date().toISOString() })
      }
    } catch (err) {
      addTurn({ id: crypto.randomUUID(), role: 'assistant', text: '[error: could not reach conversation service]', timestamp: new Date().toISOString() })
    } finally {
      isProcessing.value = false
      pendingText.value = ''
    }
  }

  function $reset() {
    turns.value = []
    pendingText.value = ''
    isProcessing.value = false
    sessionId.value = null
  }

  return { turns, pendingText, isProcessing, sessionId, addTurn, applyEvent, submitTurn, $reset }
})
