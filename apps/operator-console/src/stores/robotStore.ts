import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface MotionLogEntry {
  id: string
  name: string
  timestamp: string
  status: 'started' | 'completed' | 'failed'
}

export const useRobotStore = defineStore('robot', () => {
  const mode = ref<string>('unknown')
  const behaviorState = ref<string>('idle')
  const isSpeaking = ref(false)
  const currentTranscript = ref('')
  const uptime = ref(0)
  const connected = ref(false)
  const motionLog = ref<MotionLogEntry[]>([])

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
    } else if (type === 'MotionStarted') {
      isSpeaking.value = false
      const entry: MotionLogEntry = {
        id: crypto.randomUUID(),
        name: (event.motion_name as string) ?? 'unknown',
        timestamp: new Date().toISOString(),
        status: 'started',
      }
      motionLog.value.unshift(entry)
      if (motionLog.value.length > 10) motionLog.value.pop()
    } else if (type === 'MotionCompleted') {
      const entry = motionLog.value.find(e => e.name === event.motion_name && e.status === 'started')
      if (entry) entry.status = 'completed'
    } else if (type === 'SpeechStarted') {
      isSpeaking.value = true
      currentTranscript.value = ''
    } else if (type === 'SpeechCompleted') {
      isSpeaking.value = false
    } else if (type === 'TranscriptUpdated') {
      currentTranscript.value = (event.transcript as string) ?? ''
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
  }

  return { mode, behaviorState, isSpeaking, currentTranscript, uptime, connected, motionLog, statusBadgeClass, applyEvent, $reset }
})
