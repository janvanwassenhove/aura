<template>
  <div :class="docked ? 'brain-docked' : 'brain-overlay'" @click.self="onBackdrop">
    <div :class="docked ? 'brain-dock-inner' : 'brain-modal'">
      <header class="brain-header">
        <span class="brain-title"><Brain :size="17" /> {{ prefs.assistantName }}'s brain</span>
        <span v-if="store.tier" class="brain-tier" :title="`Unlock tier: ${store.tier}`">
          <ShieldCheck :size="12" /> {{ store.tier }}
        </span>
        <span v-if="store.locked" class="brain-locked-badge" title="Encrypted &amp; locked"><Lock :size="12" /> locked</span>
        <button v-if="!docked" class="brain-close" aria-label="Close" @click="$emit('close')"><X :size="15" /></button>
      </header>

      <div v-if="store.brainError" class="brain-restart-banner">
        <span>⚠ The brain needs a restart to load recent fixes and your profiles.</span>
        <button class="brb-btn" :disabled="restartingBrain" @click="restartBrain">
          {{ restartingBrain ? 'Restarting…' : 'Restart brain' }}
        </button>
      </div>

      <div class="brain-body">
        <!-- ── Left rail: skills library + people ── -->
        <nav class="brain-rail">
          <button :class="['rail-item', selected === '_skills' && 'rail-item--active']" @click="select('_skills')">
            <span class="rail-avatar rail-avatar--skills"><Sparkles :size="15" /></span>
            <span class="rail-label">Skills library</span>
            <span class="rail-count">{{ skills.length }}</span>
          </button>
          <button :class="['rail-item', selected === '_graph' && 'rail-item--active']" @click="selectGraph()">
            <span class="rail-avatar rail-avatar--skills"><Share2 :size="15" /></span>
            <span class="rail-label">Graph</span>
          </button>
          <div class="rail-sep">People</div>
          <button
            v-for="p in store.people" :key="p.person_id"
            :class="['rail-item', selected === p.person_id && 'rail-item--active']"
            @click="select(p.person_id)"
          >
            <span class="rail-avatar">{{ initials(p.display_name) }}</span>
            <span class="rail-label">{{ p.display_name }}</span>
            <span :class="['rail-role', `rail-role--${p.role}`]">{{ p.role }}</span>
          </button>
          <div v-if="store.locked" class="rail-unlock">
            <p class="rail-locked">Profiles are locked.</p>
            <input v-model="unlockPass" type="password" class="rail-input" placeholder="Knowledge passphrase" @keydown.enter="doUnlock" />
            <button class="rail-btn" :disabled="!unlockPass || unlocking" @click="doUnlock">
              {{ unlocking ? 'Unlocking…' : 'Unlock' }}
            </button>
            <p v-if="unlockErr" class="rail-err">{{ unlockErr }}</p>
          </div>
          <div v-else class="rail-add">
            <!-- U112: the add-person form only unfolds on demand -->
            <button v-if="!showAddPerson" class="rail-btn rail-btn--ghost" @click="showAddPerson = true">
              + Add person
            </button>
            <template v-else>
              <div class="rail-sep">Add person</div>
              <input v-model="newP.id" class="rail-input" placeholder="id (e.g. jan)" />
              <input v-model="newP.name" class="rail-input" placeholder="Display name" />
              <select v-model="newP.role" class="rail-input">
                <option value="owner">owner</option><option value="family">family</option>
                <option value="guest">guest</option><option value="minor">minor</option>
              </select>
              <button class="rail-btn" :disabled="!newP.id.trim() || !newP.name.trim() || addingP" @click="addPerson">
                {{ addingP ? 'Adding…' : 'Add' }}
              </button>
              <button class="rail-btn rail-btn--ghost" @click="showAddPerson = false">Cancel</button>
            </template>
          </div>
        </nav>

        <!-- ── Right: skills library (U117: full editing + optimize live here) ── -->
        <section v-if="selected === '_skills'" class="brain-content">
          <!-- U108: proactive optimization suggestions -->
          <div v-if="suggestions.length" class="skill-suggest">
            <span>🔧 <strong>{{ suggestions.length }} skill{{ suggestions.length === 1 ? '' : 's' }} ready to optimize</strong></span>
            <button v-for="s in suggestions" :key="s.name" class="b-tag" :disabled="optimizing === s.name" @click="optimizeSkillByName(s.name)">
              {{ s.name }} <em class="suggest-plus">+{{ s.new_since_optimized }}</em>
            </button>
          </div>

          <h3 class="content-title">General skills</h3>
          <p class="content-hint">Procedures that apply to everyone. Teach new ones with the 🎓 button, or add below.</p>
          <div class="skill-grid">
            <article v-for="sk in generalSkills" :key="sk.name" :class="['b-skill-card', !sk.enabled && 'b-skill-card--off']">
              <header class="b-skill-head">
                <span class="b-skill-name">{{ sk.name }}</span>
                <span v-if="skillMetrics[sk.name]?.uses" class="b-uses" :title="`Used ${skillMetrics[sk.name].uses}× · ${skillMetrics[sk.name].new_since_optimized} new signal(s)`">{{ skillMetrics[sk.name].uses }}×</span>
                <button class="b-icon-btn" :disabled="optimizing === sk.name" title="Optimize — rewrite from real usage (you approve the diff)" @click="optimizeSkillCard(sk)"><Sparkles :size="12" /></button>
                <button class="b-icon-btn" title="Edit" @click="editSkillCard(sk)"><Pencil :size="12" /></button>
              </header>
              <p class="b-skill-desc"><WikiText :text="sk.description" @open="openTarget" /></p>
              <div class="b-skill-tags">
                <span v-for="t in sk.triggers" :key="t" class="b-tag" title="Trigger word — the assistant uses this skill when your request contains it">“{{ t }}” <button class="b-tag-x" :aria-label="`Remove trigger ${t}`" @click="removeTrigger(sk, t)">×</button></span>
                <button class="b-tag b-tag--add" title="Add a trigger word" @click="addTrigger(sk)">+ trigger</button>
              </div>
            </article>
            <p v-if="!generalSkills.length" class="content-hint">No general skills yet.</p>
          </div>

          <template v-for="grp in personSkillGroups" :key="grp.personId">
            <h3 class="content-title content-title--spaced">
              <button class="person-link" @click="select(grp.personId)">{{ grp.label }}</button>'s way of working
            </h3>
            <div class="skill-grid">
              <article v-for="sk in grp.skills" :key="sk.name" :class="['b-skill-card', !sk.enabled && 'b-skill-card--off']">
                <header class="b-skill-head">
                  <span class="b-skill-name">{{ sk.name }}</span>
                  <button class="b-icon-btn" :disabled="optimizing === sk.name" title="Optimize — rewrite from real usage" @click="optimizeSkillCard(sk)"><Sparkles :size="12" /></button>
                  <button class="b-icon-btn" title="Edit" @click="editSkillCard(sk)"><Pencil :size="12" /></button>
                </header>
                <p class="b-skill-desc"><WikiText :text="sk.description" @open="openTarget" /></p>
              </article>
            </div>
          </template>

          <!-- U117: optimize proposal — before/after diff, owner applies -->
          <div v-if="skillProposal" class="skill-opt">
            <p class="skill-opt-head"><strong>{{ skillProposal.name }}</strong> — proposed rewrite, based on {{ skillProposal.based_on }} use(s). {{ skillProposal.rationale }}</p>
            <p v-if="!skillProposal.changed" class="content-hint">Already optimal — nothing to change.</p>
            <div v-else class="skill-opt-diff">
              <div class="skill-opt-col"><span class="skill-opt-label">Current</span><pre class="skill-opt-pre">{{ skillProposal.current_body }}</pre></div>
              <div class="skill-opt-col"><span class="skill-opt-label">Proposed</span><pre class="skill-opt-pre skill-opt-pre--new">{{ skillProposal.proposed_body }}</pre></div>
            </div>
            <div class="inline-add">
              <button v-if="skillProposal.changed" class="b-btn" @click="applySkillProposal()">Apply rewrite</button>
              <button class="b-btn b-btn--ghost" @click="skillProposal = null">Dismiss</button>
            </div>
          </div>
          <p v-if="optimizeNote" class="b-error">{{ optimizeNote }}</p>

          <!-- U117: inline skill editor — no more jump to Settings -->
          <div v-if="editSkillDraft" class="skill-editor-inline">
            <h3 class="content-title content-title--spaced">{{ editSkillIsNew ? 'New skill' : `Edit ${editSkillDraft.name}` }}</h3>
            <div class="inline-add">
              <input v-model="editSkillDraft.name" class="b-input" placeholder="name (kebab-case)" :disabled="!editSkillIsNew" aria-label="Skill name" />
              <input v-model="editSkillDraft.description" class="b-input b-grow" placeholder="One-line description" aria-label="Skill description" />
            </div>
            <div class="inline-add">
              <input v-model="editSkillTriggers" class="b-input b-grow" placeholder="Triggers, comma-separated (e.g. deploy, release)" aria-label="Skill triggers" />
              <input v-model="editSkillDraft.person" class="b-input" placeholder="Person id (optional)" aria-label="Skill person" />
            </div>
            <textarea v-model="editSkillDraft.body" class="b-input b-skill-body" rows="6" placeholder="The procedure, step by step… Link with [[person-id]] or [[other-skill]]." aria-label="Skill procedure" />
            <div class="inline-add">
              <button class="b-btn" :disabled="!editSkillDraft.name.trim() || !editSkillDraft.body.trim()" @click="saveSkillDraft()">Save</button>
              <button class="b-btn b-btn--ghost" @click="editSkillDraft = null">Cancel</button>
              <button v-if="!editSkillIsNew" class="b-btn b-btn--danger" @click="deleteSkillDraft()">Delete</button>
              <label v-if="!editSkillIsNew" class="refresh-toggle" title="Disabled skills stay saved but are never used">
                <input type="checkbox" v-model="editSkillDraft.enabled" /> enabled
              </label>
            </div>
          </div>
          <button v-else class="b-btn" @click="newSkillDraft()">+ New skill</button>
          <p v-if="addError" class="b-error">{{ addError }}</p>
        </section>

        <!-- ── Right: the graph (U75) ── -->
        <section v-else-if="selected === '_graph'" class="brain-content brain-content--graph">
          <BrainGraph
            :people="store.people"
            :skills="skills"
            :facts="graphFacts"
            @open="onGraphOpen"
          />
        </section>

        <!-- ── Right: one person's brain ── -->
        <section v-else-if="selected !== '_skills' && store.detail" class="brain-content">
          <div class="person-hero">
            <span class="hero-avatar">{{ initials(store.detail.person.display_name) }}</span>
            <div class="hero-meta">
              <h2 class="hero-name">{{ store.detail.person.display_name }}</h2>
              <span :class="['rail-role', `rail-role--${store.detail.person.role}`]">{{ store.detail.person.role }}</span>
            </div>
            <span class="hero-spacer" />
            <button v-if="store.recognitionEnabled" class="hero-btn" :disabled="teaching" title="Teach this person's face" @click="doTeachFace">
              <ScanFace :size="14" /> {{ teaching ? 'Looking…' : 'Teach face' }}
            </button>
            <!-- U112: rare actions live behind ⋯ instead of permanent sections -->
            <div class="hero-menu-wrap">
              <button class="hero-btn" title="More actions" @click="heroMenuOpen = !heroMenuOpen">
                <MoreHorizontal :size="14" />
              </button>
              <div v-if="heroMenuOpen" class="hero-menu" @click="heroMenuOpen = false">
                <button class="hero-menu-item" :disabled="importing"
                        title="Drop a ChatGPT/Claude data-export (conversations.json) — mined locally for facts about this person"
                        @click="chatFileInput?.click()">
                  {{ importing ? 'Mining chats…' : 'Import chat export…' }}
                </button>
                <button class="hero-menu-item" title="Download everything the brain knows as JSON" @click="doExportBrain">
                  Export brain (JSON)
                </button>
                <button class="hero-menu-item hero-menu-item--danger" title="Forget this person (erase profile + face)" @click="doForget">
                  Forget {{ store.detail.person.display_name }}…
                </button>
              </div>
            </div>
          </div>
          <p v-if="teachMsg" class="content-hint teach-line">{{ teachMsg }}</p>
          <p v-if="importNote" class="content-hint teach-line">{{ importNote }}</p>

          <!-- U112: profile tabs — no more one long scroll -->
          <nav class="person-tabs" role="tablist">
            <button v-for="t in PERSON_TABS" :key="t.id" role="tab"
                    :class="['person-tab', personTab === t.id && 'person-tab--active']"
                    :aria-selected="personTab === t.id" @click="personTab = t.id">
              {{ t.label }}
              <span v-if="t.id === 'skills' && (store.detail.skills?.length ?? 0)" class="person-tab-count">{{ store.detail.skills!.length }}</span>
            </button>
          </nav>

          <!-- hidden file input for the ⋯ Import action (lives outside the menu) -->
          <input ref="chatFileInput" type="file" accept=".json,application/json" class="file-hidden" aria-label="Chat export file" @change="importChatsFile" />

          <!-- Profile: About + Facts -->
          <template v-if="personTab === 'profile'">
            <h3 class="content-title">About</h3>
            <textarea
              v-model="aboutDraft" class="b-input b-about" rows="2"
              placeholder="Who is this person to you? Style, preferences… Link with [[skill-name]]."
              aria-label="About this person" @blur="saveAbout"
            />
            <p v-if="aboutDraft.includes('[[')" class="content-hint"><WikiText :text="aboutDraft" @open="openTarget" /></p>

            <h3 class="content-title content-title--spaced">Facts <span v-if="plainFacts.length" class="person-tab-count">{{ plainFacts.length }}</span></h3>
            <input v-if="plainFacts.length > 8" v-model="factFilter" class="b-input fact-filter" placeholder="Filter facts…" aria-label="Filter facts" />
            <!-- U117: facts scale — grouped per category, capped per group -->
            <div v-for="g in factGroups" :key="g.key" class="fact-group">
              <h4 class="fact-group-title">{{ g.key }} <span class="fact-group-count">×{{ g.facts.length }}</span></h4>
              <div class="fact-chips">
                <span v-for="f in (expandedGroups.has(g.key) ? g.facts : g.facts.slice(0, 5))" :key="f.fact_id" class="fact-chip" :title="f.value">
                  {{ f.value }}
                  <button class="chip-x" :aria-label="`Delete ${g.key} fact`" @click="store.deleteFact(f.fact_id, store.detail!.person.person_id)"><X :size="10" /></button>
                </span>
                <button v-if="g.facts.length > 5 && !expandedGroups.has(g.key)" class="fact-more" @click="expandedGroups.add(g.key)">
                  +{{ g.facts.length - 5 }} more
                </button>
                <button v-else-if="g.facts.length > 5" class="fact-more" @click="expandedGroups.delete(g.key)">show less</button>
              </div>
            </div>
            <p v-if="!plainFacts.length" class="content-hint">No facts yet — add one below, or let sources/chats fill them in.</p>
            <p v-else-if="!factGroups.length" class="content-hint">Nothing matches “{{ factFilter }}”.</p>
            <div class="inline-add">
              <input v-model="newFact.key" class="b-input" placeholder="what (e.g. hobby)" aria-label="Fact key" />
              <input v-model="newFact.value" class="b-input b-grow" placeholder="answer (e.g. cycling)" aria-label="Fact value" />
              <button class="b-btn" :disabled="!newFact.key.trim() || !newFact.value.trim()" @click="addFact()">Add fact</button>
            </div>
          </template>

          <!-- Memory: what Richie remembers across conversations -->
          <template v-else-if="personTab === 'memory'">
            <h3 class="content-title" :title="`Grown automatically from conversations, injected into future turns. Edit freely.`">Memory</h3>
            <textarea
              v-model="memoryDraft" class="b-input b-memory" rows="10"
              :placeholder="`Nothing remembered yet. This fills in as you talk with ${prefs.assistantName}.`"
              aria-label="Long-term memory" @blur="saveMemory"
            />
          </template>

          <!-- Sources: where to read this person + grow the graph -->
          <template v-else-if="personTab === 'sources'">
            <h3 class="content-title" title="Injected into conversations as context; blog/website/github are read to grow the graph.">Sources</h3>
            <div class="fact-chips">
              <span v-for="f in sourceFacts" :key="f.fact_id" class="fact-chip fact-chip--source" :title="f.value">
                <component :is="sourceIcon(f.key.slice(7))" :size="12" class="chip-icon" />
                {{ shortSource(f.value) }}
                <span v-if="!FETCHABLE.includes(f.key.slice(7))" class="chip-muted" title="Needs a login — used as context only, not read">🔒</span>
                <button class="chip-x" :aria-label="`Delete ${f.key}`" @click="store.deleteFact(f.fact_id, store.detail!.person.person_id)"><X :size="10" /></button>
              </span>
              <span v-if="!sourceFacts.length" class="content-hint">No sources yet — add a blog, site or handle below.</span>
            </div>
            <div class="inline-add">
              <select v-model="newSource.kind" class="b-input" aria-label="Source kind">
                <option v-for="k in SOURCE_KINDS" :key="k" :value="k">{{ k }}</option>
              </select>
              <input v-model="newSource.value" class="b-input b-grow" placeholder="handle / url / address" aria-label="Source value" />
              <button class="b-btn" :disabled="!newSource.value.trim()" @click="addSource()">Add</button>
            </div>
            <div v-if="sourceFacts.length" class="inline-add">
              <button class="b-btn" :disabled="ingesting" @click="growBrain()">
                {{ ingesting ? 'Reading sources…' : 'Grow brain from sources' }}
              </button>
              <label class="refresh-toggle" title="Re-read this person's sources on the weekly refresh (SOURCE_REFRESH_HOURS)">
                <input type="checkbox" :checked="refreshOn" @change="toggleRefresh()" /> auto-refresh
              </label>
              <span v-if="ingestNote" class="content-hint">{{ ingestNote }}</span>
            </div>
          </template>

          <!-- Skills: their way of working -->
          <template v-else-if="personTab === 'skills'">
            <h3 class="content-title">Their way of working</h3>
            <div class="skill-grid">
              <article v-for="sk in store.detail.skills ?? []" :key="sk.name" :class="['b-skill-card', !sk.enabled && 'b-skill-card--off']">
                <header class="b-skill-head">
                  <span class="b-skill-name">{{ sk.name }}</span>
                  <span v-if="(sk as any).via === 'mention'" class="b-tag" title="Mentions this person via a [[link]]">backlink</span>
                  <button class="b-icon-btn" title="Edit in Settings" @click="nav.openSkills(sk.name)"><Pencil :size="12" /></button>
                </header>
                <p class="b-skill-desc">{{ sk.description }}</p>
              </article>
              <p v-if="!(store.detail.skills?.length)" class="content-hint">No personal skills yet — add one below or teach via 🎓.</p>
            </div>
            <div class="inline-add">
              <input v-model="newSkill.name" class="b-input" placeholder="skill-name" aria-label="Skill name" />
              <input v-model="newSkill.body" class="b-input b-grow" :placeholder="`How ${store.detail.person.display_name} wants this done…`" aria-label="Skill procedure" />
              <button class="b-btn" :disabled="!newSkill.name.trim() || !newSkill.body.trim()" @click="addSkill(store.detail.person.person_id)">Add skill</button>
            </div>
            <p v-if="addError" class="b-error">{{ addError }}</p>
          </template>
        </section>

        <section v-else class="brain-content">
          <p class="content-hint">Select a person or the skills library.</p>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  BookOpen, Brain, Facebook, Github, Globe, Instagram, Linkedin, Lock, Mail,
  MoreHorizontal, Pencil, ScanFace, Share2, ShieldCheck, Sparkles, Twitter, X,
} from 'lucide-vue-next'
import BrainGraph from './BrainGraph.vue'
import WikiText from './WikiText.vue'
import { useKnowledgeStore } from '../stores/knowledgeStore'
import { useNavStore } from '../stores/navStore'
import { usePrefsStore } from '../stores/prefsStore'

