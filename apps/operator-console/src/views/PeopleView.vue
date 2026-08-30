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
          <!-- U271: 34×26 px, and the one thing this row asks is "who is
               that?". Click it to see a face you can actually read. -->
          <button class="visitor-thumb-btn" title="See this face larger"
                  @click="zoomVisitor(v)">
            <img :src="knowledge.sightingImageUrl(v.sighting_id)" alt="Unknown visitor" class="visitor-thumb">
          </button>
          <span class="visitor-seen">Seen {{ v.count }}× · {{ fmtAgo(v.last_seen) }}</span>
          <!-- U277: why a face you HAVE taught can still land here. It scored
               below the bar — a different angle, worse light, further away —
               and that near-miss was computed and thrown away, so the row gave
               no way to tell "this is you badly lit" from "this is a stranger". -->
          <span v-if="nearMiss(v)" class="visitor-near">{{ nearMiss(v) }}</span>
          <div class="visitor-actions">
            <select :aria-label="'Tag as person'" class="visitor-select" @change="tagVisitor(v.sighting_id, $event)">
              <option value="">Tag as…</option>
              <option v-for="p in knowledge.people" :key="p.person_id" :value="p.person_id">{{ p.display_name }}</option>
            </select>
            <button class="visitor-dismiss" title="Not a person / never mind" @click="knowledge.dismissSighting(v.sighting_id)">Dismiss</button>
          </div>
        </div>
        <p class="visitors-note">Tagging adds this shot to that person's face — every angle you tag makes the next one recognisable. The guest profile is absorbed.</p>
        <p v-if="tagMsg" class="visitors-note visitors-tagged">{{ tagMsg }}</p>
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
            <span class="person-sub">
              {{ p.role }} · {{ hasFace(p.person_id) ? 'face known' : 'no face yet' }}
              <!-- U281: he may now add someone he hears about in a
                   conversation. A household should never have to wonder where
                   a profile came from, so his are marked as his. -->
              <span v-if="(p as { auto_created?: boolean }).auto_created" class="added-by-him"
                    title="He added this profile from something you said. Rename, change the role, or forget it — it is yours now.">added by him</span>
            </span>
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
            <option value="family">family</option>
            <!-- U274: the brain's roles are owner/family/guest/minor/demo.
                 This offered "kid", which every PUT rejected with 422 —
                 silently, because a failed role change showed nothing. And
                 it is the one role with real teeth: a minor is never learned
                 about passively (ADR-008 §10). -->
            <option value="minor">child — nothing learned passively</option>
            <option value="guest">guest</option><option value="owner">owner</option>
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
              <option value="owner">owner</option><option value="family">family</option>
              <option value="minor">child — nothing learned passively</option>
              <option value="guest">guest</option>
            </select>
          </label>
          <span v-else class="role-chip">Role: {{ detail.person.role }} · set by the owner</span>
        </div>

        <!-- U274: how he should meet THIS person. Asked for as "per person,
             add option to select default language and default robot" — the
             robot being which of his characters he becomes. Both default to
             "same as everyone", so a household that wants none of this sees
             no change. -->
        <p v-if="roleError" class="present-error role-error">{{ roleError }}</p>

        <div v-if="isOwner" class="person-prefs">
          <label class="pref">
            <span class="pref-k">Speaks to them in</span>
            <select :value="personLanguage" class="d2-field" aria-label="Reply language for this person"
                    @change="savePref('language', $event)">
              <option value="">same as everyone (Settings)</option>
              <option v-for="l in LANGUAGES" :key="l.code" :value="l.code">{{ l.name }}</option>
            </select>
          </label>
          <label class="pref">
            <span class="pref-k">Meets them as</span>
            <select :value="personCharacter" class="d2-field" aria-label="Character for this person"
                    @change="savePref('character', $event)">
              <option value="">same as everyone (Robot)</option>
              <option v-for="c in brainCharacters" :key="c.id" :value="c.id">{{ c.display_name }}</option>
            </select>
          </label>
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
                <!-- U271: the question here is "is this really them?", which
                     a thumbnail cannot answer either. -->
                <button class="snapshot-btn" title="See this shot larger"
                        @click="zoomSnapshot(s)">
                  <img :src="s.image" alt="Recognition snapshot" class="snapshot-img">
                </button>
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
              <!-- U262: editing in place. A wrong belief about a person that
                   you can only read is worse than one you can correct. -->
              <template v-if="editingFact === f.fact_id">
                <input v-model="editKey" class="d2-field fact-key-input" aria-label="Fact key"
                       @keydown.esc="editingFact = null">
                <input v-model="editValue" class="d2-field" aria-label="Fact value"
                       @keydown.enter="saveEdit(f)" @keydown.esc="editingFact = null">
                <div class="fact-actions">
                  <button class="d2-primary-btn fact-save" :disabled="!editKey.trim() || !editValue.trim()"
                          @click="saveEdit(f)">Save</button>
                  <button class="d2-ghost-btn fact-save" @click="editingFact = null">Cancel</button>
                </div>
              </template>
              <template v-else>
                <div class="fact-key">{{ f.key }}</div>
                <div class="fact-value">
                  <!-- [[targets]] substituted INLINE — the sentence stays whole -->
                  <WikiText :text="f.value" @open="openTarget" />
                </div>
                <div v-if="full" class="mono fact-src">{{ f.source }}</div>
                <div class="fact-tools">
                  <button class="fact-x" title="Correct this fact" @click="startEdit(f)">✎</button>
                  <button class="fact-x" title="Delete this fact" @click="removeFact(f)">✕</button>
                </div>
              </template>
            </div>
          </div>
          <p v-if="factError" class="fact-error">{{ factError }}</p>
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
          <!-- U276: it only grows for the person the BRAIN believes it is
               talking to, and that used to come from face recognition alone.
               With no face taught, conversations were answered properly and
               then forgotten — while this very paragraph promised otherwise. -->
          <p v-if="!knowledge.remembering" class="memory-warn">
            <strong>Nothing is being remembered right now.</strong>
            He does not know who he is talking to, so this conversation is
            answered and then dropped. Pick who you are in the header, or teach
            him this face, and it starts growing again.
          </p>
          <template v-if="memoryText || memoryDraft">
            <textarea v-model="memoryDraft" rows="9" aria-label="Memory" class="memory-area" />
            <div class="memory-actions">
              <button class="d2-ghost-btn" @click="saveMemory">Save memory</button>
              <span v-if="memoryMsg" class="memory-msg">{{ memoryMsg }}</span>
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

    <!-- U271: the photo, big enough to recognise. For an unknown visitor the
         tag control comes along: you enlarged it precisely in order to decide
         who it is, and closing the panel to hunt for the same tiny row again
         is the annoying half of the job. -->
    <PhotoLightbox
      v-if="zoomed" :src="zoomed.src" :caption="zoomed.caption"
      @close="zoomed = null"
    >
      <template v-if="zoomed.sightingId" #actions>
        <select class="visitor-select" aria-label="Tag as person"
                @change="tagFromLightbox($event)">
          <option value="">Tag as…</option>
          <option v-for="p in knowledge.people" :key="p.person_id" :value="p.person_id">
            {{ p.display_name }}
          </option>
        </select>
        <button class="visitor-dismiss" title="Not a person / never mind"
                @click="dismissFromLightbox()">Dismiss</button>
      </template>
    </PhotoLightbox>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import KnowledgeGraph from '../components/canvas/KnowledgeGraph.vue'
