<template>
  <div :class="docked ? 'brain-docked' : 'brain-overlay'" @click.self="onBackdrop">
    <div :class="docked ? 'brain-dock-inner' : 'brain-modal'">
      <header class="brain-header">
        <span class="brain-title"><Brain :size="17" /> {{ prefs.assistantName }}'s brain</span>
        <button class="brain-sec-btn" @click="$emit('open-knowledge')">
          <ShieldCheck :size="13" /> Security &amp; faces
        </button>
        <button v-if="!docked" class="brain-close" aria-label="Close" @click="$emit('close')"><X :size="15" /></button>
      </header>

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
          <p v-if="store.locked" class="rail-locked">
            Profiles are locked — unlock via Security &amp; faces.
          </p>
        </nav>

        <!-- ── Right: skills library ── -->
        <section v-if="selected === '_skills'" class="brain-content">
          <h3 class="content-title">General skills</h3>
          <p class="content-hint">Procedures that apply to everyone. Teach new ones with the 🎓 button, or add below.</p>
          <div class="skill-grid">
            <article v-for="sk in generalSkills" :key="sk.name" :class="['b-skill-card', !sk.enabled && 'b-skill-card--off']">
              <header class="b-skill-head">
                <span class="b-skill-name">{{ sk.name }}</span>
                <button class="b-icon-btn" title="Edit in Settings" @click="nav.openSkills(sk.name)"><Pencil :size="12" /></button>
              </header>
              <p class="b-skill-desc"><WikiText :text="sk.description" @open="openTarget" /></p>
              <div class="b-skill-tags">
                <span v-for="t in sk.triggers.slice(0, 4)" :key="t" class="b-tag">“{{ t }}”</span>
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
                  <button class="b-icon-btn" title="Edit in Settings" @click="nav.openSkills(sk.name)"><Pencil :size="12" /></button>
                </header>
                <p class="b-skill-desc"><WikiText :text="sk.description" @open="openTarget" /></p>
              </article>
            </div>
          </template>

          <div class="inline-add">
            <input v-model="newSkill.name" class="b-input" placeholder="skill-name" aria-label="Skill name" />
            <input v-model="newSkill.description" class="b-input b-grow" placeholder="What it covers" aria-label="Skill description" />
            <input v-model="newSkill.body" class="b-input b-grow" placeholder="The procedure…" aria-label="Skill procedure" />
            <button class="b-btn" :disabled="!newSkill.name.trim() || !newSkill.body.trim()" @click="addSkill()">Add skill</button>
          </div>
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
          </div>

          <h3 class="content-title">About</h3>
          <textarea
            v-model="aboutDraft" class="b-input b-about" rows="2"
            placeholder="Who is this person to you? Style, preferences… Link with [[skill-name]]."
            aria-label="About this person" @blur="saveAbout"
          />
          <p v-if="aboutDraft.includes('[[')" class="content-hint"><WikiText :text="aboutDraft" @open="openTarget" /></p>

          <h3 class="content-title content-title--spaced">Facts</h3>
          <div class="fact-chips">
            <span v-for="f in store.detail.facts" :key="f.fact_id" class="fact-chip">
              <em>{{ f.key }}</em> {{ f.value }}
              <button class="chip-x" :aria-label="`Delete ${f.key}`" @click="store.deleteFact(f.fact_id, store.detail!.person.person_id)"><X :size="10" /></button>
            </span>
          </div>
          <div class="inline-add">
            <input v-model="newFact.key" class="b-input" placeholder="what (e.g. hobby)" aria-label="Fact key" />
            <input v-model="newFact.value" class="b-input b-grow" placeholder="answer (e.g. cycling)" aria-label="Fact value" />
            <button class="b-btn" :disabled="!newFact.key.trim() || !newFact.value.trim()" @click="addFact()">Add fact</button>
          </div>

          <h3 class="content-title content-title--spaced">Their way of working</h3>
          <div class="skill-grid">
            <article v-for="sk in store.detail.skills ?? []" :key="sk.name" :class="['b-skill-card', !sk.enabled && 'b-skill-card--off']">
              <header class="b-skill-head">
                <span class="b-skill-name">{{ sk.name }}</span>
                <span v-if="(sk as any).via === 'mention'" class="b-tag" title="Mentions this person via a [[link]]">backlink</span>
                <button class="b-icon-btn" title="Edit in Settings" @click="nav.openSkills(sk.name)"><Pencil :size="12" /></button>
              </header>
              <p class="b-skill-desc">{{ sk.description }}</p>
            </article>
          </div>
          <div class="inline-add">
            <input v-model="newSkill.name" class="b-input" placeholder="skill-name" aria-label="Skill name" />
            <input v-model="newSkill.body" class="b-input b-grow" :placeholder="`How ${store.detail.person.display_name} wants this done…`" aria-label="Skill procedure" />
            <button class="b-btn" :disabled="!newSkill.name.trim() || !newSkill.body.trim()" @click="addSkill(store.detail.person.person_id)">Add skill</button>
          </div>
          <p v-if="addError" class="b-error">{{ addError }}</p>
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
import { Brain, Pencil, Share2, ShieldCheck, Sparkles, X } from 'lucide-vue-next'
import BrainGraph from './BrainGraph.vue'
import WikiText from './WikiText.vue'
import { useKnowledgeStore } from '../stores/knowledgeStore'
import { useNavStore } from '../stores/navStore'
import { usePrefsStore } from '../stores/prefsStore'

const props = defineProps<{ docked?: boolean }>()
const emit = defineEmits<{ (e: 'close'): void; (e: 'open-knowledge'): void }>()

function onBackdrop(): void {
  if (!props.docked) emit('close')
}

const store = useKnowledgeStore()
const prefs = usePrefsStore()
const nav = useNavStore()

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
  } catch { skills.value = [] }
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
  else nav.openSkills(id)
}

async function select(id: string): Promise<void> {
  selected.value = id
  addError.value = ''
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
  await Promise.all([store.fetchPeople(), fetchSkills()])
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
.rail-locked { font-size: 0.72rem; color: var(--warn, #d9a441); padding: 0.4rem; }

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
.b-btn {
  background: var(--accent); color: var(--accent-contrast, #fff);
  border: none; border-radius: var(--radius-md); padding: 0.4rem 0.8rem;
  font-size: 0.78rem; cursor: pointer;
}
.b-btn:disabled { opacity: 0.5; cursor: default; }
.b-error { color: var(--danger-text, #e5484d); font-size: 0.75rem; margin: 0.3rem 0 0; }
</style>
