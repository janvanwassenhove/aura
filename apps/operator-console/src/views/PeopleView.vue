<template>
  <main class="people">
    <!-- ═══ Who he knows: a real list you can search, add to and act on ═══ -->
    <aside class="people-rail">
      <div class="rail-top">
        <template v-if="isOwner">
          <button class="add-btn" @click="startAdd">+ Add a person</button>
          <input v-model="search" placeholder="Search people…" aria-label="Search people" class="search-input">
        </template>
        <p class="scope-note">{{ scopeNote }}</p>
      </div>

      <!-- Unknown visitors: tag or dismiss (owner only) -->
      <div v-if="isOwner && knowledge.sightings.length" class="visitors">
        <div class="visitors-head">
          <span class="visitors-title">Unknown visitors</span>
          <span class="mono visitors-count">{{ knowledge.sightings.length }}</span>
        </div>
        <div v-for="v in knowledge.sightings.slice(0, 3)" :key="v.sighting_id" class="visitor">
          <img :src="knowledge.sightingImageUrl(v.sighting_id)" alt="Unknown visitor" class="visitor-thumb">
          <span class="visitor-seen">Seen {{ v.count }}× · {{ fmtAgo(v.last_seen) }}</span>
          <div class="visitor-actions">
            <select :aria-label="'Tag as person'" class="visitor-select" @change="tagVisitor(v.sighting_id, $event)">
              <option value="">Tag as…</option>
              <option v-for="p in knowledge.people" :key="p.person_id" :value="p.person_id">{{ p.display_name }}</option>
            </select>
            <button class="visitor-dismiss" title="Not a person / never mind" @click="knowledge.dismissSighting(v.sighting_id)">Dismiss</button>
          </div>
        </div>
        <p class="visitors-note">Tagging moves the face onto that person — recognition keeps working and the guest profile is absorbed.</p>
      </div>

      <div class="people-list">
        <button
          v-for="p in visiblePeople" :key="p.person_id"
          class="person-row" :class="{ active: p.person_id === selectedId }"
          :title="`Open ${p.display_name}`" @click="select(p.person_id)"
        >
          <span class="person-avatar" :class="{ noface: !hasFace(p.person_id) }">{{ initials(p.display_name) }}</span>
          <span class="person-text">
            <span class="person-name">{{ p.display_name }}</span>
            <span class="person-sub">{{ p.role }} · {{ hasFace(p.person_id) ? 'face known' : 'no face yet' }}</span>
          </span>
          <span class="face-dot" :class="{ on: hasFace(p.person_id) }"
                :title="hasFace(p.person_id) ? 'He can recognise this face' : 'No face taught yet — he will ask who it is'" />
        </button>
      </div>
    </aside>

    <!-- ═══ The person ═══ -->
    <div class="person-main">
      <!-- add-person inline form -->
      <div v-if="adding" class="add-form">
        <h3 class="d2-h3">New person</h3>
        <div class="add-row">
          <input v-model="addName" class="d2-field" placeholder="Name" aria-label="Name">
          <select v-model="addRole" class="d2-field" aria-label="Role">
            <option>family</option><option>kid</option><option>guest</option><option>owner</option>
          </select>
          <button class="d2-primary-btn" :disabled="!addName.trim()" @click="createPerson">Add</button>
          <button class="d2-ghost-btn" @click="adding = false">Cancel</button>
        </div>
      </div>

      <template v-if="detail">
        <div class="person-head">
          <span class="head-avatar">{{ initials(detail.person.display_name) }}</span>
          <div class="head-text">
            <h2>{{ detail.person.display_name }}</h2>
            <!-- Built from the data — a hand-written count always drifts. -->
            <span class="head-sub">{{ personSub }}</span>
          </div>
          <span class="head-spacer" />
          <label v-if="isOwner" class="role-label">
            Role
            <select :value="detail.person.role" class="d2-field role-select" aria-label="Role" @change="changeRole">
              <option>owner</option><option>family</option><option>kid</option><option>guest</option>
            </select>
          </label>
          <span v-else class="role-chip">Role: {{ detail.person.role }} · set by the owner</span>
        </div>

        <div class="person-actions">
          <button class="d2-ghost-btn" title="Take four photos so he recognises this person"
                  :disabled="teaching" @click="doTeachFace">{{ teaching ? 'Watching…' : 'Teach face' }}</button>
          <button class="d2-ghost-btn" title="Add something he should remember" @click="addingFact = !addingFact">+ Add a fact</button>
          <template v-if="isOwner">
            <button class="d2-ghost-btn" title="See this person's knowledge as a graph" @click="openGraph">Open graph</button>
            <label class="consent-label" title="What he may store about this person">
              Consent
              <select :value="consentValue" class="d2-field consent-select" aria-label="Consent scope" @change="changeConsent">
                <option value="full">full — remember everything</option>
                <option value="basic">basic — name and face only</option>
                <option value="none">none — remember nothing</option>
              </select>
            </label>
            <button class="d2-danger-btn forget-btn" title="Delete this person and everything he remembers about them"
                    @click="confirmForget">Forget this person</button>
          </template>
        </div>
        <p v-if="teachMsg" class="teach-msg">{{ teachMsg }}</p>

        <div v-if="addingFact" class="add-fact">
          <input v-model="factKey" class="d2-field fact-key" placeholder="key (e.g. coffee)" aria-label="Fact key">
          <input v-model="factValue" class="d2-field" placeholder="value — link with [[person]] or [[skill]]" aria-label="Fact value">
          <button class="d2-primary-btn" :disabled="!factKey.trim() || !factValue.trim()" @click="saveFact">Save</button>
        </div>

        <nav role="tablist" class="tabs">
          <button
            v-for="t in TABS" :key="t" role="tab"
            class="tab" :class="{ active: knowledge.personTab === t }"
            @click="knowledge.personTab = t"
          >{{ t }}</button>
        </nav>

        <!-- ── Profile ── -->
        <template v-if="knowledge.personTab === 'Profile'">
          <template v-if="snapshots.length">
            <h3 class="d2-h3">Recently seen</h3>
            <div class="snapshots">
              <figure v-for="s in snapshots" :key="s.snapshot_id" class="snapshot">
                <img :src="s.image" alt="Recognition snapshot" class="snapshot-img">
                <button
                  class="snapshot-x"
                  title="Not this person? It goes back to unknown visitors so you can tag the right one"
                  @click="wrongSnapshot(s.snapshot_id)"
                >✕</button>
                <figcaption class="mono snapshot-meta">{{ fmtSnapshot(s) }}</figcaption>
              </figure>
            </div>
            <p class="snapshots-note">Kept in memory only, wiped on restart. Hit ✕ on anything that isn't {{ detail.person.display_name }}.</p>
          </template>

          <h3 class="d2-h3">What he knows about {{ detail.person.display_name }}</h3>
          <div class="facts-grid">
            <div v-for="f in profileFacts" :key="f.fact_id" class="fact-card">
              <div class="fact-key">{{ f.key }}</div>
              <div class="fact-value">
                <!-- [[targets]] substituted INLINE — the sentence stays whole -->
                <WikiText :text="f.value" @open="openTarget" />
              </div>
              <div v-if="full" class="mono fact-src">{{ f.source }}</div>
              <button class="fact-x" title="Delete this fact" @click="knowledge.deleteFact(f.fact_id, detail.person.person_id)">✕</button>
            </div>
          </div>
          <p v-if="!profileFacts.length" class="empty-note">Nothing yet — add a fact above, or let him learn from conversations.</p>

          <template v-if="full && detail.signals.length">
            <h3 class="d2-h3">Observed signals</h3>
            <div class="facts-grid">
              <div v-for="s in detail.signals" :key="s.signal_id" class="fact-card">
                <div class="fact-key">{{ s.kind }}</div>
                <div class="fact-value">{{ s.value }}</div>
                <div class="mono fact-src">inferred · {{ s.confidence.toFixed(2) }} · seen {{ s.evidence_count }}×</div>
              </div>
            </div>
          </template>
        </template>

        <!-- ── Memory ── -->
        <template v-else-if="knowledge.personTab === 'Memory'">
          <h3 class="d2-h3">Memory</h3>
          <p class="tab-lead">Grown automatically from your conversations and injected into future turns. Edit or delete anything — it is your memory of you.</p>
          <template v-if="memoryText || memoryDraft">
            <textarea v-model="memoryDraft" rows="9" aria-label="Memory" class="memory-area" />
            <div class="memory-actions">
              <button class="d2-ghost-btn" @click="saveMemory">Save memory</button>
              <button class="d2-danger-btn" @click="clearMemory">Clear all memory</button>
            </div>
          </template>
          <div v-else class="empty-box">
            <div class="empty-title">Nothing remembered yet</div>
            <p class="empty-body">He writes here as he learns from conversations with {{ detail.person.display_name }}. You can also add something yourself.</p>
            <button class="d2-ghost-btn" @click="memoryDraft = ' '">Write the first note</button>
          </div>
        </template>

        <!-- ── Sources ── -->
        <template v-else-if="knowledge.personTab === 'Sources'">
          <h3 class="d2-h3">Sources</h3>
          <p class="tab-lead">Pages he may read to grow what he knows about {{ detail.person.display_name }}. Reading happens on this laptop; nothing is sent anywhere.</p>
          <p v-if="!sourceFacts.length" class="empty-note boxed">No sources yet — add one below and he will read it on your say-so.</p>
          <div class="source-chips">
            <span v-for="f in sourceFacts" :key="f.fact_id" class="source-chip">
              {{ f.value }}
              <button aria-label="Remove source" class="chip-x" @click="knowledge.deleteFact(f.fact_id, detail.person.person_id)">✕</button>
            </span>
          </div>
          <div class="source-add">
            <input v-model="newSource" class="d2-field source-input" placeholder="https://… blog, site or github" aria-label="Add a source">
            <button class="d2-ghost-btn" :disabled="!newSource.trim()" @click="addSource">Add source</button>
            <button class="d2-primary-btn" title="Read every source now and add what he finds"
                    :disabled="reading || !sourceFacts.length" @click="readSources">{{ reading ? 'Reading…' : 'Read them now' }}</button>
          </div>
          <p v-if="readResult" class="read-result">{{ readResult }}</p>
          <h3 class="d2-h3">Import &amp; export</h3>
          <div class="ie-row">
            <button class="d2-ghost-btn" title="Drop a ChatGPT or Claude conversations.json — mined locally for facts about this person" @click="pickImport">Import a chat export…</button>
            <input ref="importInput" type="file" accept=".json,application/json" class="hidden-input" @change="doImport">
            <button class="d2-ghost-btn" title="Download everything he knows as JSON" @click="doExport">Export the brain (JSON)</button>
          </div>
          <p v-if="importResult" class="read-result">{{ importResult }}</p>
          <p class="ie-note">The export is the honest counterpart to “it stays on this laptop” — you can always take it with you.</p>
        </template>

        <!-- ── Skills ── -->
        <template v-else>
          <h3 class="d2-h3">Things he has learned to do</h3>
          <div v-for="sk in detail.skills ?? []" :key="sk.name" class="skill-row">
            <div class="skill-text">
              <div class="skill-name">{{ sk.name }}</div>
              <div class="skill-when">{{ sk.description }}</div>
            </div>
            <button class="d2-ghost-btn" @click="nav.openSkills(sk.name)">Open</button>
          </div>
          <p v-if="!(detail.skills ?? []).length" class="empty-note">No skills bound to {{ detail.person.display_name }} yet — teach one from any conversation.</p>
        </template>
      </template>

      <p v-else-if="knowledge.error" class="empty-note">{{ knowledge.error }}</p>
      <p v-else class="empty-note">Pick a person on the left.</p>
    </div>

    <!-- ═══ Graph aside (Full density, wide windows) ═══ -->
    <aside v-if="full && detail" data-graph-aside class="graph-aside">
      <div class="graph-head">
        <span class="mono graph-label">knowledge graph</span>
        <span class="head-spacer" />
        <button class="graph-btn" title="Re-centre and re-layout" @click="graphRef?.reset()">Reset</button>
        <button class="graph-btn accent" title="Open the graph full screen" @click="openGraph">Expand</button>
      </div>
      <div class="graph-box">
        <KnowledgeGraph ref="graphRef" :detail="detail" :people-ids="peopleIds" @open-person="select" />
        <span class="mono graph-hint">drag · scroll to zoom</span>
      </div>
      <div class="mono retrieval-label">retrieval preview</div>
      <p class="mono retrieval">
        context for “{{ detail.person.person_id }}” · {{ modeStore.mode }}<br>
        facts {{ profileFacts.length }} · signals {{ detail.signals.length }}<br>
        skills {{ (detail.skills ?? []).length }} bound
      </p>
    </aside>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import KnowledgeGraph from '../components/canvas/KnowledgeGraph.vue'
