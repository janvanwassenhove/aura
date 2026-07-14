import { defineStore } from 'pinia'
import { ref } from 'vue'

export type LLMProvider = 'openai' | 'openrouter' | 'gemini' | 'echo'

export interface LLMConfig {
  provider: LLMProvider
  model: string
  openaiKeySet: boolean
  openrouterKeySet: boolean
  geminiKeySet: boolean
}

export interface ModelOption {
  id: string
  name: string
  free: boolean
}

export const useSettingsStore = defineStore('settings', () => {
  const orchestratorUrl = import.meta.env.VITE_ORCHESTRATOR_URL ?? 'http://localhost:8003'

  const provider = ref<LLMProvider>('openai')
  const model = ref<string>('')
  const openaiKeySet = ref<boolean>(false)
  const openrouterKeySet = ref<boolean>(false)
  const geminiKeySet = ref<boolean>(false)
  const loading = ref<boolean>(false)
  const error = ref<string | null>(null)
  const successMessage = ref<string | null>(null)

  const models = ref<ModelOption[]>([])
  const modelsLoading = ref<boolean>(false)

  async function fetchConfig(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const resp = await fetch(`${orchestratorUrl}/orchestrator/config/llm`)
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      provider.value = data.provider as LLMProvider
      model.value = data.model ?? ''
      openaiKeySet.value = data.openai_key_set ?? false
      openrouterKeySet.value = data.openrouter_key_set ?? false
      geminiKeySet.value = data.gemini_key_set ?? false
    } catch (err: unknown) {
      error.value = err instanceof Error ? err.message : 'Could not connect to orchestrator'
    } finally {
      loading.value = false
    }
  }

  async function fetchModels(p: LLMProvider): Promise<void> {
    if (p === 'echo') {
      models.value = [{ id: 'echo', name: 'Echo (test)', free: true }]
      return
    }
    modelsLoading.value = true
    try {
      const resp = await fetch(`${orchestratorUrl}/orchestrator/config/llm/models?provider=${p}`)
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      models.value = (data.models ?? []) as ModelOption[]
    } catch {
      models.value = []
    } finally {
      modelsLoading.value = false
    }
  }

  async function applyConfig(newProvider: LLMProvider, newModel: string): Promise<boolean> {
    loading.value = true
    error.value = null
    successMessage.value = null
    try {
      const resp = await fetch(`${orchestratorUrl}/orchestrator/config/llm`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: newProvider, model: newModel }),
      })
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}))
        throw new Error(body?.detail?.[0]?.msg ?? `HTTP ${resp.status}`)
      }
      const data = await resp.json()
      provider.value = data.provider as LLMProvider
      model.value = data.model ?? ''
      openaiKeySet.value = data.openai_key_set ?? false
      openrouterKeySet.value = data.openrouter_key_set ?? false
      geminiKeySet.value = data.gemini_key_set ?? false
      successMessage.value = 'Applied'
      return true
    } catch (err: unknown) {
      error.value = err instanceof Error ? err.message : 'Failed to apply config'
      return false
    } finally {
      loading.value = false
    }
  }

  return {
    provider, model, openaiKeySet, openrouterKeySet, geminiKeySet,
    loading, error, successMessage,
    models, modelsLoading,
    fetchConfig, fetchModels, applyConfig,
  }
})

