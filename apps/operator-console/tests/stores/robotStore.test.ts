import { describe, it, expect, beforeEach, vi } from 'vitest'
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

describe('robotStore — follow-me mode (U162)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('defaults to following (the adapter enables tracking on connect)', () => {
    expect(useRobotStore().tracking).toBe(true)
  })

  it('setTracking flips the shared state and calls the brain', async () => {
    const store = useRobotStore()
    const fetchMock = vi.fn().mockResolvedValue({ ok: true })
    vi.stubGlobal('fetch', fetchMock)

    expect(await store.setTracking(false, 'http://brain')).toBe(true)
    expect(store.tracking).toBe(false)          // → Manual mode
    expect(fetchMock).toHaveBeenCalledWith(
      'http://brain/robot/tracking',
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ enabled: false }) }),
    )
  })

  it('reverts when the robot refuses, so the UI never claims a mode it is not in', async () => {
    const store = useRobotStore()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 503 }))

    expect(await store.setTracking(false, 'http://brain')).toBe(false)
    expect(store.tracking).toBe(true)           // still following
  })

  it('reverts when the brain is unreachable', async () => {
    const store = useRobotStore()
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))

    expect(await store.setTracking(false, 'http://brain')).toBe(false)
    expect(store.tracking).toBe(true)
  })

  it('syncFromStatus takes the robot as source of truth', () => {
    const store = useRobotStore()
    // A motion (or the follow-me watchdog) changed tracking without us asking.
    store.syncFromStatus({ connected: true, mode: 'home', tracking: false })
    expect(store.tracking).toBe(false)
    store.syncFromStatus({ connected: true, mode: 'home', tracking: true })
    expect(store.tracking).toBe(true)
  })

  it('syncFromStatus leaves tracking alone when the robot omits it', () => {
    const store = useRobotStore()
    store.syncFromStatus({ connected: true, mode: 'home', tracking: false })
    store.syncFromStatus({ connected: true, mode: 'home' })   // older payload
    expect(store.tracking).toBe(false)
  })
})

describe('robotStore — face visibility (U165)', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('reports whether the robot actually sees a face', () => {
    const store = useRobotStore()
    expect(store.faceVisible).toBeNull()          // unknown until the robot says
    store.syncFromStatus({ connected: true, tracking: true, face_visible: true })
    expect(store.faceVisible).toBe(true)
    store.syncFromStatus({ connected: true, tracking: true, face_visible: false })
    expect(store.faceVisible).toBe(false)
  })

  it('falls back to unknown when the robot omits the field', () => {
    const store = useRobotStore()
    store.syncFromStatus({ connected: true, tracking: true, face_visible: true })
    store.syncFromStatus({ connected: true, tracking: true })   // older robot
    expect(store.faceVisible).toBeNull()
  })
})
