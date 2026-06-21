import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useRobotStore } from '../../src/stores/robotStore'

describe('robotStore', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('starts with unknown mode and not connected', () => {
    const store = useRobotStore()
    expect(store.mode).toBe('unknown')
    expect(store.connected).toBe(false)
  })

  it('sets connected and mode on RobotConnected event', () => {
    const store = useRobotStore()
    store.applyEvent({ event_type: 'RobotConnected', mode: 'work' })
    expect(store.connected).toBe(true)
    expect(store.mode).toBe('work')
  })

  it('sets connected=false on RobotDisconnected event', () => {
    const store = useRobotStore()
    store.applyEvent({ event_type: 'RobotConnected', mode: 'work' })
    store.applyEvent({ event_type: 'RobotDisconnected' })
    expect(store.connected).toBe(false)
  })

  it('updates mode and behaviorState on RobotStateChanged', () => {
    const store = useRobotStore()
    store.applyEvent({ event_type: 'RobotConnected', mode: 'work' })
    store.applyEvent({ event_type: 'RobotStateChanged', mode: 'DEGRADED', behavior_state: 'error' })
    expect(store.mode).toBe('DEGRADED')
    expect(store.behaviorState).toBe('error')
    expect(store.statusBadgeClass).toBe('badge-red')
  })

  it('adds motion entry on MotionStarted', () => {
    const store = useRobotStore()
    store.applyEvent({ event_type: 'MotionStarted', motion_name: 'wave' })
    expect(store.motionLog).toHaveLength(1)
    expect(store.motionLog[0].name).toBe('wave')
    expect(store.motionLog[0].status).toBe('started')
  })

  it('marks motion completed on MotionCompleted', () => {
    const store = useRobotStore()
    store.applyEvent({ event_type: 'MotionStarted', motion_name: 'nod' })
    store.applyEvent({ event_type: 'MotionCompleted', motion_name: 'nod' })
    expect(store.motionLog[0].status).toBe('completed')
  })

  it('caps motion log at 10 entries', () => {
    const store = useRobotStore()
    for (let i = 0; i < 15; i++) {
      store.applyEvent({ event_type: 'MotionStarted', motion_name: `m${i}` })
    }
    expect(store.motionLog.length).toBeLessThanOrEqual(10)
  })

  it('sets isSpeaking on SpeechStarted', () => {
    const store = useRobotStore()
    store.applyEvent({ event_type: 'SpeechStarted' })
    expect(store.isSpeaking).toBe(true)
  })

  it('clears isSpeaking on SpeechCompleted', () => {
    const store = useRobotStore()
    store.applyEvent({ event_type: 'SpeechStarted' })
    store.applyEvent({ event_type: 'SpeechCompleted' })
    expect(store.isSpeaking).toBe(false)
  })

  it('$reset restores defaults', () => {
    const store = useRobotStore()
    store.applyEvent({ event_type: 'RobotConnected', mode: 'work' })
    store.$reset()
    expect(store.mode).toBe('unknown')
    expect(store.connected).toBe(false)
  })
})
