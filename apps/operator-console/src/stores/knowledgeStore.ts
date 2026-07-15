import { defineStore } from 'pinia'
import { ref } from 'vue'

// The knowledge API is served by the brain (same origin as orchestrator after U11).
const BRAIN_URL =
  import.meta.env.VITE_BRAIN_URL ??
  import.meta.env.VITE_ORCHESTRATOR_URL ??
  'http://localhost:8000'

export interface KnowledgePerson {
  person_id: string
  display_name: string
  role: string
  description?: string
  created_at?: string
}

export interface KnowledgeFact {
  fact_id: string
  person_id: string
  key: string
  value: string
  source: string
  created_at?: string
}

export interface KnowledgeSignal {
  signal_id: string
  person_id: string
  kind: string
  value: string
  confidence: number
  evidence_count: number
  last_seen?: string
}

export interface PersonSkillRef {
  name: string
  description: string
  enabled: boolean
}

export interface PersonDetail {
  person: KnowledgePerson
  facts: KnowledgeFact[]
  signals: KnowledgeSignal[]
  /** U63: skills scoped to this person (their way of working). */
  skills?: PersonSkillRef[]
}

export const useKnowledgeStore = defineStore('knowledge', () => {
  const people = ref<KnowledgePerson[]>([])
  const detail = ref<PersonDetail | null>(null)
  const tier = ref<string>('benign')
  const omkLoaded = ref(false)
  const locked = ref(false)
  const brainError = ref(false)  // U98: /people 5xx → brain needs a restart
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function _request(path: string, init?: RequestInit): Promise<Response | null> {
    error.value = null
    try {
      const resp = await fetch(`${BRAIN_URL}/knowledge${path}`, init)
      if (resp.status === 403) {
        // Sensitive tier gate: the store is encrypted and currently locked.
        locked.value = true
        error.value = 'Knowledge is locked. Restart the brain with KNOWLEDGE_PASSPHRASE to unlock.'
        return null
      }
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}))
        error.value = body.detail ?? `Request failed (${resp.status})`
        if (resp.status >= 500) brainError.value = true
        return null
      }
      locked.value = false
      return resp
    } catch {
      error.value = 'Could not reach the brain.'
      return null
    }
  }

  async function fetchTier(): Promise<void> {
    const resp = await _request('/tier')
    if (!resp) return
    const data = await resp.json()
    tier.value = data.tier
    omkLoaded.value = data.omk_loaded
  }

  async function fetchPeople(): Promise<void> {
    loading.value = true
    brainError.value = false
    try {
      const resp = await _request('/people')
      if (resp) { people.value = await resp.json(); return }
    } catch { brainError.value = true }
    finally { loading.value = false }
  }

  async function inspectPerson(personId: string): Promise<void> {
    loading.value = true
    try {
      const resp = await _request(`/people/${encodeURIComponent(personId)}`)
      if (resp) detail.value = await resp.json()
    } finally {
      loading.value = false
    }
  }

  async function upsertPerson(personId: string, displayName: string, role: string): Promise<boolean> {
    const resp = await _request(`/people/${encodeURIComponent(personId)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ display_name: displayName, role }),
    })
    if (resp) await fetchPeople()
    return resp !== null
  }

  // U63: owner-written portrait of the person (merged server-side — name and
  // role are untouched).
  async function saveDescription(personId: string, description: string): Promise<boolean> {
    const resp = await _request(`/people/${encodeURIComponent(personId)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ description }),
    })
    if (resp && detail.value?.person.person_id === personId) await inspectPerson(personId)
    return resp !== null
  }

  async function addFact(personId: string, key: string, value: string): Promise<boolean> {
    const resp = await _request(`/people/${encodeURIComponent(personId)}/facts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key, value }),
    })
    if (resp) await inspectPerson(personId)
    return resp !== null
  }

  async function updateFact(personId: string, factId: string, key: string, value: string): Promise<boolean> {
    // No update endpoint — replace: add the new fact, then delete the old one.
    const added = await addFact(personId, key, value)
    if (added) await deleteFact(factId, personId)
    return added
  }

  async function renamePerson(personId: string, displayName: string, role: string): Promise<boolean> {
    const ok = await upsertPerson(personId, displayName, role)
    if (ok && detail.value?.person.person_id === personId) {
      detail.value.person.display_name = displayName
      detail.value.person.role = role
    }
    return ok
  }

  async function deleteFact(factId: string, personId: string): Promise<boolean> {
    // Destructive — the brain requires a phone step-up when encryption is active (ADR-008 §9).
    const resp = await _request(`/facts/${encodeURIComponent(factId)}`, { method: 'DELETE' })
    if (resp) await inspectPerson(personId)
    return resp !== null
  }

  async function forgetPerson(personId: string): Promise<boolean> {
    // Right-to-be-forgotten — step-up required when encryption is active (ADR-008 §9).
    const resp = await _request(`/people/${encodeURIComponent(personId)}`, { method: 'DELETE' })
    if (resp) {
      if (detail.value?.person.person_id === personId) detail.value = null
      await fetchPeople()
    }
    return resp !== null
  }

  async function setConsent(personId: string, scope: string): Promise<boolean> {
    const resp = await _request(`/people/${encodeURIComponent(personId)}/consent`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ granted_by: 'owner', scope }),
    })
    return resp !== null
  }

  async function lock(): Promise<void> {
    const resp = await _request('/lock', { method: 'POST' })
    if (resp) {
      tier.value = 'benign'
      locked.value = omkLoaded.value // encrypted store → now inaccessible
    }
  }

  // ── In-app secure enable (U34-slice) + face recognition ──

  const recognitionEnabled = ref<boolean | null>(null)

  async function fetchRecognition(): Promise<void> {
    try {
      const resp = await fetch(`${BRAIN_URL}/recognition/status`)
      recognitionEnabled.value = resp.ok ? (await resp.json()).enabled === true : false
    } catch {
      recognitionEnabled.value = false
    }
  }

  async function secure(passphrase: string, remember: boolean): Promise<boolean> {
    error.value = null
    try {
      const resp = await fetch(`${BRAIN_URL}/setup/secure`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ passphrase, remember }),
      })
      const body = await resp.json().catch(() => ({}))
      if (!resp.ok) {
        error.value = body.error ?? `Securing failed (${resp.status})`
        return false
      }
      await fetchTier()
      await fetchRecognition()
      return true
    } catch {
      error.value = 'Could not reach the brain.'
      return false
    }
  }

  // ── Unknown-visitor sightings (U36f) ──

  const sightings = ref<{ sighting_id: string; first_seen: number; last_seen: number; count: number }[]>([])

  async function fetchSightings(): Promise<void> {
    try {
      const resp = await fetch(`${BRAIN_URL}/recognition/sightings`)
      sightings.value = resp.ok ? (await resp.json()).sightings ?? [] : []
    } catch {
      sightings.value = []
    }
  }

  function sightingImageUrl(id: string): string {
    return `${BRAIN_URL}/recognition/sightings/${id}/image?t=${Date.now()}`
  }

  async function tagSighting(sightingId: string, personId: string): Promise<string> {
    try {
      const resp = await fetch(`${BRAIN_URL}/recognition/sightings/${sightingId}/tag`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ person_id: personId }),
      })
      const body = await resp.json().catch(() => ({}))
      if (resp.ok) {
        await fetchSightings()
        return `Tagged as ${body.tagged} — recognition improved.`
      }
      return body.error ?? `Tagging failed (${resp.status})`
    } catch {
      return 'Could not reach the brain.'
    }
  }

  async function dismissSighting(sightingId: string): Promise<void> {
    try {
      await fetch(`${BRAIN_URL}/recognition/sightings/${sightingId}`, { method: 'DELETE' })
    } catch { /* ignore */ }
    await fetchSightings()
  }

  async function teachFace(personId: string): Promise<string> {
    try {
      const resp = await fetch(`${BRAIN_URL}/recognition/enroll`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ person_id: personId }),
      })
      const body = await resp.json().catch(() => ({}))
      return resp.ok
        ? `Face learned — the robot now recognizes ${body.enrolled}.`
        : (body.error ?? `Enrollment failed (${resp.status})`)
    } catch {
      return 'Could not reach the brain.'
    }
  }

  function clearDetail() {
    detail.value = null
  }

  function $reset() {
    people.value = []
    detail.value = null
    tier.value = 'benign'
    omkLoaded.value = false
    locked.value = false
    loading.value = false
    error.value = null
  }

  return {
    people, detail, tier, omkLoaded, locked, brainError, loading, error, recognitionEnabled,
    sightings,
    fetchTier, fetchPeople, inspectPerson, upsertPerson, saveDescription,
    addFact, updateFact, deleteFact, renamePerson, forgetPerson, setConsent, lock,
    fetchRecognition, secure, teachFace,
    fetchSightings, sightingImageUrl, tagSighting, dismissSighting,
    clearDetail, $reset,
  }
})
