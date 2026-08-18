<template>
  <main class="d2-main modes">
    <div class="modes-inner">
      <h2>Modes &amp; boundaries</h2>
      <p class="lead">
        What he may do, per mode. <strong>Allows</strong> runs without asking,
        <strong>Asks</strong> stops for your approval, <strong>Blocked</strong> means he
        refuses even if told to. Changing a row takes effect immediately.
      </p>

      <div class="mode-tabs">
        <button
          v-for="m in UI_MODES" :key="m"
          class="mode-tab" :class="{ active: editMode === m }"
          @click="editMode = m"
        >{{ MODE_META[m].label }}{{ m === modeStore.mode ? ' · active' : '' }}</button>
      </div>

      <section class="d2-card policy-card">
        <div v-for="g in groups" :key="g.id" class="policy-row">
          <div class="policy-text">
            <div class="policy-group">
              {{ g.label }}
              <span v-if="g.source === 'override'" class="override-chip" title="You changed this row — reset returns it to the derived policy">yours</span>
            </div>
            <div class="policy-detail">{{ g.detail }}</div>
          </div>
          <div v-if="g.id === 'conversation'" class="policy-fixed">always — talking is not a tool</div>
          <div v-else class="policy-opts" role="group" :aria-label="`${g.label} policy`">
            <button
              v-for="o in STATES" :key="o"
              class="policy-opt" :class="{ [o]: g.state === o }"
              :title="OPT_HINTS[o]"
              @click="setState(g.id, o)"
            >{{ OPT_LABELS[o] }}</button>
            <button
              v-if="g.source === 'override'" class="policy-reset"
              title="Back to the derived policy" @click="setState(g.id, 'default')"
            >↺</button>
          </div>
        </div>
        <p v-if="!groups.length" class="policy-empty">The brain is not answering — boundaries load from the real policy, never from a copy.</p>
      </section>

      <section class="d2-card behaviour-card">
        <h3>How he behaves in {{ MODE_META[editMode].label }}</h3>
        <div class="behaviour-grid">
          <label class="behaviour-field">
            <span class="mono behaviour-k">persona</span>
            <select :value="behaviour?.persona" class="d2-field" aria-label="persona" @change="saveBehaviour('persona', $event)">
              <option v-for="c in personas" :key="c.id" :value="c.id">{{ c.name }}</option>
            </select>
          </label>
          <label class="behaviour-field">
            <span class="mono behaviour-k">voice</span>
            <select :value="behaviour?.voice" class="d2-field" aria-label="voice" @change="saveBehaviour('voice', $event)">
              <option v-for="v in TTS_VOICES" :key="v" :value="v">{{ v }}</option>
            </select>
          </label>
          <label class="behaviour-field">
            <span class="mono behaviour-k">speaks first</span>
            <select :value="behaviour?.speaks_first" class="d2-field" aria-label="speaks first" @change="saveBehaviour('speaks_first', $event)">
              <option value="yes">yes</option>
              <option value="only for reminders">only for reminders</option>
              <option value="never — cues only">never — cues only</option>
            </select>
          </label>
          <label class="behaviour-field">
            <span class="mono behaviour-k">memory writing</span>
            <select :value="behaviour?.memory_writing" class="d2-field" aria-label="memory writing" @change="saveBehaviour('memory_writing', $event)">
              <option value="on">on</option>
              <option value="off">off</option>
            </select>
          </label>
        </div>

        <!-- Apps he may drive — only when the mode does not block screen control -->
        <div v-if="screenAllowed" class="apps-sec">
          <h4>Apps he may drive</h4>
          <p class="apps-lead">Screen control is limited to this list. Anything else is refused, even when the mode allows it.</p>
          <div class="apps-chips">
            <span v-for="a in allowedApps" :key="a" class="app-chip">
              {{ a }}
              <button aria-label="Remove app" class="chip-x" @click="removeApp(a)">✕</button>
            </span>
            <input
              v-model="newApp" class="app-add" placeholder="+ Add an app"
              aria-label="Add an app" @keydown.enter.prevent="addApp"
            >
          </div>
          <p v-if="appsNote" class="apps-note">{{ appsNote }}</p>
        </div>

        <p class="quiet-note">Quiet hours compose with every mode: when on, he never speaks first — reminders arrive silently in the transcript instead.</p>

        <button v-if="editMode === 'present'" class="present-btn" @click="nav.go('present')">
          <Presentation :size="15" /> Build &amp; run a presentation
        </button>
      </section>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Presentation } from 'lucide-vue-next'
