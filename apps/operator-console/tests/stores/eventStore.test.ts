import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useEventStore } from '../../src/stores/eventStore'

describe('eventStore', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('starts empty', () => {
    const store = useEventStore()
    expect(store.events).toHaveLength(0)
  })

  it('addEvent prepends to the list', () => {
    const store = useEventStore()
    store.addEvent({ event_type: 'RobotConnected', timestamp: new Date().toISOString() })
    expect(store.events).toHaveLength(1)
    expect(store.events[0].event_type).toBe('RobotConnected')
  })

  it('filteredEvents returns all when filter is empty', () => {
    const store = useEventStore()
    store.addEvent({ event_type: 'RobotConnected', timestamp: new Date().toISOString() })
    store.addEvent({ event_type: 'TranscriptUpdated', timestamp: new Date().toISOString() })
    expect(store.filteredEvents).toHaveLength(2)
  })

  it('filteredEvents filters by event_type substring', () => {
    const store = useEventStore()
    store.addEvent({ event_type: 'RobotConnected', timestamp: new Date().toISOString() })
    store.addEvent({ event_type: 'TranscriptUpdated', timestamp: new Date().toISOString() })
    store.addEvent({ event_type: 'RobotStateChanged', timestamp: new Date().toISOString() })
    store.filter = 'Robot'
    expect(store.filteredEvents).toHaveLength(2)
    expect(store.filteredEvents.every(e => e.event_type.includes('Robot'))).toBe(true)
  })

  it('caps at maxEvents', () => {
    const store = useEventStore()
    for (let i = 0; i < 210; i++) {
      store.addEvent({ event_type: `Event${i}`, timestamp: new Date().toISOString() })
    }
    expect(store.events.length).toBeLessThanOrEqual(200)
  })

  it('clearEvents empties the list', () => {
    const store = useEventStore()
    store.addEvent({ event_type: 'Test', timestamp: new Date().toISOString() })
    store.clearEvents()
    expect(store.events).toHaveLength(0)
  })
})