import WikiText from '../components/WikiText.vue'
import { BRAIN_URL } from '../lib/endpoints'
import { useKnowledgeStore } from '../stores/knowledgeStore'
import { useModeStore } from '../stores/modeStore'
import { useNavStore } from '../stores/navStore'
import { usePrefsStore } from '../stores/prefsStore'

const knowledge = useKnowledgeStore()
const modeStore = useModeStore()
const nav = useNavStore()
const prefs = usePrefsStore()

const TABS = ['Profile', 'Memory', 'Sources', 'Skills'] as const
const full = computed(() => prefs.density === 'full')

// ── Owner scoping: only the owner sees everyone and can add ────────────────
const isOwner = computed(() => {
  if (!knowledge.people.length) return true
  const s = knowledge.speaker
  if (s === null) return true
  if (s === 'guest') return false
  return knowledge.people.find(p => p.person_id === s)?.role === 'owner'
})
const scopeNote = computed(() => {
  if (isOwner.value) return 'You are the owner — you see everyone he knows.'
  const me = knowledge.people.find(p => p.person_id === knowledge.speaker)
  return me
    ? `Signed in as ${me.display_name}. Only the owner can see or add other people.`
    : 'Guests are not remembered — nothing from this session is stored.'
})
const search = ref('')
const visiblePeople = computed(() => {
  let list = knowledge.people
  if (!isOwner.value) list = list.filter(p => p.person_id === knowledge.speaker)
  const q = search.value.trim().toLowerCase()
  if (q) list = list.filter(p => p.display_name.toLowerCase().includes(q) || p.person_id.includes(q))
  return list
})
const peopleIds = computed(() => knowledge.people.map(p => p.person_id))

