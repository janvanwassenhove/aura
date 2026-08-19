import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { BRAIN_URL } from '../lib/endpoints'

/** U255: MCP servers the owner added, and the tools they brought.
 *
 * Adding is not activating. A server is registered, its tools are discovered
 * and shown, and only then can it be switched on — a stranger's tool list
 * should never quietly become part of what the assistant will do.
 */

export interface McpTool {
  name: string
  description: string
}

export interface McpServer {
  name: string
  url: string
  auth_type: 'none' | 'bearer' | 'api_key'
  enabled: boolean
  has_secret: boolean
  tools: McpTool[]
  tool_names: string[]
  last_error: string
}

export const useMcpStore = defineStore('mcp', () => {
  const servers = ref<McpServer[]>([])
  /** The policy group all added tools land in — named by the brain, not here. */
  const group = ref<string>('mcp tools')
  const enabledTools = ref<string[]>([])
  const busy = ref(false)
  const error = ref('')

  const toolCount = computed(() =>
    servers.value.reduce((n, s) => n + (s.enabled ? s.tools.length : 0), 0))

  function _apply(data: {
    servers?: McpServer[]; group?: string; enabled_tools?: string[]
    discovery_error?: string
  }): void {
    servers.value = data.servers ?? []
    group.value = data.group ?? group.value
    enabledTools.value = data.enabled_tools ?? []
    if (data.discovery_error) error.value = data.discovery_error
  }

  async function _send(path: string, init?: RequestInit): Promise<boolean> {
    busy.value = true
    error.value = ''
    try {
      const resp = await fetch(`${BRAIN_URL}${path}`, init)
      const body = await resp.json().catch(() => ({}))
      if (!resp.ok) {
        error.value = body?.error ?? `HTTP ${resp.status}`
        return false
      }
      _apply(body)
      return true
    } catch (err: unknown) {
      error.value = err instanceof Error ? err.message : 'could not reach the brain'
      return false
    } finally {
      busy.value = false
    }
  }

  const fetchServers = () => _send('/mcp/servers')

  const add = (name: string, url: string, authType: string, secret: string) =>
    _send('/mcp/servers', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, url, auth_type: authType, secret }),
    })

  const refresh = (name: string) =>
    _send(`/mcp/servers/${encodeURIComponent(name)}/refresh`, { method: 'POST' })

  /** Switching a server on changes what he may do, so the policy — which the
   *  capability chips render — has to be refetched in the same breath. */
  async function setEnabled(name: string, enabled: boolean): Promise<boolean> {
    const ok = await _send(`/mcp/servers/${encodeURIComponent(name)}/enabled`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled }),
    })
    if (ok) {
      const { useModeStore } = await import('./modeStore')
      await useModeStore().fetchPolicy()
    }
    return ok
  }

  async function remove(name: string): Promise<boolean> {
    const ok = await _send(`/mcp/servers/${encodeURIComponent(name)}`, { method: 'DELETE' })
    if (ok) {
      const { useModeStore } = await import('./modeStore')
      await useModeStore().fetchPolicy()
    }
    return ok
  }

  return {
    servers, group, enabledTools, busy, error, toolCount,
    fetchServers, add, refresh, setEnabled, remove,
  }
})