import PhotoLightbox from '../components/PhotoLightbox.vue'
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
  fetchCharacters()          // U274: the "meets them as" list
  knowledge.fetchSpeaker()   // U276: is he attributing anything to anyone?
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
// U278: the LAST memory fact, not the first. Saving used to append, so a
// store can already hold several — and first-match showed the oldest, which
// is precisely why a correction looked like it had not saved. The next save
// collapses them back to one; until then, show what the owner wrote last.
const memoryText = computed(() => {
  const notes = (detail.value?.facts ?? []).filter(f => f.key === 'memory')
  return notes.length ? notes[notes.length - 1].value : ''
})

const addingFact = ref(false)
const factKey = ref('')
const factValue = ref('')

// ── U262: correcting and removing what he believes ─────────────────────────
// The cross used to call the brain and, when the brain refused, nothing at all
// happened on screen — the single most confusing outcome available. Whatever
// goes wrong now has to be readable next to the fact it went wrong on.
const editingFact = ref<string | null>(null)
const editKey = ref('')
const editValue = ref('')
const factError = ref('')

function startEdit(f: { fact_id: string; key: string; value: string }): void {
  editingFact.value = f.fact_id
  editKey.value = f.key
  editValue.value = f.value
  factError.value = ''
}

async function saveEdit(f: { fact_id: string }): Promise<void> {
  const person = detail.value?.person.person_id
  if (!person) return
  factError.value = ''
  const ok = await knowledge.updateFact(
    person, f.fact_id, editKey.value.trim(), editValue.value.trim())
  if (ok) editingFact.value = null
  else factError.value = knowledge.error ?? 'Could not save that change.'
}

