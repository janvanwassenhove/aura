import { ref, onUnmounted } from 'vue'
import { useRobotStore } from '../stores/robotStore'
import { useConversationStore } from '../stores/conversationStore'
import { useEventStore } from '../stores/eventStore'
import { useApprovalStore } from '../stores/approvalStore'

const WS_URL = import.meta.env.VITE_ROBOT_RUNTIME_WS ?? 'ws://localhost:8001/ws/events'
const RECONNECT_BASE_MS = 1_000
const RECONNECT_MAX_MS = 30_000

export function useEventBusWs() {
  const wsStatus = ref<'connecting' | 'open' | 'closed'>('closed')
  let ws: WebSocket | null = null
  let reconnectDelay = RECONNECT_BASE_MS
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null

  function dispatch(raw: Record<string, unknown>) {
    const robotStore = useRobotStore()
    const conversationStore = useConversationStore()
    const eventStore = useEventStore()
    const approvalStore = useApprovalStore()

    robotStore.applyEvent(raw)
    conversationStore.applyEvent(raw)
    eventStore.addEvent(raw)
    approvalStore.applyEvent(raw)
  }

  function connect() {
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
    wsStatus.value = 'connecting'
    ws = new WebSocket(WS_URL)

    ws.onopen = () => {
      wsStatus.value = 'open'
      reconnectDelay = RECONNECT_BASE_MS
    }

    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data as string)
        dispatch(data)
      } catch { /* ignore malformed frames */ }
    }

    ws.onclose = () => {
      wsStatus.value = 'closed'
      reconnectTimer = setTimeout(connect, reconnectDelay)
      reconnectDelay = Math.min(reconnectDelay * 2, RECONNECT_MAX_MS)
    }

    ws.onerror = () => {
      ws?.close()
    }
  }

  function disconnect() {
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
    ws?.close()
    ws = null
  }

  onUnmounted(disconnect)

  return { wsStatus, connect, disconnect }
}