const props = defineProps<{ docked?: boolean }>()
const emit = defineEmits<{ (e: 'close'): void }>()

function onBackdrop(): void {
  if (!props.docked) emit('close')
}

const store = useKnowledgeStore()
const prefs = usePrefsStore()
const nav = useNavStore()
const teaching = ref(false)
const unlockPass = ref('')
const unlocking = ref(false)
const unlockErr = ref('')
const newP = ref({ id: '', name: '', role: 'guest' })
const addingP = ref(false)

async function doUnlock() {
  if (!unlockPass.value) return
  unlocking.value = true
  unlockErr.value = ''
  try {
    const r = await fetch(`${BRAIN_URL}/knowledge/unlock`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ passphrase: unlockPass.value }),
    })
    if (!r.ok) { unlockErr.value = (await r.json().catch(() => ({}))).error ?? 'unlock failed'; return }
    unlockPass.value = ''
    await Promise.all([store.fetchTier(), store.fetchPeople()])
  } catch { unlockErr.value = 'brain unreachable' } finally { unlocking.value = false }
}
async function addPerson() {
  addingP.value = true
  try {
    const ok = await store.upsertPerson(newP.value.id.trim().toLowerCase(), newP.value.name.trim(), newP.value.role)
    if (ok) { const id = newP.value.id.trim().toLowerCase(); newP.value = { id: '', name: '', role: 'guest' }; await select(id) }
  } finally { addingP.value = false }
}
const teachMsg = ref('')
const restartingBrain = ref(false)
async function restartBrain() {
  const aura = (window as any).aura
  if (!aura?.restartBrain) {
    alert('Please fully CLOSE the AURA app (the X button, not Ctrl+R) and reopen it — that restarts the brain.')
    return
  }
  restartingBrain.value = true
  try {
    const r = await aura.restartBrain()
    if (r?.ok) location.reload()
    else alert('Restart failed: ' + (r?.error ?? 'unknown') + ' — try fully closing and reopening the app.')
  } finally { restartingBrain.value = false }
}