import { BRAIN_URL } from '../lib/endpoints'
import { MODE_META, useModeStore, type PolicyState, type UiMode } from '../stores/modeStore'
import { useNavStore } from '../stores/navStore'

const modeStore = useModeStore()
const nav = useNavStore()

const UI_MODES: UiMode[] = ['home', 'work', 'present']
const STATES: PolicyState[] = ['allows', 'asks', 'blocked']
const OPT_LABELS: Record<PolicyState, string> = { allows: 'Allow', asks: 'Ask', blocked: 'Blocked' }
const OPT_HINTS: Record<PolicyState, string> = {
  allows: 'Runs without asking',
  asks: 'Stops for your approval every time',
  blocked: 'Refused even if you ask for it',
}
const TTS_VOICES = ['alloy', 'ash', 'ballad', 'coral', 'echo', 'fable', 'onyx', 'nova', 'sage', 'shimmer', 'verse']

const editMode = ref<UiMode>(modeStore.mode)
const groups = computed(() => modeStore.groupsFor(editMode.value))
const behaviour = computed(() => modeStore.behaviourFor(editMode.value))
const screenAllowed = computed(() =>
  groups.value.find(g => g.id === 'screen control')?.state !== 'blocked')

async function setState(group: string, state: PolicyState | 'default'): Promise<void> {
  await modeStore.setGroupState(editMode.value, group, state)
}
async function saveBehaviour(key: string, e: Event): Promise<void> {
  await modeStore.setBehaviour(editMode.value, { [key]: (e.target as HTMLSelectElement).value })
}

// Personas for the behaviour select: the brain's character list.
const personas = ref<{ id: string; name: string }[]>([])
async function fetchPersonas(): Promise<void> {
  try {
    const r = await fetch(`${BRAIN_URL}/setup/characters`)
    const data = await r.json()
    personas.value = (data.characters ?? []).map((c: { id: string; display_name?: string }) => ({ id: c.id, name: c.display_name ?? c.id }))
  } catch { personas.value = [] }
  // The backend modes are personas too — offer them even without characters.
  for (const m of ['home', 'work', 'presentation']) {
    if (!personas.value.some(p => p.id === m)) personas.value.push({ id: m, name: m })
  }
}

// Apps he may drive — the launch_app allow-list (ALLOWED_APPS).
const allowedApps = ref<string[]>([])
const newApp = ref('')
const appsNote = ref('')
async function fetchApps(): Promise<void> {
  try {
    const r = await fetch(`${BRAIN_URL}/capabilities`)
    if (!r.ok) return
    const data = await r.json()
    allowedApps.value = data.allowed_apps ?? []
  } catch { /* brain offline */ }
}
function removeApp(name: string): void {
  allowedApps.value = allowedApps.value.filter(a => a !== name)
  appsNote.value = 'Removing an app needs its command too — manage the full list in Settings › Capabilities.'
}
function addApp(): void {
  const name = newApp.value.trim()
  if (!name) return
  appsNote.value = 'Adding an app needs its launch command — add it in Settings › Capabilities.'
  newApp.value = ''
}

onMounted(() => {
  modeStore.fetchPolicy()
  fetchPersonas()
  fetchApps()
})
</script>

<style scoped>
.modes-inner { max-width: 840px; }
.mono { font-family: var(--font-mono); }
.modes-inner h2 { margin: 0 0 3px; font-size: 19px; }
.lead { margin: 0 0 18px; font-size: 13.5px; color: var(--ink-2); max-width: 66ch; }

