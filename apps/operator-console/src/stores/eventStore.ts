import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface BusEvent {
  id: string
  event_type: string
  session_id?: string
  timestamp: string
  payload: Record<string, unknown>
}

export const useEventStore = defineStore('eventLog', () => {
  const events = ref<BusEvent[]>([])
  const filter = ref('')
  const maxEvents = 200

  const filteredEvents = computed(() => {
    if (!filter.value.trim()) return events.value
    const q = filter.value.toLowerCase()
    return events.value.filter(e => e.event_type.toLowerCase().includes(q))
  })

  function addEvent(raw: Record<string, unknown>) {
    const entry: BusEvent = {
      id: crypto.randomUUID(),
      event_type: (raw.event_type as string) ?? 'Unknown',
      session_id: raw.session_id as string | undefined,
      timestamp: (raw.timestamp as string) ?? new Date().toISOString(),
      payload: raw,
    }
    events.value.unshift(entry)
    if (events.value.length > maxEvents) events.value.length = maxEvents
  }

  function clearEvents() {
    events.value = []
  }

  function $reset() {
    events.value = []
    filter.value = ''
  }

  return { events, filter, filteredEvents, addEvent, clearEvents, $reset }
})