// ── Selection ──────────────────────────────────────────────────────────────
const selectedId = computed(() => knowledge.selectedPerson)
const detail = computed(() => knowledge.detail)

function select(id: string): void {
  knowledge.selectedPerson = id
  knowledge.inspectPerson(id)
  loadSnapshots(id)
}
function initials(name: string): string { return name.slice(0, 2).toUpperCase() }
function hasFace(personId: string): boolean {
  return knowledge.recognitionEnabled && enrolled.value.includes(personId)
}
const enrolled = ref<string[]>([])
async function fetchEnrolled(): Promise<void> {
  try {
    const r = await fetch(`${BRAIN_URL}/recognition/status`)
    if (r.ok) enrolled.value = (await r.json()).enrolled ?? []
  } catch { /* recognition off */ }
}

onMounted(async () => {
  await knowledge.fetchPeople()
  knowledge.fetchSightings()
  fetchEnrolled()
  // [[wikilink]] requests from other views land here.
  const req = nav.knowledgeRequest
  const first = req?.personId ?? knowledge.selectedPerson ?? visiblePeople.value[0]?.person_id
  if (first) select(first)
})
watch(() => nav.knowledgeRequest, (r) => { if (r) select(r.personId) })

// The sub-line is DERIVED — a hand-written count always drifts.
const personSub = computed(() => {
  if (!detail.value) return ''
  const f = profileFacts.value.length
  const face = hasFace(detail.value.person.person_id) ? 'Face known' : 'No face taught yet'
  const enc = knowledge.omkLoaded ? 'encrypted on this laptop' : 'not yet encrypted'
  const mem = memoryText.value ? '1 memory note · ' : ''
  return `${face} · ${f} fact${f === 1 ? '' : 's'} · ${mem}${enc}`
})

