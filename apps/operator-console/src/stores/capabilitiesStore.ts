import { defineStore } from 'pinia'
import { ref } from 'vue'

const BRAIN_URL =
  import.meta.env.VITE_BRAIN_URL ??
  import.meta.env.VITE_ORCHESTRATOR_URL ??
  'http://localhost:8000'

export interface Capability {
  key: string
  label: string
  description: string
  enabled: boolean
  applies_live: boolean
}

export const useCapabilitiesStore = defineStore('capabilities', () => {
  const capabilities = ref<Capability[]>([])
  const allowedApps = ref<string[]>([])
  const pending = ref<string[]>([]) // keys toggled that need a restart to apply
  const loading = ref(false)
  const error = ref<string | null>(null)
  const notice = ref<string | null>(null)

  async function fetchCapabilities(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const resp = await fetch(`${BRAIN_URL}/capabilities`)
      if (resp.ok) {
        const data = await resp.json()
        capabilities.value = data.capabilities ?? []
        allowedApps.value = data.allowed_apps ?? []
      } else {
        error.value = `Could not load capabilities (${resp.status})`
      }
    } catch {
      error.value = 'Could not reach the brain.'
    } finally {
      loading.value = false
    }
  }

  async function toggle(key: string, enabled: boolean): Promise<void> {
    notice.value = null
    // Optimistic UI.
    const cap = capabilities.value.find(c => c.key === key)
    if (cap) cap.enabled = enabled
    try {
      const resp = await fetch(`${BRAIN_URL}/capabilities/${key}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      })
      const body = await resp.json().catch(() => ({}))
      if (!resp.ok) {
        if (cap) cap.enabled = !enabled // revert
        error.value = body.error ?? `Toggle failed (${resp.status})`
        return
      }
      if (body.restart_required) {
        notice.value = `"${cap?.label ?? key}" will take effect after the next restart.`
        if (!pending.value.includes(key)) pending.value.push(key)
      } else {
        pending.value = pending.value.filter(k => k !== key)
      }
    } catch {
      if (cap) cap.enabled = !enabled
      error.value = 'Could not reach the brain.'
    }
  }

  return { capabilities, allowedApps, pending, loading, error, notice, fetchCapabilities, toggle }
})