.mode-tabs { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
.mode-tab {
  padding: 7px 15px; border-radius: 9px; cursor: pointer; font-family: inherit;
  font-size: 13px; font-weight: 600; background: transparent;
  border: 1.5px solid var(--line); color: var(--ink-3);
}
.mode-tab.active { background: var(--surface); border-color: var(--line-strong); color: var(--ink); }

.policy-card { border-radius: 12px; overflow: hidden; margin-bottom: 16px; }
.policy-row { display: flex; align-items: center; gap: 14px; padding: 11px 16px; border-bottom: 1px solid var(--line); }
.policy-row:last-child { border-bottom: none; }
.policy-text { flex: 1; min-width: 0; }
.policy-group { font-size: 14px; font-weight: 600; display: flex; align-items: center; gap: 7px; }
.override-chip {
  font-size: 9.5px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em;
  padding: 1px 6px; border-radius: 999px; background: var(--accent-wash); color: var(--accent);
}
.policy-detail { font-size: 12px; color: var(--ink-3); margin-top: 1px; }
.policy-fixed { font-size: 12px; color: var(--ink-3); }
.policy-opts {
  display: flex; background: var(--sunken); border: 1px solid var(--line);
  border-radius: 8px; padding: 2px; gap: 1px; flex-shrink: 0; align-items: center;
}
.policy-opt {
  padding: 5px 12px; border: none; border-radius: 6px; cursor: pointer;
  font-family: inherit; font-size: 12px; font-weight: 600;
  background: transparent; color: var(--ink-3);
}
.policy-opt.allows { background: var(--ok); color: #fff; }
.policy-opt.asks { background: var(--warn); color: #fff; }
.policy-opt.blocked { background: var(--danger); color: #fff; }
.policy-reset { border: none; background: none; color: var(--ink-3); cursor: pointer; padding: 2px 6px; font-size: 13px; }
.policy-reset:hover { color: var(--accent); }
.policy-empty { padding: 14px 16px; font-size: 13px; color: var(--ink-3); }

.behaviour-card { padding: 16px 18px; border-radius: 12px; }
.behaviour-card h3 { margin: 0 0 12px; font-size: 14px; }
.behaviour-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }
.behaviour-field { display: flex; flex-direction: column; gap: 5px; }
.behaviour-k {
  font-size: 10px; font-weight: 700; letter-spacing: 0.1em;
  text-transform: uppercase; color: var(--ink-3);
}

.apps-sec { margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--line); }
.apps-sec h4 { margin: 0 0 4px; font-size: 13px; }
.apps-lead { margin: 0 0 9px; font-size: 12.5px; color: var(--ink-2); }
.apps-chips { display: flex; flex-wrap: wrap; gap: 7px; }
.app-chip {
  display: inline-flex; align-items: center; gap: 7px; font-size: 12.5px;
  padding: 5px 11px; border-radius: 999px; background: var(--surface-2);
  border: 1px solid var(--line-strong);
}
.chip-x { background: none; border: none; color: var(--ink-3); cursor: pointer; padding: 0; font-size: 12px; }
.chip-x:hover { color: var(--danger); }
.app-add {
  padding: 5px 11px; border-radius: 999px; background: transparent;
  border: 1px dashed var(--line-strong); color: var(--ink-2);
  font-size: 12.5px; font-weight: 600; font-family: inherit; outline: none; width: 110px;
}
.apps-note { margin: 8px 0 0; font-size: 12px; color: var(--ink-3); }

.quiet-note { margin: 14px 0 0; font-size: 12.5px; color: var(--ink-3); }
.present-btn {
  margin-top: 14px; display: inline-flex; align-items: center; gap: 8px;
  padding: 9px 16px; border-radius: 10px; background: var(--present); color: #fff;
  border: none; font-size: 13px; font-weight: 700; cursor: pointer; font-family: inherit;
}
</style>