async function removeFact(f: { fact_id: string; key: string }): Promise<void> {
  const person = detail.value?.person.person_id
  if (!person) return
  if (!window.confirm(`Forget that ${f.key}? He will no longer know it.`)) return
  factError.value = ''
  if (!await knowledge.deleteFact(f.fact_id, person)) {
    factError.value = knowledge.error ?? 'Could not delete that fact.'
  }
}
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
// ── U277: how close an unknown face came to someone he knows ──────────────
// A face lands in "unknown visitors" because its best match scored under the
// threshold. That number exists — `identify()` computes it — and used to be
// discarded, so a face taught ten minutes ago showed up as a stranger with no
// explanation. Seeing "closest: Jan (0.34 of 0.40)" turns tagging from a
// guess into a decision, and confirms what tagging is FOR.
function nearMiss(v: { near_person?: string; near_score?: number }): string {
  if (!v.near_person || typeof v.near_score !== 'number') return ''
  const name = knowledge.people.find(p => p.person_id === v.near_person)?.display_name
    ?? v.near_person
  return `closest: ${name} (${v.near_score.toFixed(2)} of ${knowledge.recognitionThreshold.toFixed(2)} needed)`
}

const tagMsg = ref('')

// ── U274: per-person language and character ───────────────────────────────
// The list the brain actually understands (orchestrator/_LANGUAGE_NAMES) —
// offering a language he cannot be instructed in would be a dropdown that
// silently does nothing.
const LANGUAGES = [
  { code: 'en', name: 'English' }, { code: 'nl', name: 'Nederlands' },
  { code: 'fr', name: 'Français' }, { code: 'de', name: 'Deutsch' },
  { code: 'es', name: 'Español' }, { code: 'it', name: 'Italiano' },
]
interface BrainCharacter { id: string; display_name: string }
const brainCharacters = ref<BrainCharacter[]>([])
async function fetchCharacters(): Promise<void> {
  try {
    const r = await fetch(`${BRAIN_URL}/setup/characters`)
    if (r.ok) brainCharacters.value = (await r.json()).characters ?? []
  } catch { /* the dropdown falls back to "same as everyone" */ }
}
const personLanguage = computed(() =>
  (detail.value?.person as { language?: string } | undefined)?.language ?? '')
const personCharacter = computed(() =>
  (detail.value?.person as { character?: string } | undefined)?.character ?? '')

async function savePref(field: 'language' | 'character', e: Event): Promise<void> {
  if (!detail.value) return
  const value = (e.target as HTMLSelectElement).value
  await knowledge.setPersonPrefs(detail.value.person.person_id, { [field]: value })
}

const roleError = ref('')
async function changeRole(e: Event): Promise<void> {
  if (!detail.value) return
  const role = (e.target as HTMLSelectElement).value
  roleError.value = ''
  const ok = await knowledge.renamePerson(
    detail.value.person.person_id, detail.value.person.display_name, role)
  // U274: this failed silently for every "kid" ever chosen — the select moved,
  // the brain said 422, and the screen showed the new value as if it had taken.
  if (!ok) roleError.value = knowledge.error ?? 'That role was not accepted.'
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
  // U277: the store returns what actually happened ("he now has 5 shots of
  // that face") and it used to be thrown away at the call site.
  tagMsg.value = await knowledge.tagSighting(sightingId, personId)
  knowledge.fetchSightings()
  fetchEnrolled()
}

// ── U271: see the face ─────────────────────────────────────────────────────
// The visitor thumbnails are 34×26 px and the row's only question is "who is
// that?"; the snapshots ask "is this really them?". Neither is answerable at
// that size. Reported as "photos are quite small, on click picture ad larger
// preview to more easily recognize".
const zoomed = ref<{ src: string; caption: string; sightingId?: string } | null>(null)