async function doTeachFace() {
  if (!store.detail) return
  teaching.value = true
  teachMsg.value = ''
  try { teachMsg.value = await store.teachFace(store.detail.person.person_id) }
  finally { teaching.value = false }
}
async function doForget() {
  if (!store.detail) return
  if (!confirm(`Forget ${store.detail.person.display_name}? This erases their profile and face.`)) return
  await store.forgetPerson(store.detail.person.person_id)
  selected.value = '_skills'
}
async function lockKnowledge() {
  try { await fetch(`${BRAIN_URL}/knowledge/lock`, { method: 'POST' }) } catch {}
  await store.fetchTier()
}
async function removeTrigger(sk: any, t: string) {
  const triggers = sk.triggers.filter((x: string) => x !== t)
  await saveSkillTriggers(sk, triggers)
}
async function addTrigger(sk: any) {
  const t = prompt('New trigger word (the assistant activates this skill when your request contains it):')
  if (!t || !t.trim()) return
  await saveSkillTriggers(sk, [...sk.triggers, t.trim().toLowerCase()])
}
async function saveSkillTriggers(sk: any, triggers: string[]) {
  await fetch(`${BRAIN_URL}/skills`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...sk, triggers }),
  }).catch(() => {})
  await fetchSkills()
}

interface SkillItem {
  name: string; description: string; triggers: string[]
  personas: string[]; person: string; enabled: boolean; body: string
}