// ── Facts ──────────────────────────────────────────────────────────────────
const profileFacts = computed(() =>
  (detail.value?.facts ?? []).filter(f => f.key !== 'memory' && !f.key.startsWith('source:')))
const sourceFacts = computed(() =>
  (detail.value?.facts ?? []).filter(f => f.key.startsWith('source:')))
const memoryText = computed(() =>
  (detail.value?.facts ?? []).find(f => f.key === 'memory')?.value ?? '')

const addingFact = ref(false)
const factKey = ref('')
const factValue = ref('')
async function saveFact(): Promise<void> {
  if (!detail.value) return
  const ok = await knowledge.addFact(detail.value.person.person_id, factKey.value.trim(), factValue.value.trim())
  if (ok) { factKey.value = ''; factValue.value = ''; addingFact.value = false }
}

function openTarget(target: string): void {
  if (knowledge.people.some(p => p.person_id === target)) select(target)
  else nav.openSkills(target)
}

// ── Role / consent / forget ────────────────────────────────────────────────
async function changeRole(e: Event): Promise<void> {
  if (!detail.value) return
  const role = (e.target as HTMLSelectElement).value
  await knowledge.renamePerson(detail.value.person.person_id, detail.value.person.display_name, role)
  await knowledge.inspectPerson(detail.value.person.person_id)
}
const consentValue = computed(() => {
  const c = (detail.value?.person as { consent?: string } | undefined)?.consent ?? 'full'
  return c.split(' ')[0]
})
async function changeConsent(e: Event): Promise<void> {
  if (!detail.value) return
  await knowledge.setConsent(detail.value.person.person_id, (e.target as HTMLSelectElement).value)
}
async function confirmForget(): Promise<void> {
  if (!detail.value) return
  const name = detail.value.person.display_name
  // Right-to-be-forgotten is destructive — the typed confirmation is the gate.
  if (!window.confirm(`Forget ${name}? This deletes their profile, facts, memory AND their face. There is no undo.`)) return
  await knowledge.forgetPerson(detail.value.person.person_id)
  knowledge.selectedPerson = null
  knowledge.clearDetail()
  await knowledge.fetchPeople()
}

