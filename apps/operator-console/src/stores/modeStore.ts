import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { BRAIN_URL } from '../lib/endpoints'

/** D2: modes are a first-class capability boundary.
 *
 * `MODE_TOOL_MAP` has governed what the robot may do since U58; nothing in the
 * shipping console ever called the mode endpoint — mode surfaced as a 9px dot.
 * This store drives it: the header switcher POSTs the mode, and the capability
 * chip row renders what `/orchestrator/policy` derives from the real policy.
 * Never a hand-written rule.
 *
 * Vocabulary is fixed: Mode, and allows / asks / blocked — identical in the
 * UI, the config keys and the docs.
 */

export type UiMode = 'home' | 'work' | 'present'
export type PolicyState = 'allows' | 'asks' | 'blocked'

/** UI name ↔ backend name. The backend keeps `presentation` (plus silent_desk
 * and demo, reachable via API but not part of the three-way switch). */
export const TO_BACKEND: Record<UiMode, string> = { home: 'home', work: 'work', present: 'presentation' }
const TO_UI: Record<string, UiMode> = { home: 'home', work: 'work', presentation: 'present' }

export interface PolicyGroup {
  id: string
  label: string
  detail: string
  state: PolicyState
  source: 'default' | 'override'
  /** U254: the mode allows it, but no connected account can serve it. */
  unreachable?: boolean
  tools: string[]
}

export interface ModeBehaviour {
  persona: string
  voice: string
  speaks_first: string
  memory_writing: string
}

export const MODE_META: Record<UiMode, { label: string; hint: string }> = {
  home: { label: 'Home', hint: 'Family life — chat, music, reminders. Anything sensitive asks first; dev tools and the desktop are off limits.' },
  work: { label: 'Work', hint: 'Chief of staff — mail, calendar and todos are available. Dev tools and screen control ask every time.' },
  present: { label: 'Present', hint: 'On stage — speech, gestures and slides only. Everything else is refused, even if you ask.' },
}

export const useModeStore = defineStore('mode', () => {
  const mode = ref<UiMode>('home')
  const quiet = ref(localStorage.getItem('aura-quiet') === '1')
  const policy = ref<Record<string, { groups: PolicyGroup[]; behaviour: ModeBehaviour }>>({})
  const switching = ref(false)
  const error = ref<string | null>(null)

  const activeGroups = computed<PolicyGroup[]>(
    () => policy.value[TO_BACKEND[mode.value]]?.groups ?? [],
  )

  function groupsFor(ui: UiMode): PolicyGroup[] {
    return policy.value[TO_BACKEND[ui]]?.groups ?? []
  }
  function behaviourFor(ui: UiMode): ModeBehaviour | null {
    return policy.value[TO_BACKEND[ui]]?.behaviour ?? null
  }

  async function fetchPolicy(): Promise<void> {
    try {
      const resp = await fetch(`${BRAIN_URL}/orchestrator/policy`)
      if (!resp.ok) return
      const data = await resp.json()
      policy.value = data.modes ?? {}
      const ui = TO_UI[data.active_mode]
      if (ui) mode.value = ui
    } catch { /* brain offline — the header shows the last known state */ }
  }

  async function setMode(ui: UiMode): Promise<boolean> {
    const previous = mode.value
    mode.value = ui // optimistic — the switch must feel instant
    switching.value = true
    error.value = null
    try {
      const resp = await fetch(`${BRAIN_URL}/orchestrator/mode`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: TO_BACKEND[ui] }),
      })
      if (!resp.ok) {
        mode.value = previous
        const body = await resp.json().catch(() => ({}))
        error.value = body.error ?? `Mode change failed (${resp.status})`
        return false
      }
      return true
    } catch {
      mode.value = previous
      error.value = 'Could not reach the brain.'
      return false
    } finally {
      switching.value = false
    }
  }

  async function setGroupState(ui: UiMode, group: string, state: PolicyState | 'default'): Promise<boolean> {
    try {
      const resp = await fetch(`${BRAIN_URL}/orchestrator/policy`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: TO_BACKEND[ui], group, state }),
      })
      if (!resp.ok) return false
      await fetchPolicy() // re-derive — never patch the local copy by hand
      return true
    } catch { return false }
  }

  async function setBehaviour(ui: UiMode, behaviour: Partial<ModeBehaviour>): Promise<boolean> {
    try {
      const resp = await fetch(`${BRAIN_URL}/orchestrator/policy/behaviour`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: TO_BACKEND[ui], behaviour }),
      })
      if (!resp.ok) return false
      await fetchPolicy()
      return true
    } catch { return false }
  }

  function toggleQuiet(): void {
    quiet.value = !quiet.value
    try { localStorage.setItem('aura-quiet', quiet.value ? '1' : '0') } catch { /* session-only */ }
  }

  /** The sentence an approval card or tool badge shows: which rule caused
   * this — derived from the fetched policy, with a route to its source. */
  function ruleFor(toolName: string): { sentence: string; group: PolicyGroup | null } {
    const label = MODE_META[mode.value].label
    const group = activeGroups.value.find(g => g.tools.includes(toolName)) ?? null
    if (!group) return { sentence: `${toolName} always asks first, in every mode.`, group: null }
    if (group.state === 'asks') {
      const who = group.source === 'override' ? 'You set' : `${label} mode sets`
      return { sentence: `${who} ${group.id} to asks — every use needs your approval.`, group }
    }
    if (group.state === 'blocked') {
      return { sentence: `${label} mode blocks ${group.id} entirely.`, group }
    }
    return { sentence: `${label} mode allows ${group.id} without asking.`, group }
  }

  return {
    mode, quiet, policy, switching, error,
    activeGroups, groupsFor, behaviourFor, ruleFor,
    fetchPolicy, setMode, setGroupState, setBehaviour, toggleQuiet,
  }
})
