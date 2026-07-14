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
  // U23: last TurnLatencyMeasured event, shown in the conversation panel.
  const lastLatency = ref<{ total_ms: number; llm_ms: number; tool_ms: number } | null>(null)
  // U62: live agentic-loop state (AgentRoundStarted/Completed, U57).
  const agentRound = ref<{ round: number; max: number; tools: string[] } | null>(null)
  // U75: AURA is driving the screen (mouse glow overlay + abort button).
  const screenControl = ref(false)

  const conversationUrl = import.meta.env.VITE_CONVERSATION_URL ?? 'http://localhost:8002'
  const orchestratorUrl =
    import.meta.env.VITE_BRAIN_URL ??
    import.meta.env.VITE_ORCHESTRATOR_URL ??
    'http://localhost:8000'

  function addTurn(turn: ConversationTurn) {
    turns.value.push(turn)
  }

  // Turns arrive twice by design: once from the HTTP round-trip (submitTurn)
  // and once as bus events over the WebSocket. Treat an identical role+text
  // within a short window as the same turn.
  const DEDUPE_WINDOW_MS = 15_000
  function isRecentDuplicate(role: 'user' | 'assistant', text: string): boolean {
    const now = Date.now()
    return turns.value.slice(-8).some(
      t => t.role === role && t.text === text
        && now - new Date(t.timestamp).getTime() < DEDUPE_WINDOW_MS,
    )
  }

  function applyEvent(event: Record<string, unknown>) {
    const type = event.event_type as string
    if (type === 'TranscriptUpdated' && event.is_final) {
      const text = event.transcript as string
      if (!isRecentDuplicate('user', text)) {
        addTurn({
          id: crypto.randomUUID(),
          role: 'user',
          text,
          timestamp: (event.timestamp as string) ?? new Date().toISOString(),
        })
      }
    } else if (type === 'ResponseDrafted') {
      const text = event.response_text as string
      if (!isRecentDuplicate('assistant', text)) {
        addTurn({
          id: crypto.randomUUID(),
          role: 'assistant',
          text,
          timestamp: (event.timestamp as string) ?? new Date().toISOString(),
        })
      }
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
    } else if (type === 'AgentRoundStarted') {
      agentRound.value = {
        round: (event.round_no as number) ?? 1,
        max: (event.max_rounds as number) ?? 8,
        tools: [],
      }
    } else if (type === 'AgentRoundCompleted') {
      if (event.done) agentRound.value = null
      else if (agentRound.value) agentRound.value.tools = (event.tool_names as string[]) ?? []
    } else if (type === 'ComputerControlStarted') {
      screenControl.value = true
      ;(window as any).aura?.screenControl?.(true)
    } else if (type === 'ComputerControlEnded') {
      screenControl.value = false
      ;(window as any).aura?.screenControl?.(false)
    } else if (type === 'TurnLatencyMeasured') {
      // U23: per-turn latency instrumentation.
      lastLatency.value = {
        total_ms: (event.total_ms as number) ?? 0,
        llm_ms: (event.llm_ms as number) ?? 0,
        tool_ms: (event.tool_ms as number) ?? 0,
      }
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
        // The WS event may have rendered this reply already (race) — dedupe.
        if (!isRecentDuplicate('assistant', data.reply)) {
          addTurn({ id: crypto.randomUUID(), role: 'assistant', text: data.reply, timestamp: new Date().toISOString() })
        }
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
    lastLatency.value = null
  }

  // U62: steer / stop the running agentic loop; teach the brain (U60).
  async function steerAgent(text: string): Promise<void> {
    if (!text.trim()) return
    await fetch(`${orchestratorUrl}/orchestrator/agent/steer`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, session_id: sessionId.value ?? 'console' }),
    }).catch(() => {})
  }

  async function abortScreenControl(): Promise<void> {
    await fetch(`${orchestratorUrl}/orchestrator/computeruse/abort`, { method: 'POST' })
      .catch(() => {})
  }

  async function stopAgent(): Promise<void> {
    await fetch(`${orchestratorUrl}/orchestrator/agent/stop`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId.value ?? 'console' }),
    }).catch(() => {})
  }

  async function teach(text: string): Promise<void> {
    if (!text.trim() || isProcessing.value) return
    isProcessing.value = true
    addTurn({ id: crypto.randomUUID(), role: 'user', text: `🎓 ${text}`,
              timestamp: new Date().toISOString() })
    try {
      // The reply arrives as a ResponseDrafted event over the WebSocket.
      await fetch(`${orchestratorUrl}/orchestrator/agent/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, session_id: sessionId.value ?? 'console' }),
      })
    } catch { /* brain offline */ } finally {
      isProcessing.value = false
    }
  }

  return { turns, pendingText, isProcessing, sessionId, lastLatency, agentRound,
           screenControl, abortScreenControl,
           addTurn, applyEvent, submitTurn, steerAgent, stopAgent, teach, $reset }
})