// ── Face: teach + snapshots ────────────────────────────────────────────────
const teaching = ref(false)
const teachMsg = ref('')
async function doTeachFace(): Promise<void> {
  if (!detail.value) return
  teaching.value = true
  teachMsg.value = 'Look at the robot…'
  teachMsg.value = await knowledge.teachFace(detail.value.person.person_id)
  teaching.value = false
  fetchEnrolled()
}
const snapshots = ref<{ snapshot_id: string; seen_at: number; confidence: number; image: string }[]>([])
async function loadSnapshots(personId: string): Promise<void> {
  snapshots.value = await knowledge.fetchSnapshots(personId)
}
function fmtSnapshot(s: { seen_at: number; confidence: number }): string {
  return `${new Date(s.seen_at * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} · ${Math.round(s.confidence * 100)}%`
}
async function wrongSnapshot(id: string): Promise<void> {
  if (!detail.value) return
  await knowledge.flagSnapshotWrong(detail.value.person.person_id, id)
  loadSnapshots(detail.value.person.person_id)
  knowledge.fetchSightings()
}

// ── Unknown visitors ───────────────────────────────────────────────────────
function fmtAgo(ts: number): string {
  const mins = Math.round((Date.now() / 1000 - ts) / 60)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} min ago`
  return `${Math.round(mins / 60)}h ago`
}
async function tagVisitor(sightingId: string, e: Event): Promise<void> {
  const personId = (e.target as HTMLSelectElement).value
  if (!personId) return
  await knowledge.tagSighting(sightingId, personId)
  knowledge.fetchSightings()
  fetchEnrolled()
}

// ── Add person ─────────────────────────────────────────────────────────────
const adding = ref(false)
const addName = ref('')
const addRole = ref('family')
function startAdd(): void { adding.value = true }
async function createPerson(): Promise<void> {
  const id = addName.value.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-')
  const ok = await knowledge.upsertPerson(id, addName.value.trim(), addRole.value)
  if (ok) { adding.value = false; addName.value = ''; select(id) }
}

// ── Memory tab ─────────────────────────────────────────────────────────────
const memoryDraft = ref('')
watch(memoryText, (t) => { memoryDraft.value = t }, { immediate: true })
async function saveMemory(): Promise<void> {
  if (!detail.value) return
  await knowledge.addFact(detail.value.person.person_id, 'memory', memoryDraft.value.trim())
  await knowledge.inspectPerson(detail.value.person.person_id)
}
async function clearMemory(): Promise<void> {
  if (!detail.value) return
  const memFacts = (detail.value.facts ?? []).filter(f => f.key === 'memory')
  for (const f of memFacts) await knowledge.deleteFact(f.fact_id, detail.value.person.person_id)
  memoryDraft.value = ''
}

// ── Sources tab ────────────────────────────────────────────────────────────
const newSource = ref('')
const reading = ref(false)
const readResult = ref('')
async function addSource(): Promise<void> {
  if (!detail.value) return
  const url = newSource.value.trim()
  const kind = url.includes('github.com') ? 'github' : 'site'
  const ok = await knowledge.addFact(detail.value.person.person_id, `source:${kind}`, url)
  if (ok) newSource.value = ''
}
async function readSources(): Promise<void> {
  if (!detail.value) return
  reading.value = true
  readResult.value = ''
  const res = await knowledge.ingestSources(detail.value.person.person_id)
  reading.value = false
  readResult.value = res
    ? `Read ${res.read.length} source${res.read.length === 1 ? '' : 's'}, added ${res.added_count} fact${res.added_count === 1 ? '' : 's'}${res.skipped.length ? ` · skipped ${res.skipped.length} (${res.skipped.map(s => s.reason)[0]})` : ''}.`
    : (knowledge.error ?? 'Reading failed.')
}
const importInput = ref<HTMLInputElement | null>(null)
const importResult = ref('')
function pickImport(): void { importInput.value?.click() }
async function doImport(e: Event): Promise<void> {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file || !detail.value) return
  try {
    const json = JSON.parse(await file.text())
    const res = await knowledge.importChats(detail.value.person.person_id, json)
    importResult.value = res
      ? `Mined ${res.conversations} conversations — added ${res.added_count} fact${res.added_count === 1 ? '' : 's'}.`
      : (knowledge.error ?? 'Import failed.')
  } catch { importResult.value = 'That file is not valid JSON.' }
}
async function doExport(): Promise<void> {
  const data = await knowledge.exportBrain()
  if (!data) return
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = 'aura-brain-export.json'
  a.click()
  URL.revokeObjectURL(a.href)
}

// ── Graph ──────────────────────────────────────────────────────────────────
const graphRef = ref<InstanceType<typeof KnowledgeGraph> | null>(null)
function openGraph(): void { nav.go('graph') }
</script>

<style scoped>
.people { flex: 1; min-width: 0; display: flex; min-height: 0; }
.mono { font-family: var(--font-mono); }
.head-spacer { flex: 1; }

.people-rail {
  width: 214px; flex-shrink: 0; border-right: 1px solid var(--line);
  background: var(--surface); display: flex; flex-direction: column; min-height: 0;
}
.rail-top { padding: 12px 12px 8px; flex-shrink: 0; }
.add-btn {
  width: 100%; padding: 9px; border-radius: 10px; background: var(--accent);
  color: var(--on-accent); border: none; font-size: 13px; font-weight: 700;
  cursor: pointer; font-family: inherit;
}
.search-input {
  width: 100%; margin-top: 8px; padding: 7px 10px; background: var(--surface-2);
  border: 1px solid var(--line-strong); border-radius: 9px; color: var(--ink);
  font-size: 12.5px; outline: none; font-family: inherit; box-sizing: border-box;
}
.scope-note { margin: 8px 0 0; font-size: 11.5px; color: var(--ink-3); line-height: 1.45; }

.visitors {
  margin: 4px 8px 8px; padding: 9px 10px;
  border: 1px solid var(--warn); border-radius: 10px; background: var(--warn-wash);
}
.visitors-head { display: flex; align-items: center; gap: 7px; margin-bottom: 7px; }
.visitors-title { font-size: 11.5px; font-weight: 700; }
.visitors-count { font-size: 10px; color: var(--warn); }
.visitor { display: flex; align-items: center; gap: 7px; margin-bottom: 6px; flex-wrap: wrap; }
.visitor-thumb { width: 34px; height: 26px; border-radius: 6px; flex-shrink: 0; object-fit: cover; border: 1px solid var(--line); }
.visitor-seen { flex: 1; min-width: 0; font-size: 11px; color: var(--ink-2); line-height: 1.25; }
.visitor-actions { display: flex; gap: 5px; width: 100%; margin-bottom: 3px; }
.visitor-select {
  flex: 1; min-width: 0; background: var(--surface); border: 1px solid var(--line-strong);
  border-radius: 7px; color: var(--ink); padding: 4px 6px; font-size: 11px; font-family: inherit;
}
.visitor-dismiss {
  background: none; border: 1px solid var(--line-strong); border-radius: 7px;
  color: var(--ink-3); cursor: pointer; padding: 4px 7px; font-size: 11px; font-family: inherit;
}
.visitors-note { margin: 0; font-size: 10.5px; color: var(--ink-3); line-height: 1.4; }

.people-list { flex: 1; min-height: 0; overflow-y: auto; padding: 0 8px 10px; }
.person-row {
  display: flex; align-items: center; gap: 9px; width: 100%; padding: 8px 9px;
  margin-bottom: 2px; border: none; border-radius: 10px; cursor: pointer;
  font-family: inherit; background: transparent; color: var(--ink);
}
.person-row.active { background: var(--accent-wash); }
.person-avatar {
  width: 28px; height: 28px; border-radius: 50%; flex-shrink: 0;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 10.5px; font-weight: 700; background: var(--accent); color: var(--on-accent);
}
.person-avatar.noface { background: var(--sunken); color: var(--ink-3); }
.person-text { flex: 1; min-width: 0; text-align: left; line-height: 1.25; }
.person-name { display: block; font-size: 13px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.person-sub { display: block; font-size: 11px; color: var(--ink-3); }
.face-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; background: var(--line-strong); }
.face-dot.on { background: var(--ok); }

.person-main { flex: 1 1 auto; min-width: 320px; overflow-y: auto; padding: 18px 24px; }

.add-form { margin-bottom: 16px; padding: 13px 15px; border: 1.5px solid var(--accent); border-radius: 12px; background: var(--surface); }
.add-row { display: flex; gap: 8px; flex-wrap: wrap; }
.add-row .d2-field { flex: 1; min-width: 140px; width: auto; }

.person-head { display: flex; align-items: center; gap: 12px; margin-bottom: 6px; flex-wrap: wrap; }
.head-avatar {
  width: 44px; height: 44px; border-radius: 50%;
  display: inline-flex; align-items: center; justify-content: center;
  background: var(--accent); color: var(--on-accent); font-size: 15px; font-weight: 700;
}
.head-text { line-height: 1.25; }
.head-text h2 { margin: 0; font-size: 19px; }
.head-sub { font-size: 12px; color: var(--ink-3); }
.role-label { display: flex; align-items: center; gap: 7px; font-size: 12.5px; color: var(--ink-3); }
.role-select, .consent-select { width: auto; padding: 6px 9px; font-size: 12.5px; }
.role-chip {
  display: inline-flex; align-items: center; gap: 6px; font-size: 11.5px; font-weight: 600;
  color: var(--ink-3); border: 1px solid var(--line-strong); border-radius: 999px; padding: 3px 10px;
}

.person-actions { display: flex; gap: 7px; flex-wrap: wrap; margin-bottom: 18px; align-items: center; }
.consent-label { display: inline-flex; align-items: center; gap: 7px; font-size: 12.5px; color: var(--ink-3); }
.forget-btn { margin-left: auto; }
.teach-msg { margin: -10px 0 12px; font-size: 12.5px; color: var(--ink-2); }

.add-fact { display: flex; gap: 8px; margin-bottom: 14px; flex-wrap: wrap; }
.fact-key { max-width: 160px; }
.add-fact .d2-field { flex: 1; min-width: 120px; width: auto; }

.tabs { display: flex; gap: 2px; margin: 0 0 16px; border-bottom: 1px solid var(--line); }
.tab {
  background: none; border: none; border-bottom: 2px solid transparent;
  padding: 8px 15px; font-size: 13px; color: var(--ink-3);
  cursor: pointer; font-family: inherit;
}
.tab.active { border-bottom-color: var(--accent); font-weight: 600; color: var(--accent); }

.snapshots { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
.snapshot { position: relative; margin: 0; width: 84px; }
.snapshot-img { width: 84px; height: 64px; border-radius: 9px; object-fit: cover; border: 1px solid var(--line); }
.snapshot-x {
  position: absolute; top: -5px; right: -5px; width: 19px; height: 19px;
  border-radius: 50%; display: inline-flex; align-items: center; justify-content: center;
  background: var(--surface); border: 1px solid var(--line-strong); color: var(--ink-3);
  font-size: 11px; cursor: pointer; padding: 0;
}
.snapshot-x:hover { color: var(--danger); border-color: var(--danger); }
.snapshot-meta { font-size: 9.5px; color: var(--ink-3); margin-top: 4px; text-align: center; }
.snapshots-note { margin: 0 0 20px; font-size: 12px; color: var(--ink-3); }

.facts-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(min(210px, 100%), 1fr));
  gap: 9px; margin-bottom: 20px;
}
.fact-card { position: relative; background: var(--surface); border: 1px solid var(--line); border-radius: 11px; padding: 10px 13px; }
.fact-key {
  font-size: 10.5px; font-weight: 700; letter-spacing: 0.06em;
  text-transform: uppercase; color: var(--accent); margin-bottom: 3px;
}
.fact-value { font-size: 13px; color: var(--ink-2); }
.fact-src { font-size: 10px; color: var(--ink-3); margin-top: 5px; }
.fact-x {
  position: absolute; top: 7px; right: 9px; background: none; border: none;
  color: var(--ink-3); cursor: pointer; font-size: 11px; padding: 0; opacity: 0;
}
.fact-card:hover .fact-x { opacity: 1; }
.fact-x:hover { color: var(--danger); }

.empty-note { font-size: 13px; color: var(--ink-3); }
.empty-note.boxed {
  margin: 0 0 12px; padding: 11px 14px; border: 1.5px dashed var(--line-strong);
  border-radius: 11px; background: var(--surface); max-width: 60ch;
}
.tab-lead { margin: 0 0 10px; font-size: 13px; color: var(--ink-2); max-width: 64ch; }
.memory-area {
  width: 100%; box-sizing: border-box; background: var(--surface);
  border: 1.5px solid var(--line-strong); border-radius: 11px; color: var(--ink);
  padding: 12px 14px; font-size: 13.5px; line-height: 1.6; resize: vertical; font-family: inherit;
}
.memory-actions { display: flex; gap: 8px; margin-top: 9px; flex-wrap: wrap; }
.empty-box {
  padding: 16px 18px; border: 1.5px dashed var(--line-strong); border-radius: 11px;
  background: var(--surface); max-width: 60ch;
}
.empty-title { font-size: 13.5px; font-weight: 600; }
.empty-body { margin: 5px 0 10px; font-size: 13px; color: var(--ink-2); line-height: 1.5; }

.source-chips { display: flex; flex-wrap: wrap; gap: 7px; margin-bottom: 12px; }
.source-chip {
  display: inline-flex; align-items: center; gap: 7px; font-size: 12.5px;
  padding: 6px 12px; border-radius: 999px; background: var(--surface); border: 1px solid var(--line-strong);
}
.chip-x { background: none; border: none; color: var(--ink-3); cursor: pointer; padding: 0; font-size: 12px; }
.chip-x:hover { color: var(--danger); }
.source-add { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }
.source-input { flex: 1; min-width: 220px; width: auto; }
.read-result { margin: -6px 0 14px; font-size: 12.5px; color: var(--ink-2); }
.ie-row { display: flex; gap: 8px; flex-wrap: wrap; }
.hidden-input { display: none; }
.ie-note { margin: 9px 0 0; font-size: 12px; color: var(--ink-3); }

.skill-row {
  display: flex; align-items: center; gap: 11px; padding: 10px 13px;
  background: var(--surface); border: 1px solid var(--line); border-radius: 11px; margin-bottom: 7px;
}
.skill-text { flex: 1; min-width: 0; line-height: 1.3; }
.skill-name { font-size: 13.5px; font-weight: 600; }
.skill-when { font-size: 12px; color: var(--ink-3); }

.graph-aside {
  flex: 0 1 360px; min-width: 300px; background: var(--surface);
  border-left: 1px solid var(--line); padding: 12px; overflow-y: auto;
  display: flex; flex-direction: column;
}
.graph-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.graph-label {
  font-size: 9.5px; font-weight: 700; letter-spacing: 0.11em;
  text-transform: uppercase; color: var(--ink-3);
}
.graph-btn {
  background: none; border: 1px solid var(--line-strong); border-radius: 7px;
  color: var(--ink-3); cursor: pointer; padding: 3px 8px; font-size: 10.5px; font-family: inherit;
}
.graph-btn.accent { border-color: var(--accent); color: var(--accent); font-weight: 600; }
.graph-box {
  position: relative; border: 1px solid var(--line); border-radius: 10px;
  background: var(--sunken); overflow: hidden; aspect-ratio: 1;
}
.graph-hint { position: absolute; left: 8px; bottom: 7px; font-size: 9.5px; color: var(--ink-3); pointer-events: none; }
.retrieval-label {
  font-size: 9.5px; font-weight: 700; letter-spacing: 0.11em; text-transform: uppercase;
  color: var(--ink-3); margin: 16px 0 8px;
}
.retrieval {
  margin: 0; font-size: 11px; line-height: 1.6; color: var(--ink-2);
  background: var(--sunken); border: 1px solid var(--line); border-radius: 8px; padding: 9px 10px;
}

/* Narrow windows cannot hold list + profile + graph — the graph moves to its
   own full view (Expand). */
@media (max-width: 1200px) { [data-graph-aside] { display: none !important; } }
</style>