const BRAIN_URL =
  import.meta.env.VITE_BRAIN_URL ??
  import.meta.env.VITE_ORCHESTRATOR_URL ??
  'http://localhost:8000'

const skills = ref<SkillItem[]>([])
const selected = ref<string>('_skills')
const aboutDraft = ref('')
const newFact = ref({ key: '', value: '' })
// U77: per-person sources — stored as `source:<kind>` facts so they persist in
// the encrypted store and reach the LLM via the judgment layer automatically.
const SOURCE_KINDS = ['instagram', 'facebook', 'x-twitter', 'linkedin', 'blog', 'website', 'gmail', 'github'] as const
const newSource = ref({ kind: 'instagram' as string, value: '' })

// U112: profile tabs + tidy chrome.
const PERSON_TABS = [
  { id: 'profile', label: 'Profile' },
  { id: 'memory', label: 'Memory' },
  { id: 'sources', label: 'Sources' },
  { id: 'skills', label: 'Skills' },
] as const
type PersonTab = typeof PERSON_TABS[number]['id']
const personTab = ref<PersonTab>('profile')
const heroMenuOpen = ref(false)
const showAddPerson = ref(false)

const SOURCE_ICONS: Record<string, unknown> = {
  instagram: Instagram, facebook: Facebook, 'x-twitter': Twitter, linkedin: Linkedin,
  blog: BookOpen, website: Globe, gmail: Mail, github: Github,
}
function sourceIcon(kind: string) {
  return SOURCE_ICONS[kind] ?? Globe
}
// Chip label: the handle/host, not the raw URL noise.
function shortSource(value: string): string {
  let v = value.trim().replace(/^https?:\/\//, '').replace(/^www\./, '').replace(/\/+$/, '')
  const parts = v.split('/')
  if (parts.length > 1 && parts[parts.length - 1]) v = `${parts[0]}/…/${parts[parts.length - 1]}`.replace('/…/', '/')
  return v.length > 28 ? v.slice(0, 27) + '…' : v
}
const sourceFacts = computed(() => (store.detail?.facts ?? []).filter(f => f.key.startsWith('source:')))
const plainFacts = computed(() => (store.detail?.facts ?? []).filter(f => !f.key.startsWith('source:') && f.key !== 'source-refresh' && f.key !== 'memory'))

// U117: facts scale — group by category, filterable, capped per group.
const factFilter = ref('')
const expandedGroups = ref(new Set<string>())
const factGroups = computed(() => {
  const q = factFilter.value.trim().toLowerCase()
  const groups = new Map<string, typeof plainFacts.value>()
  for (const f of plainFacts.value) {
    if (q && !f.key.toLowerCase().includes(q) && !f.value.toLowerCase().includes(q)) continue
    const list = groups.get(f.key) ?? []
    list.push(f)
    groups.set(f.key, list)
  }
  // Biggest groups first — that's where the bulk sits.
  return [...groups.entries()]
    .map(([key, facts]) => ({ key, facts }))
    .sort((a, b) => b.facts.length - a.facts.length)
})
watch(() => store.detail?.person.person_id, () => { factFilter.value = ''; expandedGroups.value = new Set() })
// U109: the person's long-term memory (grown from past conversations).
const memoryFact = computed(() => (store.detail?.facts ?? []).find(f => f.key === 'memory') ?? null)
const memoryDraft = ref('')
watch(memoryFact, (f) => { memoryDraft.value = f?.value ?? '' }, { immediate: true })
async function saveMemory(): Promise<void> {
  if (!store.detail) return
  const pid = store.detail.person.person_id
  const text = memoryDraft.value.trim()
  const existing = memoryFact.value
  if (existing && existing.value === text) return
  if (existing) await store.deleteFact(existing.fact_id, pid)
  if (text) await store.addFact(pid, 'memory', text)
  else await store.inspectPerson(pid)
}
// U105: which source kinds the brain can actually read without a login.
const FETCHABLE = ['blog', 'website', 'github']
// Per-person weekly auto-refresh: the LAST `source-refresh` fact wins.
const refreshOn = computed(() => {
  const rf = (store.detail?.facts ?? []).filter(f => f.key === 'source-refresh')
  return rf.length === 0 || rf[rf.length - 1].value.trim().toLowerCase() !== 'off'
})
async function toggleRefresh(): Promise<void> {
  if (!store.detail) return
  await store.addFact(store.detail.person.person_id, 'source-refresh', refreshOn.value ? 'off' : 'on')
}

async function addSource(): Promise<void> {
  if (!store.detail) return
  const kind = newSource.value.kind
  const value = newSource.value.value.trim()
  const ok = await store.addFact(store.detail.person.person_id, `source:${kind}`, value)
  if (!ok) return
  newSource.value.value = ''
  // U105: fetchable source → read it right away, so the graph grows on add.
  if (FETCHABLE.includes(kind)) {
    ingesting.value = true
    ingestNote.value = 'Reading new source…'
    try {
      const r = await store.ingestSources(store.detail.person.person_id, { kind, value })
      ingestNote.value = r
        ? (r.added_count ? `${r.added_count} new fact${r.added_count === 1 ? '' : 's'} from ${kind}` : (r.skipped[0]?.reason ?? 'nothing new found'))
        : 'Read failed — is the brain running?'
    } finally {
      ingesting.value = false
    }
  }
}

// U103: read fetchable sources (blog/website/github) → LLM distills [[linked]]
// facts → the brain graph grows. Auth-walled sources are honestly skipped.
const ingesting = ref(false)
const ingestNote = ref('')
async function growBrain(): Promise<void> {
  if (!store.detail || ingesting.value) return
  ingesting.value = true
  ingestNote.value = ''
  try {
    const r = await store.ingestSources(store.detail.person.person_id)
    if (!r) { ingestNote.value = 'Ingest failed — is the brain running?'; return }
    const skips = r.skipped.length ? ` · skipped ${r.skipped.length} (${r.skipped.map(s => `${s.kind}: ${s.reason}`).join('; ')})` : ''
    ingestNote.value = `${r.added_count} new fact${r.added_count === 1 ? '' : 's'} from ${r.read.length} source${r.read.length === 1 ? '' : 's'}${skips}`
  } finally {
    ingesting.value = false
  }
}
// U104: import a ChatGPT/Claude export → mined facts; export the whole brain.
const chatFileInput = ref<HTMLInputElement | null>(null)
const importing = ref(false)
const importNote = ref('')
async function importChatsFile(ev: Event): Promise<void> {
  const file = (ev.target as HTMLInputElement).files?.[0]
  if (!file || !store.detail || importing.value) return
  importing.value = true
  importNote.value = ''
  try {
    let parsed: unknown
    try {
      parsed = JSON.parse(await file.text())
    } catch {
      importNote.value = 'That file is not valid JSON — expected conversations.json from a ChatGPT or Claude export.'
      return
    }
    const r = await store.importChats(store.detail.person.person_id, parsed)
    if (!r) { importNote.value = store.error ?? 'Import failed.'; return }
    const skipped = r.chunks_skipped ? ` · ${r.chunks_skipped} chunks skipped (IMPORT_MAX_CHUNKS)` : ''
    importNote.value = r.error
      ? `Stopped early (${r.error}) — ${r.added_count} facts kept`
      : `${r.added_count} new fact${r.added_count === 1 ? '' : 's'} from ${r.conversations} conversation${r.conversations === 1 ? '' : 's'}${skipped}`
  } finally {
    importing.value = false
    if (chatFileInput.value) chatFileInput.value.value = ''
  }
}

async function doExportBrain(): Promise<void> {
  const data = await store.exportBrain()
  if (!data) return
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `aura-brain-export-${new Date().toISOString().slice(0, 10)}.json`
  a.click()
  URL.revokeObjectURL(a.href)
}

const newSkill = ref({ name: '', description: '', body: '' })
const addError = ref('')

const generalSkills = computed(() => skills.value.filter(s => !s.person))
const personSkillGroups = computed(() => {
  const groups: { personId: string; label: string; skills: SkillItem[] }[] = []
  for (const sk of skills.value) {
    if (!sk.person) continue
    let g = groups.find(x => x.personId === sk.person)
    if (!g) {
      const p = store.people.find(pp => pp.person_id === sk.person)
      g = { personId: sk.person, label: p?.display_name ?? sk.person, skills: [] }
      groups.push(g)
    }
    g.skills.push(sk)
  }
  return groups
})

function initials(name: string): string {
  return name.split(/\s+/).map(w => w[0] ?? '').join('').slice(0, 2).toUpperCase() || '?'
}

async function fetchSkills(): Promise<void> {
  try {
    const resp = await fetch(`${BRAIN_URL}/skills`)
    skills.value = (await resp.json()).skills ?? []
    // U117: usage metrics + proactive optimize suggestions (moved from Settings).
    const entries = await Promise.all(skills.value.map(async (sk) => {
      try {
        const m = await fetch(`${BRAIN_URL}/skills/${encodeURIComponent(sk.name)}/metrics`)
        return m.ok ? [sk.name, await m.json()] as const : null
      } catch { return null }
    }))
    skillMetrics.value = Object.fromEntries(entries.filter(Boolean) as [string, SkillMetric][])
    try {
      const s = await fetch(`${BRAIN_URL}/skills/suggestions`)
      suggestions.value = s.ok ? (await s.json()).suggestions ?? [] : []
    } catch { suggestions.value = [] }
  } catch { skills.value = [] }
}

// ── U117: skills are managed HERE now (editor + optimize, ex-Settings) ──
interface SkillMetric { uses: number; new_since_optimized: number; last_used: number | null }
const skillMetrics = ref<Record<string, SkillMetric>>({})
const suggestions = ref<{ name: string; new_since_optimized: number }[]>([])
const optimizing = ref('')
const optimizeNote = ref('')
interface SkillProposal { name: string; changed: boolean; rationale: string; current_body: string; proposed_body: string; based_on: number }
const skillProposal = ref<SkillProposal | null>(null)
const editSkillDraft = ref<SkillItem | null>(null)
const editSkillIsNew = ref(false)
const editSkillTriggers = ref('')

function newSkillDraft(): void {
  editSkillIsNew.value = true
  editSkillTriggers.value = ''
  editSkillDraft.value = { name: '', description: '', triggers: [], personas: [], person: '', enabled: true, body: '' }
}

function editSkillCard(sk: SkillItem): void {
  editSkillIsNew.value = false
  editSkillTriggers.value = sk.triggers.join(', ')
  editSkillDraft.value = { ...sk }
}

async function saveSkillDraft(): Promise<void> {
  if (!editSkillDraft.value) return
  addError.value = ''
  const payload = {
    ...editSkillDraft.value,
    name: editSkillDraft.value.name.trim().toLowerCase(),
    triggers: editSkillTriggers.value.split(',').map(t => t.trim()).filter(Boolean),
  }
  const resp = await fetch(`${BRAIN_URL}/skills`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }).catch(() => null)
  if (!resp || !resp.ok) {
    addError.value = resp ? String((await resp.json().catch(() => ({}))).error ?? `HTTP ${resp.status}`) : 'brain unreachable'
    return
  }
  editSkillDraft.value = null
  await fetchSkills()
}

