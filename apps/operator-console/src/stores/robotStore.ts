import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface MotionLogEntry {
  id: string
  name: string
  timestamp: string
  status: 'started' | 'completed' | 'failed'
}

export interface RecognizedPerson {
  person_id: string | null
  display_name: string | null
  confidence: number
  known: boolean
  timestamp: string
}

export const useRobotStore = defineStore('robot', () => {
  const mode = ref<string>('unknown')
  const behaviorState = ref<string>('idle')
  const isSpeaking = ref(false)
  const currentTranscript = ref('')
  const uptime = ref(0)
  const connected = ref(false)
  const motionLog = ref<MotionLogEntry[]>([])
  const lastRecognized = ref<RecognizedPerson | null>(null)
  // U162: follow-me lives HERE, not in a component. Two surfaces drive it (the
  // Robot panel's Follow toggle and the camera's Follow/Manual switch); with a
  // ref per component they drifted apart and the robot fought the operator —
  // one showing "following" while the other had just aimed manually.
  const tracking = ref(true)   // the adapter enables head tracking on connect

  const statusBadgeClass = computed(() => {
    if (!connected.value) return 'badge-gray'
    switch (mode.value) {
      case 'work': return 'badge-blue'
      case 'home': return 'badge-green'
      case 'presentation': return 'badge-purple'
      case 'DEGRADED': return 'badge-red'
      default: return 'badge-gray'
    }
  })

  function applyEvent(event: Record<string, unknown>) {
    const type = event.event_type as string
    if (!type) return

    if (type === 'RobotConnected') {
      connected.value = true
      mode.value = (event.mode as string) ?? mode.value
    } else if (type === 'RobotDisconnected') {
      connected.value = false
    } else if (type === 'RobotStateChanged') {
      mode.value = (event.mode as string) ?? mode.value
      behaviorState.value = (event.behavior_state as string) ?? behaviorState.value
    } else if (type === 'RobotModeChanged') {
      // U15: OfflineBehaviorLoop emits this when the robot goes offline or recovers.
      mode.value = (event.to_mode as string) ?? mode.value
    } else if (type === 'PersonRecognized') {
      // U18: face-recognition result from the perception layer.
      lastRecognized.value = {
        person_id: (event.person_id as string | null) ?? null,
        display_name: (event.display_name as string | null) ?? null,
        confidence: (event.confidence as number) ?? 0,
        known: (event.known as boolean) ?? false,
        timestamp: (event.timestamp as string) ?? new Date().toISOString(),
      }
    } else if (type === 'MotionStarted') {
      connected.value = true
      const entry: MotionLogEntry = {
        id: crypto.randomUUID(),
        name: (event.motion_id as string) ?? (event.motion_name as string) ?? 'unknown',
        timestamp: new Date().toISOString(),
        status: 'started',
      }
      motionLog.value.unshift(entry)
      if (motionLog.value.length > 10) motionLog.value.pop()
    } else if (type === 'MotionCompleted') {
      const name = (event.motion_id as string) ?? (event.motion_name as string)
      const entry = motionLog.value.find(e => e.name === name && e.status === 'started')
      if (entry) entry.status = 'completed'
    } else if (type === 'MotionFailed') {
      const name = (event.motion_id as string) ?? (event.motion_name as string)
      const entry = motionLog.value.find(e => e.name === name && e.status === 'started')
      if (entry) entry.status = 'failed'
    } else if (type === 'SpeechStarted' || type === 'SpeechPlaybackStarted') {
      connected.value = true
      isSpeaking.value = true
      currentTranscript.value = (event.text as string) ?? ''
    } else if (type === 'SpeechCompleted' || type === 'SpeechPlaybackCompleted') {
      isSpeaking.value = false
    } else if (type === 'BehaviorStateChanged') {
      connected.value = true
      behaviorState.value = (event.behavior_state as string) ?? behaviorState.value
    } else if (type === 'TranscriptUpdated') {
      currentTranscript.value = (event.transcript as string) ?? ''
    }
  }

  // U152: sync from a /robot/status poll. WS events (RobotConnected) can be
  // missed if the robot connected before the console opened or during a network
  // blip, leaving the title bar wrongly "offline" while the camera streams fine.
  function syncFromStatus(s: { connected?: boolean; mode?: string; tracking?: boolean } | null): void {
    if (!s) return
    connected.value = s.connected === true
    if (s.mode) mode.value = s.mode
    // U162: the robot is the source of truth — a motion or the follow-me
    // watchdog can change tracking without the console asking.
    if (typeof s.tracking === 'boolean') tracking.value = s.tracking
  }

  /** U162: flip follow-me on the robot; reverts on failure so the UI never
   *  claims a mode the robot isn't in. Returns whether it took. */
  async function setTracking(enabled: boolean, brainUrl: string): Promise<boolean> {
    const previous = tracking.value
    tracking.value = enabled          // optimistic: the switch feels instant
    try {
      const resp = await fetch(`${brainUrl}/robot/tracking`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      })
      if (!resp.ok) throw new Error(String(resp.status))
      return true
    } catch {
      tracking.value = previous
      return false
    }
  }

  function $reset() {
    mode.value = 'unknown'
    behaviorState.value = 'idle'
    isSpeaking.value = false
    currentTranscript.value = ''
    uptime.value = 0
    connected.value = false
    motionLog.value = []
    lastRecognized.value = null
    tracking.value = true
  }

  return { mode, behaviorState, isSpeaking, currentTranscript, uptime, connected, motionLog, lastRecognized, tracking, statusBadgeClass, applyEvent, syncFromStatus, setTracking, $reset }
})