function zoomVisitor(v: { sighting_id: string; count: number; last_seen: number }): void {
  zoomed.value = {
    src: knowledge.sightingImageUrl(v.sighting_id),
    caption: `Unknown visitor — seen ${v.count}× · ${fmtAgo(v.last_seen)}`,
    sightingId: v.sighting_id,
  }
}
function zoomSnapshot(s: { image: string; seen_at: number; confidence: number }): void {
  zoomed.value = { src: s.image, caption: fmtSnapshot(s) }
}

async function tagFromLightbox(e: Event): Promise<void> {
  const id = zoomed.value?.sightingId
  if (!id) return
  await tagVisitor(id, e)
  zoomed.value = null          // the decision is made; the photo has done its job
}
async function dismissFromLightbox(): Promise<void> {
  const id = zoomed.value?.sightingId
  if (!id) return
  await knowledge.dismissSighting(id)
  zoomed.value = null
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
const memoryMsg = ref('')
async function saveMemory(): Promise<void> {
  if (!detail.value) return
  // U278: REPLACE, don't append. addFact() posted a second fact with the same
  // key while every reader — this view and the brain both — takes the first,
  // so a correction was stored, never shown, and never reached the model.
  memoryMsg.value = ''
  const ok = await knowledge.saveMemory(
    detail.value.person.person_id, memoryDraft.value.trim())
  memoryMsg.value = ok
    ? 'Saved — this is what he reads from now on.'
    : knowledge.error ?? 'Could not save that.'
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
/* U271: the thumbnail is now a button — the face you must recognise is one
   click from being legible. */
.visitor-thumb-btn { padding: 0; border: 0; background: none; cursor: zoom-in; flex-shrink: 0; line-height: 0; }
.visitor-thumb { width: 34px; height: 26px; border-radius: 6px; flex-shrink: 0; object-fit: cover; border: 1px solid var(--line); }
.visitor-thumb-btn:hover .visitor-thumb { border-color: var(--accent); }
.snapshot-btn { padding: 0; border: 0; background: none; cursor: zoom-in; display: block; line-height: 0; }
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

.visitor-near { font-size: 0.72rem; color: var(--ink-3); display: block; margin-top: 1px; }
.visitors-tagged { color: var(--ok, #2f7d32); }
.memory-msg { font-size: 0.78rem; color: var(--ok, #2f7d32); align-self: center; }
.added-by-him {
  display: inline-block; margin-left: 0.3rem; padding: 0 0.35rem;
  border-radius: 999px; background: var(--surface-2, rgba(127,127,127,0.12));
  color: var(--ink-3); font-size: 0.66rem;
}
.memory-warn {
  background: var(--warn-wash, rgba(200, 150, 20, 0.12)); color: var(--ink-2);
  border-radius: 8px; padding: 0.6rem 0.8rem; font-size: 0.82rem; line-height: 1.5;
  margin: 0 0 0.6rem;
}
.role-error { color: var(--danger, #e5484d); font-size: 0.8rem; margin: 0.3rem 0 0; }
.person-prefs { display: flex; gap: 1.2rem; flex-wrap: wrap; margin: 0.5rem 0 0.2rem; }
.pref { display: flex; flex-direction: column; gap: 0.2rem; font-size: 0.78rem; }
.pref-k { color: var(--ink-3); }

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
  /* The container is positioned now (.fact-tools), so these sit side by side
     instead of stacking on the same corner. */
  background: none; border: none; color: var(--ink-3); cursor: pointer;
  font-size: 12px; line-height: 1; padding: 3px 4px; border-radius: 6px;
  opacity: 0.35;                 /* discoverable, not shouting */
}
.fact-card:hover .fact-tools .fact-x { opacity: 1; }
.fact-x:hover { background: var(--sunken); }
.fact-tools { position: absolute; top: 6px; right: 6px; display: flex; gap: 2px; }
.fact-key-input { margin-bottom: 5px; font-size: 12px; }
.fact-actions { display: flex; gap: 5px; margin-top: 7px; }
.fact-save { padding: 4px 11px; font-size: 12px; }
.fact-error {
  margin: 8px 0 0; font-size: 12.5px; color: var(--danger);
  background: var(--danger-wash); border-radius: 8px; padding: 7px 11px; max-width: 60ch;
}
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