async function deleteSkillDraft(): Promise<void> {
  if (!editSkillDraft.value || editSkillIsNew.value) return
  await fetch(`${BRAIN_URL}/skills/${encodeURIComponent(editSkillDraft.value.name)}`, { method: 'DELETE' }).catch(() => {})
  editSkillDraft.value = null
  await fetchSkills()
}

async function optimizeSkillCard(sk: SkillItem): Promise<void> {
  optimizing.value = sk.name
  optimizeNote.value = ''
  skillProposal.value = null
  try {
    const resp = await fetch(`${BRAIN_URL}/skills/${encodeURIComponent(sk.name)}/optimize`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}),
    }).catch(() => null)
    if (!resp || !resp.ok) {
      optimizeNote.value = resp ? String((await resp.json().catch(() => ({}))).error ?? `HTTP ${resp.status}`) : 'brain unreachable'
      return
    }
    skillProposal.value = await resp.json()
  } finally {
    optimizing.value = ''
  }
}

async function optimizeSkillByName(name: string): Promise<void> {
  const sk = skills.value.find(s => s.name === name)
  if (sk) await optimizeSkillCard(sk)
}

async function applySkillProposal(): Promise<void> {
  const prop = skillProposal.value
  if (!prop) return
  const sk = skills.value.find(s => s.name === prop.name)
  if (!sk) return
  const resp = await fetch(`${BRAIN_URL}/skills`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...sk, body: prop.proposed_body, mark_optimized: true }),
  }).catch(() => null)
  if (resp && resp.ok) {
    skillProposal.value = null
    await fetchSkills()
  } else {
    optimizeNote.value = 'Could not save the rewrite.'
  }
}

