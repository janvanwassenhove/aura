import { defineStore } from 'pinia'
import { ref } from 'vue'

const BRAIN_URL =
  import.meta.env.VITE_BRAIN_URL ??
  import.meta.env.VITE_ORCHESTRATOR_URL ??
  'http://localhost:8000'

export interface SetupStatus {
  setup_done: boolean
  encrypted: boolean
  assistant_name: string
  robot_url: string
  voice_mode: string
  llm_provider: string
  openai_key_set: boolean
  openrouter_key_set: boolean
  gemini_key_set: boolean
  people_count: number
}

export interface RobotProbe {
  url: string
  ok: boolean
  mode?: string
  battery_pct?: number
  error?: string
}

export const useSetupStore = defineStore('setup', () => {
  const status = ref<SetupStatus | null>(null)
  const loading = ref(false)
  const discovering = ref(false)
  const found = ref<RobotProbe[]>([])

  async function fetchStatus(): Promise<void> {
    loading.value = true
    try {
      const resp = await fetch(`${BRAIN_URL}/setup/status`)
      if (resp.ok) status.value = await resp.json()
    } catch {
      // brain offline — leave null; App won't force the wizard
    } finally {
      loading.value = false
    }
  }

  /** Write config (secrets are write-only server-side). Returns error text or null. */
  async function saveConfig(cfg: Record<string, unknown>): Promise<string | null> {
    try {
      const resp = await fetch(`${BRAIN_URL}/setup/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cfg),
      })
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}))
        return String(data.error ?? `HTTP ${resp.status}`)
      }
      await fetchStatus()
      return null
    } catch {
      return 'AURA brain is unreachable'
    }
  }

  async function testRobot(url: string): Promise<RobotProbe> {
    try {
      const resp = await fetch(`${BRAIN_URL}/setup/test-robot`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
      })
      return await resp.json()
    } catch {
      return { url, ok: false, error: 'brain unreachable' }
    }
  }

  async function discover(): Promise<void> {
    discovering.value = true
    found.value = []
    try {
      const resp = await fetch(`${BRAIN_URL}/setup/discover`)
      const data = await resp.json()
      found.value = (data.found ?? []) as RobotProbe[]
    } catch {
      found.value = []
    } finally {
      discovering.value = false
    }
  }

  async function finish(): Promise<void> {
    await saveConfig({ setup_done: true })
  }

  return { status, loading, discovering, found, fetchStatus, saveConfig, testRobot, discover, finish }
})
