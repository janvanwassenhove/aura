import { defineStore } from 'pinia'
import { ref } from 'vue'

const IDENTITY_URL = import.meta.env.VITE_IDENTITY_URL ?? 'http://localhost:8006'
const CONNECTOR_URL = import.meta.env.VITE_CONNECTOR_URL ?? 'http://localhost:8004'

export type ConnectorStatus = 'ok' | 'mock' | 'unauthenticated' | 'unavailable' | 'unknown'

export type Provider = 'microsoft' | 'google' | 'github' | 'slack' | 'music'

export interface ProviderState {
  provider: Provider
  label: string
  status: ConnectorStatus
  /** Device Code: code to show user */
  deviceCode?: string
  /** Device Code: URL to visit */
  verificationUri?: string
  /** Whether an auth flow is currently in progress */
  authPending: boolean
  error?: string
  /** True when the service returned 503 "credentials not configured" — show setup wizard */
  needsSetup?: boolean
  /** U52: result of the last per-connector probe (Test button) */
  testResult?: string
  testing?: boolean
}

export const useConnectionsStore = defineStore('connections', () => {
  const connectorKey: Record<Provider, string> = {
    microsoft: 'm365',
    google: 'google',
    github: 'github',
    slack: 'slack',
    music: 'music',
  }

  const providers = ref<ProviderState[]>([
    { provider: 'microsoft', label: 'Microsoft M365',   status: 'unknown', authPending: false },
    { provider: 'google',    label: 'Google Workspace', status: 'unknown', authPending: false },
    { provider: 'github',    label: 'GitHub',           status: 'unknown', authPending: false },
    { provider: 'slack',     label: 'Slack',            status: 'unknown', authPending: false },
    { provider: 'music',     label: 'Spotify / Sonos',  status: 'unknown', authPending: false },
  ])

  const userId = ref<string>('default')
  const loading = ref<boolean>(false)

  // server-side flow_id returned by /start; used by /poll
  const _msPendingFlowId = ref<string | null>(null)
  const _googlePendingFlowId = ref<string | null>(null)
  const _githubPendingFlowId = ref<string | null>(null)

  function _ps(p: Provider): ProviderState {
    return providers.value.find(x => x.provider === p)!
  }

  async function _json(resp: Response): Promise<any> {
    try { return await resp.json() } catch { return {} }
  }

  // ------------------------------------------------------------------
  // Fetch connector health from connector-service
  // ------------------------------------------------------------------
  async function fetchStatus(): Promise<void> {
    loading.value = true
    try {
      const resp = await fetch(`${CONNECTOR_URL}/connector/health`)
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json() as { connectors?: Record<string, string> }
      const connectors = data.connectors ?? {}
      for (const ps of providers.value) {
        const key = connectorKey[ps.provider]
        if (key in connectors) ps.status = connectors[key] as ConnectorStatus
      }
    } catch {
      // connector-service offline — leave statuses as-is
    } finally {
      loading.value = false
    }
  }

  // Also check identity-service for stored tokens (covers GitHub/Slack/etc.)
  async function fetchIdentityStatus(): Promise<void> {
    for (const ps of providers.value) {
      if (ps.status !== 'unknown') continue // already known from connector-service
      if (ps.provider === 'music') continue // music status comes from connector health only
      try {
        const resp = await fetch(
          `${IDENTITY_URL}/identity/token/${userId.value}/${connectorKey[ps.provider]}`,
        )
        ps.status = resp.ok ? 'ok' : 'unauthenticated'
      } catch {
        ps.status = 'unknown'
      }
    }
  }

  async function refreshAllStatuses(): Promise<void> {
    // Reset to unknown so stale ok/unauthenticated values are replaced
    for (const ps of providers.value) ps.status = 'unknown'
    await Promise.all([fetchStatus(), fetchIdentityStatus()])
  }

  // ------------------------------------------------------------------
  // Microsoft — Device Code flow
  // ------------------------------------------------------------------
  async function startMicrosoftAuth(): Promise<void> {
    const ps = _ps('microsoft')
    ps.authPending = true
    ps.error = undefined
    ps.deviceCode = undefined
    ps.verificationUri = undefined
    _msPendingFlowId.value = null
    try {
      const resp = await fetch(`${IDENTITY_URL}/identity/auth/microsoft/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId.value }),
      })
      const data = await _json(resp)
      if (!resp.ok) {
        if (resp.status === 503) ps.needsSetup = true
        throw new Error(data.detail ?? `HTTP ${resp.status}`)
      }
      ps.needsSetup = false
      ps.deviceCode      = data.user_code as string
      ps.verificationUri = data.verification_uri as string
      _msPendingFlowId.value = data.flow_id as string   // server-side handle
      // authPending stays true — user still needs to sign in and click Done
    } catch (err: unknown) {
      ps.error = err instanceof Error ? err.message : 'Failed to start Microsoft auth'
      ps.authPending = false
    }
  }

  async function pollMicrosoftAuth(): Promise<void> {
    const ps = _ps('microsoft')
    const flowId = _msPendingFlowId.value
    if (!flowId) {
      ps.error = 'No pending flow — click Connect again.'
      ps.authPending = false
      return
    }
    try {
      const resp = await fetch(`${IDENTITY_URL}/identity/auth/microsoft/poll`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ flow_id: flowId }),   // ← server looks up flow by ID
      })
      const data = await _json(resp)
      if (!resp.ok) {
        const msg = data.detail ?? `HTTP ${resp.status}`
        throw new Error(resp.status === 408 ? `Code expired — ${msg}` : msg)
      }
      ps.status = 'ok'
      ps.deviceCode = undefined
      ps.verificationUri = undefined
      _msPendingFlowId.value = null
    } catch (err: unknown) {
      ps.error = err instanceof Error ? err.message : 'Authentication failed'
    } finally {
      ps.authPending = false
    }
  }

  function cancelMicrosoftAuth(): void {
    const ps = _ps('microsoft')
    ps.authPending = false
    ps.deviceCode = undefined
    ps.verificationUri = undefined
    _msPendingFlowId.value = null
  }

  // ------------------------------------------------------------------
  // Google — Device Code flow
  // ------------------------------------------------------------------
  async function startGoogleAuth(): Promise<void> {
    const ps = _ps('google')
    ps.authPending = true
    ps.error = undefined
    ps.deviceCode = undefined
    ps.verificationUri = undefined
    _googlePendingFlowId.value = null
    try {
      const resp = await fetch(`${IDENTITY_URL}/identity/auth/google/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId.value }),
      })
      const data = await _json(resp)
      if (!resp.ok) {
        if (resp.status === 503) ps.needsSetup = true
        throw new Error(data.detail ?? `HTTP ${resp.status}`)
      }
      ps.needsSetup = false
      ps.deviceCode = data.user_code as string
      ps.verificationUri = data.verification_url as string
      _googlePendingFlowId.value = data.flow_id as string
      // authPending stays true — user still needs to sign in and click Done
    } catch (err: unknown) {
      ps.error = err instanceof Error ? err.message : 'Failed to start Google auth'
      ps.authPending = false
    }
  }

  async function pollGoogleAuth(): Promise<void> {
    const ps = _ps('google')
    const flowId = _googlePendingFlowId.value
    if (!flowId) {
      ps.error = 'No pending flow — click Connect again.'
      ps.authPending = false
      return
    }
    try {
      const resp = await fetch(`${IDENTITY_URL}/identity/auth/google/poll`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ flow_id: flowId }),
      })
      const data = await _json(resp)
      if (resp.status === 202) {
        // Still pending — user hasn't signed in yet
        ps.error = 'Waiting for sign-in… Try again in a few seconds.'
        return
      }
      if (!resp.ok) {
        const msg = data.detail ?? `HTTP ${resp.status}`
        throw new Error(resp.status === 408 ? `Code expired — ${msg}` : msg)
      }
      ps.status = 'ok'
      ps.deviceCode = undefined
      ps.verificationUri = undefined
      _googlePendingFlowId.value = null
    } catch (err: unknown) {
      ps.error = err instanceof Error ? err.message : 'Authentication failed'
    } finally {
      ps.authPending = false
    }
  }

  function cancelGoogleAuth(): void {
    const ps = _ps('google')
    ps.authPending = false
    ps.deviceCode = undefined
    ps.verificationUri = undefined
    _googlePendingFlowId.value = null
  }

  // ------------------------------------------------------------------
  // GitHub — Device Code flow
  // ------------------------------------------------------------------
  async function startGitHubAuth(): Promise<void> {
    const ps = _ps('github')
    ps.authPending = true
    ps.error = undefined
    ps.deviceCode = undefined
    ps.verificationUri = undefined
    _githubPendingFlowId.value = null
    try {
      const resp = await fetch(`${IDENTITY_URL}/identity/auth/github/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId.value }),
      })
      const data = await _json(resp)
      if (!resp.ok) {
        if (resp.status === 503) ps.needsSetup = true
        throw new Error(data.detail ?? `HTTP ${resp.status}`)
      }
      ps.needsSetup = false
      ps.deviceCode = data.user_code as string
      ps.verificationUri = data.verification_uri as string
      _githubPendingFlowId.value = data.flow_id as string
    } catch (err: unknown) {
      ps.error = err instanceof Error ? err.message : 'Failed to start GitHub auth'
      ps.authPending = false
    }
  }

  async function pollGitHubAuth(): Promise<void> {
    const ps = _ps('github')
    const flowId = _githubPendingFlowId.value
    if (!flowId) {
      ps.error = 'No pending flow — click Connect again.'
      ps.authPending = false
      return
    }
    try {
      const resp = await fetch(`${IDENTITY_URL}/identity/auth/github/poll`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ flow_id: flowId }),
      })
      const data = await _json(resp)
      if (resp.status === 202) {
        ps.error = 'Waiting for sign-in… Try again in a few seconds.'
        return
      }
      if (!resp.ok) {
        const msg = data.detail ?? `HTTP ${resp.status}`
        throw new Error(resp.status === 408 ? `Code expired — ${msg}` : msg)
      }
      ps.status = 'ok'
      ps.deviceCode = undefined
      ps.verificationUri = undefined
      _githubPendingFlowId.value = null
    } catch (err: unknown) {
      ps.error = err instanceof Error ? err.message : 'Authentication failed'
    } finally {
      ps.authPending = false
    }
  }

  function cancelGitHubAuth(): void {
    const ps = _ps('github')
    ps.authPending = false
    ps.deviceCode = undefined
    ps.verificationUri = undefined
    _githubPendingFlowId.value = null
  }

  // ------------------------------------------------------------------
  // GitHub / Slack — simple API token
  // ------------------------------------------------------------------
  async function saveToken(provider: 'github' | 'slack', token: string): Promise<void> {
    const ps = _ps(provider)
    ps.authPending = true
    ps.error = undefined
    try {
      const resp = await fetch(
        `${IDENTITY_URL}/identity/token/${userId.value}/${provider}`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ access_token: token }),
        },
      )
      const data = await _json(resp)
      if (!resp.ok) throw new Error(data.detail ?? `HTTP ${resp.status}`)
      ps.status = 'ok'
    } catch (err: unknown) {
      ps.error = err instanceof Error ? err.message : 'Failed to save token'
    } finally {
      ps.authPending = false
    }
  }

  // ------------------------------------------------------------------
  // Revoke
  // ------------------------------------------------------------------
  async function disconnect(provider: Provider): Promise<void> {
    const ps = _ps(provider)
    ps.error = undefined
    try {
      const resp = await fetch(
        `${IDENTITY_URL}/identity/token/${userId.value}/${connectorKey[provider]}`,
        { method: 'DELETE' },
      )
      if (!resp.ok && resp.status !== 404) throw new Error(`HTTP ${resp.status}`)
      ps.status = 'unauthenticated'
    } catch (err: unknown) {
      ps.error = err instanceof Error ? err.message : 'Disconnect failed'
    }
  }

  // U52: one cheap real call per connector so the owner can verify a
  // connection actually works instead of trusting a green badge.
  async function testProvider(p: Provider): Promise<void> {
    const ps = _ps(p)
    ps.testing = true
    ps.testResult = undefined
    try {
      const resp = await fetch(`${CONNECTOR_URL}/connector/test/${connectorKey[p]}`, { method: 'POST' })
      const data = await _json(resp)
      ps.testResult = String(data.detail ?? (resp.ok ? 'ok' : `HTTP ${resp.status}`))
    } catch {
      ps.testResult = 'connector-service unreachable'
    } finally {
      ps.testing = false
    }
  }

  return {
    providers,
    userId,
    loading,
    testProvider,
    refreshAllStatuses,
    startMicrosoftAuth,
    pollMicrosoftAuth,
    cancelMicrosoftAuth,
    startGoogleAuth,
    pollGoogleAuth,
    cancelGoogleAuth,
    startGitHubAuth,
    pollGitHubAuth,
    cancelGitHubAuth,
    saveToken,
    disconnect,
  }
})