interface GraphFact { person_id: string; key: string; value: string }
const graphFacts = ref<GraphFact[]>([])

async function selectGraph(): Promise<void> {
  selected.value = '_graph'
  // Collect facts across people for the constellation (small N — fine).
  const all: GraphFact[] = []
  for (const p of store.people) {
    try {
      await store.inspectPerson(p.person_id)
      for (const f of store.detail?.facts ?? []) {
        all.push({ person_id: p.person_id, key: f.key, value: f.value })
      }
    } catch { /* locked or gone */ }
  }
  graphFacts.value = all
}

function onGraphOpen(kind: string, id: string): void {
  if (kind === 'person') select(id)
  else if (kind === 'skill') nav.openSkills(id)
  // topic nodes are anchors, not documents — nothing to open (yet).
}

// U117: skills open in THIS panel's library now (Settings lost its Skills tab).
watch(() => nav.skillsRequest, async (r) => {
  if (!r) return
  selected.value = '_skills'
  await fetchSkills()
  if (r.skillName) {
    const sk = skills.value.find(s => s.name === r.skillName)
    if (sk) editSkillCard(sk)
  }
}, { immediate: true })

async function select(id: string): Promise<void> {
  selected.value = id
  addError.value = ''
  personTab.value = 'profile'   // U112: fresh person → first tab
  heroMenuOpen.value = false
  if (id !== '_skills') await store.inspectPerson(id)
}

function openTarget(target: string): void {
  const t = target.toLowerCase()
  const person = store.people.find(
    p => p.person_id.toLowerCase() === t || p.display_name.toLowerCase() === t)
  if (person) { select(person.person_id); return }
  const skill = skills.value.find(sk => sk.name === t)
  if (skill) nav.openSkills(skill.name)
}

async function saveAbout(): Promise<void> {
  if (!store.detail) return
  const d = aboutDraft.value.trim()
  if (d === (store.detail.person.description ?? '')) return
  await store.saveDescription(store.detail.person.person_id, d)
}

async function addFact(): Promise<void> {
  if (!store.detail) return
  const ok = await store.addFact(store.detail.person.person_id, newFact.value.key.trim(), newFact.value.value.trim())
  if (ok) newFact.value = { key: '', value: '' }
}

async function addSkill(personId = ''): Promise<void> {
  addError.value = ''
  const payload = {
    name: newSkill.value.name.trim().toLowerCase(),
    description: newSkill.value.description.trim() ||
      (personId ? `${store.detail?.person.display_name}'s way of working` : ''),
    person: personId,
    body: newSkill.value.body.trim(),
  }
  const resp = await fetch(`${BRAIN_URL}/skills`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).catch(() => null)
  if (!resp || !resp.ok) {
    const data = resp ? await resp.json().catch(() => ({})) : {}
    addError.value = String(data.error ?? 'could not save skill')
    return
  }
  newSkill.value = { name: '', description: '', body: '' }
  await fetchSkills()
  if (personId && store.detail) await store.inspectPerson(personId)
}

watch(() => store.detail?.person.person_id, () => {
  aboutDraft.value = store.detail?.person.description ?? ''
})

// A [[wikilink]] elsewhere asked for a person → select them here.
watch(() => nav.knowledgeRequest, async (r) => {
  if (r) await select(r.personId)
})

onMounted(async () => {
  await Promise.all([store.fetchPeople(), fetchSkills(), store.fetchTier(), store.fetchRecognition()])
})
</script>

<style scoped>
/* U76: docked mode — fills the workspace dock instead of a modal overlay. */
.brain-docked { height: 100%; min-height: 0; display: flex; }
.brain-dock-inner {
  flex: 1; min-width: 0; min-height: 0;
  display: flex; flex-direction: column; overflow: hidden;
}
.brain-docked .brain-rail { width: 12rem; }

