import { defineStore } from 'pinia'
import { ref } from 'vue'
import { BRAIN_URL } from '../lib/endpoints'

// Identity and connectors are routes on the brain, not separate hosts (ADR-007).
const IDENTITY_URL = BRAIN_URL
const CONNECTOR_URL = BRAIN_URL

// U254: `not_enabled` and `no_credentials` used to arrive as `unknown`, which
// is the one status an owner cannot act on: switching a connector on and
// registering an OAuth app are completely different jobs.
export type ConnectorStatus =
  'ok' | 'mock' | 'unauthenticated' | 'unavailable' | 'unknown'
  | 'not_enabled' | 'no_credentials'

export type Provider = 'calendar' | 'microsoft' | 'google' | 'github' | 'slack' | 'music'

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
  /** U254: what is true now, and what the owner would do next — from the brain,
   *  never composed here, so the console and the assistant cannot disagree. */
  detail?: string
  nextStep?: string
  /** Env vars still missing before a sign-in is even possible. */
  missing?: string[]
  /** What this connection would let him answer (mail, calendar, …). */
  domains?: string[]
  /** Switched on by the owner — independent of whether it is signed in. */
  enabled?: boolean
}

export const useConnectionsStore = defineStore('connections', () => {
  const connectorKey: Record<Provider, string> = {
    calendar: 'calendar_link',
    microsoft: 'm365',
    google: 'google',
    github: 'github',
    slack: 'slack',
    music: 'music',
  }

  const providers = ref<ProviderState[]>([
    // U298: first, because it is the one that needs nothing registered.
    { provider: 'calendar',  label: 'Calendar by link', status: 'unknown', authPending: false },
    { provider: 'microsoft', label: 'Microsoft M365',   status: 'unknown', authPending: false },
    { provider: 'google',    label: 'Google Workspace', status: 'unknown', authPending: false },
    { provider: 'github',    label: 'GitHub',           status: 'unknown', authPending: false },
    { provider: 'slack',     label: 'Slack',            status: 'unknown', authPending: false },
    { provider: 'music',     label: 'Spotify / Sonos',  status: 'unknown', authPending: false },
  ])

  const userId = ref<string>('default')
  const loading = ref<boolean>(false)
  /** U254: what the connections together let him answer right now. */
  const liveDomains = ref<string[]>([])

  /** Switch a connector on or off. The brain rebuilds and republishes what he
   *  may do, so this changes his capabilities in the same request — a setting
   *  that needs a restart reads as broken. */
  async function setEnabled(p: Provider, enabled: boolean): Promise<void> {
    const ps = _ps(p)
    ps.error = undefined
    try {
      const resp = await fetch(`${CONNECTOR_URL}/connector/enable/${connectorKey[p]}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      })
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      await refreshAllStatuses()
      // The brain has already republished what he may do; the chip row reads
      // that from the policy, so it has to be refetched in the same breath.
      // Without this the switch says "connected" while the header still says
      // "no account" — two truths on one screen, which is the bug this whole
      // unit is about.
      const { useModeStore } = await import('./modeStore')
      await useModeStore().fetchPolicy()
    } catch (err: unknown) {
      ps.error = err instanceof Error ? err.message : 'could not change it'
    }
  }

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
      const data = await resp.json() as {
        connectors?: Record<string, string>
        details?: {
          key: string; status: string; detail?: string; next_step?: string
          missing?: string[]; domains?: string[]; live?: boolean
        }[]
        live_domains?: string[]
      }
      const connectors = data.connectors ?? {}
      for (const ps of providers.value) {
        const key = connectorKey[ps.provider]
        if (key in connectors) ps.status = connectors[key] as ConnectorStatus
      }
      // U254: the rich per-connector answer, when the brain is new enough to
      // send it. An older brain still works — it just has less to say.
      liveDomains.value = data.live_domains ?? []
      for (const d of data.details ?? []) {
        const ps = providers.value.find(p => connectorKey[p.provider] === d.key)
        if (!ps) continue
        ps.status = d.status as ConnectorStatus
        ps.detail = d.detail
        ps.nextStep = d.next_step
        ps.missing = d.missing ?? []
        ps.domains = d.domains ?? []
        ps.enabled = d.status !== 'not_enabled'
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
      if (ps.enabled === false) continue    // U254: off — nothing to sign in to
      if (ps.provider === 'music') continue // music status comes from connector health only
      // U298: a pasted calendar link is not an account — there is no
      // token for identity to have, and asking would report it as "not
      // signed in" forever.
      if (ps.provider === 'calendar') continue
      try {
        // U221: ask whether it's connected, don't fetch the live access token.
        // This only ever read resp.ok — pulling a real Microsoft/Google/GitHub
        // token into the browser to colour a badge was gratuitous exposure.
        const resp = await fetch(
          `${IDENTITY_URL}/identity/status/${userId.value}/${connectorKey[ps.provider]}`,
        )
        const body = resp.ok ? await resp.json().catch(() => null) : null
        ps.status = body?.connected ? 'ok' : 'unauthenticated'
      } catch {
        ps.status = 'unknown'
      }
    }
  }

  async function refreshAllStatuses(): Promise<void> {
    // Reset to unknown so stale ok/unauthenticated values are replaced
    for (const ps of providers.value) ps.status = 'unknown'
    // SEQUENTIAL on purpose. fetchIdentityStatus() skips anything connector
    // health already answered ("already known from connector-service"), and
    // that skip only works if health has actually landed. Run in parallel and
    // identity overwrites the verdict: m365 is `mock` (running on canned data)
    // but was reported as `unauthenticated` (not connected) — two different
    // messages to the owner, decided by a race.
    await fetchStatus()
    await fetchIdentityStatus()
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
    liveDomains,
    setEnabled,
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