.brain-overlay {
  position: fixed; inset: 0; z-index: 120;
  background: color-mix(in srgb, var(--bg) 60%, transparent);
  backdrop-filter: blur(2px);
  display: flex; align-items: center; justify-content: center;
}
.brain-modal {
  width: 58rem; max-width: 96vw; height: 40rem; max-height: 92vh;
  background: var(--surface); border: 1px solid var(--border-strong);
  border-radius: var(--radius-xl); box-shadow: var(--shadow-modal);
  display: flex; flex-direction: column; overflow: hidden;
}
.brain-header {
  display: flex; align-items: center; gap: 0.75rem;
  padding: 0.9rem 1.1rem; border-bottom: 1px solid var(--border);
}
.brain-title { font-weight: 600; font-size: 0.95rem; display: inline-flex; align-items: center; gap: 0.45rem; flex: 1; }
.brain-tier { font-size: 0.68rem; color: var(--text-faint); display: inline-flex; align-items: center; gap: 0.25rem; text-transform: uppercase; }
.brain-locked-badge { font-size: 0.7rem; color: var(--warn, #d9a441); display: inline-flex; align-items: center; gap: 0.25rem; }
.hero-spacer { flex: 1; }
.hero-btn { display: inline-flex; align-items: center; gap: 0.3rem; font-size: 0.75rem; background: var(--surface-2); border: 1px solid var(--border-strong); border-radius: var(--radius-md); color: var(--text); padding: 0.3rem 0.55rem; cursor: pointer; }
.hero-btn--danger { color: var(--danger-text, #e5484d); }
.hero-btn:disabled { opacity: 0.5; }
.teach-line { color: var(--ok-text, #2f9e6e); }
.b-tag-x { background: none; border: none; color: var(--text-faint); cursor: pointer; padding: 0 0 0 0.15rem; }
.b-tag--add { cursor: pointer; border-style: dashed; }
.brain-sec-btn {
  display: inline-flex; align-items: center; gap: 0.3rem;
  font-size: 0.75rem; color: var(--text-faint); background: none;
  border: 1px solid var(--border-strong); border-radius: var(--radius-md);
  padding: 0.3rem 0.6rem; cursor: pointer;
}
.brain-sec-btn:hover { color: var(--text); }
.brain-close { background: none; border: none; color: var(--text-faint); cursor: pointer; }
.brain-close:hover { color: var(--text); }

.brain-body { flex: 1; display: flex; min-height: 0; }
.brain-restart-banner { display: flex; align-items: center; gap: 0.8rem; padding: 0.6rem 1rem; background: var(--warn-bg, rgba(217,164,65,0.15)); color: var(--warn, #b8860b); font-size: 0.82rem; border-bottom: 1px solid var(--border); }
.brb-btn { background: var(--accent); color: var(--accent-contrast, #fff); border: none; border-radius: var(--radius-md); padding: 0.35rem 0.8rem; font-size: 0.78rem; cursor: pointer; margin-left: auto; }

/* rail */
.brain-rail {
  width: 15rem; border-right: 1px solid var(--border); padding: 0.75rem 0.6rem;
  display: flex; flex-direction: column; gap: 0.25rem; overflow-y: auto;
  background: var(--surface-2);
}
.rail-item {
  display: flex; align-items: center; gap: 0.55rem;
  background: none; border: none; border-radius: var(--radius-md);
  padding: 0.45rem 0.55rem; cursor: pointer; color: var(--text);
  text-align: left;
}
.rail-item:hover { background: var(--surface-hover, var(--surface)); }
.rail-item--active { background: var(--surface); box-shadow: inset 0 0 0 1px var(--border-strong); }
.rail-avatar {
  width: 28px; height: 28px; border-radius: 50%; flex-shrink: 0;
  display: inline-flex; align-items: center; justify-content: center;
  background: var(--accent); color: var(--accent-contrast, #fff);
  font-size: 0.7rem; font-weight: 700;
}
.rail-avatar--skills { background: var(--surface); color: var(--accent); border: 1px solid var(--accent); }
.rail-label { flex: 1; font-size: 0.83rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rail-count { font-size: 0.7rem; color: var(--text-faint); }
.rail-role { font-size: 0.62rem; text-transform: uppercase; letter-spacing: 0.04em; padding: 0.1rem 0.4rem; border-radius: 999px; border: 1px solid var(--border-strong); color: var(--text-faint); }
.rail-role--owner { color: var(--ok-text, #2f9e6e); border-color: currentColor; }
.rail-role--family { color: var(--accent); border-color: currentColor; }
.rail-role--minor { color: var(--warn, #d9a441); border-color: currentColor; }
.rail-sep { font-size: 0.66rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-faint); margin: 0.6rem 0.4rem 0.15rem; }
.rail-locked { font-size: 0.72rem; color: var(--warn, #d9a441); padding: 0.3rem 0.4rem; }
.rail-unlock, .rail-add { display: flex; flex-direction: column; gap: 0.35rem; padding: 0.3rem 0.4rem; }
.rail-input { background: var(--surface); border: 1px solid var(--border-strong); border-radius: var(--radius-md); color: var(--text); padding: 0.35rem 0.45rem; font-size: 0.78rem; }
.rail-btn { background: var(--accent); color: var(--accent-contrast, #fff); border: none; border-radius: var(--radius-md); padding: 0.4rem; font-size: 0.78rem; cursor: pointer; }
.rail-btn:disabled { opacity: 0.5; }
.rail-err { color: var(--danger-text, #e5484d); font-size: 0.72rem; margin: 0; }

/* content */
.brain-content { flex: 1; overflow-y: auto; padding: 1.1rem 1.35rem 1.5rem; }
.brain-content--graph { display: flex; flex-direction: column; padding: 0.9rem; overflow: hidden; }
.content-title { font-size: 0.8rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-faint); margin: 0 0 0.5rem; }
.content-title--spaced { margin-top: 1.4rem; }
.content-hint { font-size: 0.78rem; color: var(--text-faint); margin: 0 0 0.7rem; }
.person-link { background: none; border: none; padding: 0; cursor: pointer; color: var(--accent); font: inherit; text-transform: none; letter-spacing: normal; font-weight: 600; }

.skill-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(15rem, 1fr)); gap: 0.6rem; }
.b-skill-card {
  border: 1px solid var(--border-strong); border-radius: var(--radius-lg);
  background: var(--surface-2); padding: 0.7rem 0.8rem;
  display: flex; flex-direction: column; gap: 0.35rem;
  transition: transform 0.08s ease, box-shadow 0.08s ease;
}
.b-skill-card:hover { transform: translateY(-1px); box-shadow: var(--shadow-sm, 0 2px 8px rgba(0,0,0,0.12)); }
.b-skill-card--off { opacity: 0.5; }
.b-skill-head { display: flex; align-items: center; gap: 0.4rem; }
.b-skill-name { font-family: ui-monospace, monospace; font-weight: 600; font-size: 0.8rem; flex: 1; }
.b-skill-desc { margin: 0; font-size: 0.75rem; color: var(--text-faint); }
.b-skill-tags { display: flex; flex-wrap: wrap; gap: 0.25rem; }
.b-tag { font-size: 0.65rem; padding: 0.08rem 0.4rem; border-radius: 999px; border: 1px solid var(--border); color: var(--text-faint); }
.b-icon-btn { background: none; border: none; color: var(--text-faint); cursor: pointer; padding: 0.1rem; }
.b-icon-btn:hover { color: var(--text); }

/* person hero */
.person-hero { display: flex; align-items: center; gap: 0.8rem; margin-bottom: 1.1rem; }
.hero-avatar {
  width: 46px; height: 46px; border-radius: 50%;
  display: inline-flex; align-items: center; justify-content: center;
  background: var(--accent); color: var(--accent-contrast, #fff);
  font-size: 1rem; font-weight: 700;
}
.hero-name { margin: 0; font-size: 1.05rem; }
.hero-meta { display: flex; align-items: center; gap: 0.6rem; }

.fact-chips { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 0.6rem; }
.fact-chip {
  display: inline-flex; align-items: center; gap: 0.35rem;
  font-size: 0.75rem; padding: 0.25rem 0.6rem; border-radius: 999px;
  background: var(--surface-2); border: 1px solid var(--border-strong);
}
.fact-chip em { font-style: normal; color: var(--accent); }
.fact-chip--source em { color: var(--ok-text, #2f9e6e); }
.file-hidden { display: none; }

/* U112: person tabs */
.person-tabs {
  display: flex; gap: 0.25rem; margin: 0.6rem 0 0.8rem;
  border-bottom: 1px solid var(--border-strong);
}
.person-tab {
  background: none; border: none; border-bottom: 2px solid transparent;
  padding: 0.35rem 0.7rem; font-size: 0.8rem; color: var(--text-faint);
  cursor: pointer; display: inline-flex; align-items: center; gap: 0.3rem;
}
.person-tab:hover { color: var(--text); }
.person-tab--active { color: var(--accent); border-bottom-color: var(--accent); font-weight: 600; }
.person-tab-count {
  font-size: 0.62rem; padding: 0 0.35rem; border-radius: 999px;
  background: var(--surface-2); border: 1px solid var(--border);
}

/* U112: hero ⋯ menu */
.hero-menu-wrap { position: relative; }
.hero-menu {
  position: absolute; right: 0; top: calc(100% + 4px); z-index: 20;
  background: var(--surface); border: 1px solid var(--border-strong);
  border-radius: var(--radius-md); box-shadow: var(--shadow-modal);
  display: flex; flex-direction: column; min-width: 13rem; padding: 0.25rem;
}
.hero-menu-item {
  background: none; border: none; text-align: left; padding: 0.45rem 0.6rem;
  font-size: 0.78rem; color: var(--text); cursor: pointer; border-radius: var(--radius-sm);
}
.hero-menu-item:hover { background: var(--surface-2); }
.hero-menu-item--danger { color: var(--danger-text, #e5484d); }

/* U112: source chips with icons */
.chip-icon { flex-shrink: 0; opacity: 0.8; }
.chip-muted { font-size: 0.6rem; opacity: 0.7; }
.rail-btn--ghost { background: none; border-style: dashed; }

/* U117: grouped facts */
.fact-filter { width: 100%; margin-bottom: 0.4rem; }
.fact-group { margin-bottom: 0.45rem; }
.fact-group-title {
  margin: 0 0 0.25rem; font-size: 0.68rem; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.04em; color: var(--accent);
}
.fact-group-count { color: var(--text-faint); font-weight: 400; }
.fact-more {
  font-size: 0.68rem; padding: 0.1rem 0.5rem; border-radius: 999px;
  background: none; border: 1px dashed var(--border-strong);
  color: var(--text-faint); cursor: pointer;
}
.fact-more:hover { color: var(--text); border-color: var(--accent); }

/* U117: skills managed in the brain panel */
.skill-suggest {
  display: flex; flex-wrap: wrap; gap: 0.4rem; align-items: center;
  padding: 0.5rem 0.65rem; margin-bottom: 0.6rem; font-size: 0.76rem;
  border: 1px solid var(--accent); border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--accent) 8%, transparent);
}
.suggest-plus { font-style: normal; color: var(--accent); font-weight: 700; }
.b-uses { font-size: 0.64rem; color: var(--text-faint); }
.b-skill-body { width: 100%; font-family: ui-monospace, monospace; resize: vertical; }
.b-btn--ghost { background: none; border: 1px solid var(--border-strong); color: var(--text); }
.b-btn--danger { background: none; border: 1px solid var(--danger-text, #e5484d); color: var(--danger-text, #e5484d); }
.skill-editor-inline { display: flex; flex-direction: column; gap: 0.45rem; margin-top: 0.6rem; }
.skill-opt {
  margin-top: 0.6rem; padding: 0.6rem; border: 1px dashed var(--accent);
  border-radius: var(--radius-md); background: var(--surface); display: flex;
  flex-direction: column; gap: 0.5rem;
}
.skill-opt-head { margin: 0; font-size: 0.76rem; }
.skill-opt-diff { display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; }
@media (max-width: 700px) { .skill-opt-diff { grid-template-columns: 1fr; } }
.skill-opt-col { display: flex; flex-direction: column; gap: 0.25rem; min-width: 0; }
.skill-opt-label { font-size: 0.66rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--text-faint); }
.skill-opt-pre {
  margin: 0; padding: 0.45rem; font-size: 0.7rem; line-height: 1.35;
  font-family: ui-monospace, monospace; white-space: pre-wrap; word-break: break-word;
  background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm);
  max-height: 14rem; overflow-y: auto;
}
.skill-opt-pre--new { border-color: var(--accent); }
.refresh-toggle {
  display: inline-flex; align-items: center; gap: 0.3rem;
  font-size: 0.72rem; color: var(--text-faint); cursor: pointer; user-select: none;
}
.chip-x { background: none; border: none; color: var(--text-faint); cursor: pointer; padding: 0; display: inline-flex; }
.chip-x:hover { color: var(--danger-text, #e5484d); }

.inline-add { display: flex; gap: 0.45rem; margin-top: 0.6rem; }
.b-input {
  background: var(--surface-2); border: 1px solid var(--border-strong);
  border-radius: var(--radius-md); color: var(--text);
  padding: 0.4rem 0.55rem; font-size: 0.78rem; min-width: 8rem;
}
.b-grow { flex: 1; }
.b-about { width: 100%; resize: vertical; }
.b-memory { width: 100%; resize: vertical; font-size: 0.78rem; line-height: 1.4; white-space: pre-wrap; }
.b-btn {
  background: var(--accent); color: var(--accent-contrast, #fff);
  border: none; border-radius: var(--radius-md); padding: 0.4rem 0.8rem;
  font-size: 0.78rem; cursor: pointer;
}
.b-btn:disabled { opacity: 0.5; cursor: default; }
.b-error { color: var(--danger-text, #e5484d); font-size: 0.75rem; margin: 0.3rem 0 0; }
</style>
