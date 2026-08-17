<template>
  <main class="d2-main skills">
    <div class="skills-inner">
      <div class="skills-head">
        <h2>Skills</h2>
        <span class="head-note">Procedures he has learned. Teach a new one from any conversation.</span>
        <span class="head-spacer" />
        <button class="d2-ghost-btn" @click="startNew">+ New skill</button>
      </div>

      <!-- ═══ U251: proposals he raised HIMSELF, waiting for an answer ═══ -->
      <section v-for="p in proposals" :key="p.id" class="proposal skill-opt--raised">
        <p class="proposal-head">
          <span class="raised-badge">{{ p.kind === 'new' ? 'New skill' : 'Rewrite' }}</span>
          <strong>{{ p.skill }}</strong> — {{ p.reason }}
        </p>
        <p v-if="p.rationale" class="hint">{{ p.rationale }}</p>
        <p v-if="p.kind === 'new'" class="hint">
          {{ p.description }}
          <template v-if="p.triggers?.length">
            · triggers: <span v-for="t in p.triggers" :key="t" class="trigger-chip">“{{ t }}”</span>
          </template>
        </p>
        <div class="diff">
          <div v-if="p.kind !== 'new'" class="diff-col">
            <span class="diff-label">Current</span>
            <pre class="diff-pre">{{ p.current_body }}</pre>
          </div>
          <div class="diff-col">
            <span class="diff-label">{{ p.kind === 'new' ? 'Proposed skill' : 'Proposed' }}</span>
            <pre class="diff-pre new">{{ p.proposed_body }}</pre>
          </div>
        </div>
        <div class="proposal-actions">
          <button class="d2-primary-btn" :disabled="applyingProposal === p.id" @click="acceptProposal(p)">
            {{ p.kind === 'new' ? 'Add this skill' : 'Apply rewrite' }}
          </button>
          <button class="d2-ghost-btn" :disabled="applyingProposal === p.id" @click="editProposal(p)">Edit first</button>
          <button class="d2-ghost-btn" :disabled="applyingProposal === p.id" @click="dismissProposal(p)">No thanks</button>
        </div>
      </section>

      <!-- ═══ Editor ═══ -->
      <section v-if="editorOpen" class="editor">
        <div class="editor-head">
          <h3>{{ editorIsNew ? 'New skill' : `Edit skill` }}</h3>
          <span v-if="!editorIsNew" class="mono editor-meta">{{ draft.name }}{{ metrics[draft.name] ? ` · used ${metrics[draft.name].uses}×` : '' }}</span>
          <span class="head-spacer" />
          <button class="editor-x" title="Close without saving" @click="editorOpen = false">✕</button>
        </div>
        <div class="editor-row">
          <label class="editor-field">
            <span>Name</span>
            <input v-model="draft.name" class="d2-field" :disabled="!editorIsNew" placeholder="kebab-case" aria-label="Skill name">
          </label>
          <label class="editor-field">
            <span>Who may use it</span>
            <select v-model="draft.person" class="d2-field" aria-label="Who may use it">
              <option value="">Everyone</option>
              <option v-for="p in knowledge.people" :key="p.person_id" :value="p.person_id">{{ p.display_name }} only</option>
            </select>
          </label>
          <label class="editor-field">
            <span>Modes</span>
            <select v-model="draftModes" class="d2-field" aria-label="Modes">
              <option value="">Any mode</option>
              <option value="home">Home only</option>
              <option value="work">Work only</option>
              <option value="home,work">Home and Work</option>
              <option value="presentation">Present only</option>
            </select>
          </label>
        </div>
        <label class="editor-field wide">
          <span>Description</span>
          <input v-model="draft.description" class="d2-field" placeholder="One line — what this is for" aria-label="Description">
        </label>
        <div class="editor-triggers">
          <span class="editor-label">Triggers</span>
          <div class="trigger-row">
            <span v-for="(t, i) in draft.triggers" :key="t" class="trigger-chip removable">
              “{{ t }}”
              <button aria-label="Remove trigger" class="chip-x" @click="draft.triggers.splice(i, 1)">✕</button>
            </span>
            <input
              v-model="newTrigger" class="trigger-add" placeholder="+ trigger"
              aria-label="Add a trigger" @keydown.enter.prevent="addTrigger"
            >
          </div>
        </div>
        <div class="editor-body-wrap">
          <span class="editor-label">The procedure <em>plain steps — he reads them like instructions, not code</em></span>
          <textarea v-model="draft.body" rows="8" aria-label="Skill procedure" class="mono editor-body" />
        </div>
        <div class="editor-foot">
          <label class="polish-label" title="Rewrite your draft into tight, executable steps before saving">
            <input v-model="polishOnSave" type="checkbox"> ✨ polish on save
          </label>
          <span class="head-spacer" />
          <button class="d2-ghost-btn" :disabled="!draft.triggers.length" title="Run the first trigger as a real turn, in Talk" @click="testNow">Test it now</button>
          <button class="d2-primary-btn" :disabled="!draft.name.trim() || !draft.body.trim() || saving" @click="saveSkill">Save skill</button>
        </div>
        <p v-if="editorError" class="editor-error">{{ editorError }}</p>
      </section>

      <!-- ═══ Optimize suggestions — failing skills first, with the reason ═══ -->
      <div v-if="suggestions.length" class="suggest-banner">
        <Sparkles :size="15" class="suggest-icon" />
        <span class="suggest-text">
          <template v-if="suggestions.some(s => s.blocked_by_failure)">
            <strong>{{ suggestions.filter(s => s.blocked_by_failure).length }} skill{{ suggestions.filter(s => s.blocked_by_failure).length === 1 ? '' : 's' }} kept failing.</strong>
          </template>
          <template v-else>
            <strong>{{ suggestions.length }} skill{{ suggestions.length === 1 ? '' : 's' }}</strong> learned from how you corrected {{ suggestions.length === 1 ? 'it' : 'them' }}. Fold it in?
          </template>
        </span>
        <button
          v-for="s in suggestions" :key="s.name"
          class="suggest-chip" :class="{ warn: s.blocked_by_failure }" :title="s.reason"
          :disabled="optimizing === s.name" @click="optimize(s.name)"
        >
          {{ s.name }} <em>{{ s.blocked_by_failure ? `${s.blocked}× blocked` : `+${s.new_since_optimized}` }}</em>
        </button>
      </div>

      <!-- Optimize result: before/after diff, owner applies -->
      <section v-if="optimizeResult" class="proposal">
        <p class="proposal-head">
          <strong>{{ optimizeResult.name }}</strong> — proposed rewrite, based on {{ optimizeResult.based_on }} use(s). {{ optimizeResult.rationale }}
        </p>
        <p v-if="!optimizeResult.changed" class="hint">Already optimal — nothing to change.</p>
        <div v-else class="diff">
          <div class="diff-col"><span class="diff-label">Current</span><pre class="diff-pre">{{ optimizeResult.current_body }}</pre></div>
          <div class="diff-col"><span class="diff-label">Proposed</span><pre class="diff-pre new">{{ optimizeResult.proposed_body }}</pre></div>
        </div>
        <div class="proposal-actions">
          <button v-if="optimizeResult.changed" class="d2-primary-btn" @click="applyOptimize">Apply rewrite</button>
          <button class="d2-ghost-btn" @click="optimizeResult = null">Dismiss</button>
        </div>
      </section>
      <p v-if="optimizeNote" class="editor-error">{{ optimizeNote }}</p>

      <!-- ═══ The library ═══ -->
      <div class="cards">
        <article v-for="sk in skills" :key="sk.name" class="card" :class="{ off: !sk.enabled }">
          <header class="card-head">
            <span class="card-name">{{ sk.name }}</span>
            <span class="scope-pill" :class="scopeClass(sk)">{{ scopeLabel(sk) }}</span>
          </header>
          <p class="card-desc">
            <WikiText :text="sk.description" @open="openTarget" />
          </p>
          <div class="card-triggers">
            <span v-for="t in sk.triggers" :key="t" class="trigger-chip" title="Trigger word — he uses this skill when your request contains it">“{{ t }}”</span>
          </div>
          <div class="card-foot">
            <span class="mono card-uses">{{ metrics[sk.name] ? `${metrics[sk.name].uses}×` : '' }}</span>
            <span class="head-spacer" />
            <button class="card-edit" title="Optimize — rewrite from real usage (you approve the diff)"
                    :disabled="optimizing === sk.name" @click="optimize(sk.name)"><Sparkles :size="13" /></button>
            <button class="card-edit" title="Edit this skill" @click="startEdit(sk)"><Pencil :size="13" /></button>
          </div>
        </article>
        <p v-if="!skills.length" class="hint">No skills yet — teach one with 🎓 in Talk, or start from “+ New skill”.</p>
      </div>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { Pencil, Sparkles } from 'lucide-vue-next'
import WikiText from '../components/WikiText.vue'
import { BRAIN_URL } from '../lib/endpoints'
import { useConversationStore } from '../stores/conversationStore'
import { useKnowledgeStore } from '../stores/knowledgeStore'
import { useNavStore } from '../stores/navStore'

const knowledge = useKnowledgeStore()
const nav = useNavStore()
const convo = useConversationStore()

interface SkillItem {
  name: string; description: string; triggers: string[]
  personas: string[]; person: string; enabled: boolean; body: string
}
interface SkillMetric { uses: number; new_since_optimized: number; last_used: number | null }
interface Suggestion { name: string; new_since_optimized: number; blocked?: number; blocked_by_failure?: boolean; reason?: string }
interface RaisedProposal {
  id: string; kind: 'rewrite' | 'new'; skill: string; reason: string; rationale: string
  description?: string; triggers?: string[]; current_body: string; proposed_body: string
}
interface OptimizeResult {
  name: string; changed: boolean; rationale: string
  current_body: string; proposed_body: string; based_on: number
}

const skills = ref<SkillItem[]>([])
const metrics = ref<Record<string, SkillMetric>>({})
const suggestions = ref<Suggestion[]>([])
const proposals = ref<RaisedProposal[]>([])

async function fetchSkills(): Promise<void> {
  try {
    const resp = await fetch(`${BRAIN_URL}/skills`)
    skills.value = (await resp.json()).skills ?? []
    const entries = await Promise.all(skills.value.map(async (sk) => {
      try {
        const m = await fetch(`${BRAIN_URL}/skills/${encodeURIComponent(sk.name)}/metrics`)
        return m.ok ? [sk.name, await m.json()] as const : null
      } catch { return null }
    }))
    metrics.value = Object.fromEntries(entries.filter(Boolean) as [string, SkillMetric][])
    try {
      const s = await fetch(`${BRAIN_URL}/skills/suggestions`)
      suggestions.value = s.ok ? (await s.json()).suggestions ?? [] : []
    } catch { suggestions.value = [] }
    try {
      const p = await fetch(`${BRAIN_URL}/skills/proposals`)
      proposals.value = p.ok ? (await p.json()).proposals ?? [] : []
    } catch { proposals.value = [] }
  } catch { skills.value = [] }
}
onMounted(fetchSkills)

// [[wikilink]] requests from other views: open that skill in the editor.
watch(() => nav.skillsRequest, (r) => {
  if (!r?.skillName) return
  const sk = skills.value.find(s => s.name === r.skillName)
  if (sk) startEdit(sk)
}, { immediate: false })

function scopeLabel(sk: SkillItem): string {
  if (sk.person) return knowledge.people.find(p => p.person_id === sk.person)?.display_name ?? sk.person
  if (sk.personas.length === 1) return `${sk.personas[0] === 'presentation' ? 'Present' : sk.personas[0]} only`
  if (sk.personas.length) return sk.personas.join(' + ')
  return 'Everyone'
}
function scopeClass(sk: SkillItem): string {
  if (sk.person) return 'person'
  if (sk.personas.length) return 'mode'
  return 'all'
}
function openTarget(target: string): void {
  if (knowledge.people.some(p => p.person_id === target)) nav.openPerson(target)
  else {
    const sk = skills.value.find(s => s.name === target)
    if (sk) startEdit(sk)
  }
}

// ── Editor ─────────────────────────────────────────────────────────────────
const editorOpen = ref(false)
const editorIsNew = ref(false)
const draft = reactive<SkillItem>({ name: '', description: '', triggers: [], personas: [], person: '', enabled: true, body: '' })
const draftModes = ref('')
const newTrigger = ref('')
const polishOnSave = ref(false)
const saving = ref(false)
const editorError = ref('')

function startNew(): void {
  Object.assign(draft, { name: '', description: '', triggers: [], personas: [], person: '', enabled: true, body: '' })
  draftModes.value = ''
  editorIsNew.value = true
  editorOpen.value = true
}
function startEdit(sk: SkillItem): void {
  Object.assign(draft, { ...sk, triggers: [...sk.triggers], personas: [...sk.personas] })
  draftModes.value = sk.personas.join(',')
  editorIsNew.value = false
  editorOpen.value = true
}
function addTrigger(): void {
  const t = newTrigger.value.trim().toLowerCase()
  if (t && !draft.triggers.includes(t)) draft.triggers.push(t)
  newTrigger.value = ''
}
async function saveSkill(): Promise<void> {
  saving.value = true
  editorError.value = ''
  try {
    const resp = await fetch(`${BRAIN_URL}/skills`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...draft,
        name: draft.name.trim().toLowerCase().replace(/\s+/g, '-'),
        personas: draftModes.value ? draftModes.value.split(',') : [],
        polish: polishOnSave.value,
      }),
    })
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}))
      editorError.value = body.error ?? `Save failed (${resp.status})`
      return
    }
    editorOpen.value = false
    await fetchSkills()
  } catch { editorError.value = 'Could not reach the brain.' } finally { saving.value = false }
}
function testNow(): void {
  const trigger = draft.triggers[0]
  if (!trigger) return
  convo.submitTurn(trigger)
  nav.go('talk')
}

// ── Optimize (owner-approved rewrite from real usage) ──────────────────────
const optimizing = ref('')
const optimizeNote = ref('')
const optimizeResult = ref<OptimizeResult | null>(null)
async function optimize(name: string): Promise<void> {
  optimizing.value = name
  optimizeNote.value = ''
  optimizeResult.value = null
  try {
    const resp = await fetch(`${BRAIN_URL}/skills/${encodeURIComponent(name)}/optimize`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}),
    }).catch(() => null)
    if (!resp || !resp.ok) {
      optimizeNote.value = resp ? String((await resp.json().catch(() => ({}))).error ?? `HTTP ${resp.status}`) : 'brain unreachable'
      return
    }
    optimizeResult.value = await resp.json()
    // "Already optimal" consumes the signals server-side — refresh the badge.
    if (optimizeResult.value && !optimizeResult.value.changed) await fetchSkills()
  } finally { optimizing.value = '' }
}
async function applyOptimize(): Promise<void> {
  const prop = optimizeResult.value
  if (!prop) return
  const sk = skills.value.find(s => s.name === prop.name)
  if (!sk) return
  const resp = await fetch(`${BRAIN_URL}/skills`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...sk, body: prop.proposed_body, mark_optimized: true }),
  }).catch(() => null)
  if (resp && resp.ok) {
    optimizeResult.value = null
    await fetchSkills()
  } else optimizeNote.value = 'Could not save the rewrite.'
}

// ── U251: answering a proposal the assistant raised itself ─────────────────
//
// Three answers, and "Edit first" matters as much as the other two: a draft
// written from three of your own sentences is a good starting point and
// rarely the finished thing.
const applyingProposal = ref('')

async function resolveProposal(p: RaisedProposal): Promise<void> {
  await fetch(`${BRAIN_URL}/skills/proposals/${encodeURIComponent(p.id)}`, { method: 'DELETE' }).catch(() => null)
  proposals.value = proposals.value.filter(x => x.id !== p.id)
}
async function acceptProposal(p: RaisedProposal): Promise<void> {
  applyingProposal.value = p.id
  try {
    const existing = skills.value.find(s => s.name === p.skill)
    const payload = p.kind === 'new'
      ? { name: p.skill, description: p.description ?? '', triggers: p.triggers ?? [],
          personas: [], person: '', enabled: true, body: p.proposed_body }
      : { ...existing, body: p.proposed_body, mark_optimized: true }
    if (p.kind !== 'new' && !existing) {
      optimizeNote.value = `${p.skill} no longer exists.`
      await resolveProposal(p)
      return
    }
    const resp = await fetch(`${BRAIN_URL}/skills`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).catch(() => null)
    if (resp && resp.ok) {
      await resolveProposal(p)
      await fetchSkills()
    } else {
      optimizeNote.value = resp
        ? String((await resp.json().catch(() => ({}))).error ?? `HTTP ${resp.status}`)
        : 'brain unreachable'
    }
  } finally { applyingProposal.value = '' }
}
async function editProposal(p: RaisedProposal): Promise<void> {
  const existing = skills.value.find(s => s.name === p.skill)
  Object.assign(draft, {
    name: p.skill,
    description: p.kind === 'new' ? p.description ?? '' : existing?.description ?? '',
    triggers: p.kind === 'new' ? [...(p.triggers ?? [])] : [...(existing?.triggers ?? [])],
    personas: existing?.personas ?? [],
    person: existing?.person ?? '',
    enabled: existing?.enabled ?? true,
    body: p.proposed_body,
  })
  draftModes.value = (existing?.personas ?? []).join(',')
  editorIsNew.value = p.kind === 'new'
  editorOpen.value = true
  // Off the list: it is the owner's draft now, not an open question.
  await resolveProposal(p)
}
async function dismissProposal(p: RaisedProposal): Promise<void> {
  await resolveProposal(p)
}
</script>

<style scoped>
.skills-inner { max-width: 900px; }
.mono { font-family: var(--font-mono); }
.head-spacer { flex: 1; }
.hint { margin: 0 0 6px; font-size: 12.5px; color: var(--ink-2); line-height: 1.45; }

.skills-head { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; flex-wrap: wrap; }
.skills-head h2 { margin: 0; font-size: 19px; }
.head-note { font-size: 13px; color: var(--ink-2); }

.proposal {
  border: 1px solid var(--line); border-radius: 14px; background: var(--surface);
  padding: 14px 16px; margin-bottom: 14px;
}
.skill-opt--raised { border-left: 3px solid var(--accent); }
.proposal-head { margin: 0 0 6px; font-size: 13.5px; }
.raised-badge {
  display: inline-block; margin-right: 6px; padding: 1px 7px;
  font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em;
  border-radius: 999px; background: var(--accent-wash); color: var(--accent);
}
.diff { display: flex; gap: 10px; flex-wrap: wrap; margin: 8px 0; }
.diff-col { flex: 1; min-width: 220px; }
.diff-label {
  display: block; font-size: 10px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.08em; color: var(--ink-3); margin-bottom: 4px;
}
.diff-pre {
  margin: 0; padding: 9px 11px; border: 1px solid var(--line); border-radius: 9px;
  background: var(--sunken); font-family: var(--font-mono); font-size: 11.5px;
  line-height: 1.6; white-space: pre-wrap; word-break: break-word; max-height: 220px; overflow-y: auto;
}
.diff-pre.new { border-color: var(--accent); }
.proposal-actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 4px; }

.editor { border: 1.5px solid var(--accent); border-radius: 14px; background: var(--surface); padding: 16px 18px; margin-bottom: 14px; }
.editor-head { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
.editor-head h3 { margin: 0; font-size: 15px; }
.editor-meta { font-size: 11px; color: var(--ink-3); }
.editor-x { background: none; border: none; color: var(--ink-3); cursor: pointer; font-size: 15px; padding: 0; }
.editor-row { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
.editor-field { flex: 1; min-width: 200px; display: flex; flex-direction: column; gap: 5px; }
.editor-field.wide { margin-bottom: 12px; }
.editor-field span { font-size: 12px; color: var(--ink-3); }
.editor-label { display: block; font-size: 12px; color: var(--ink-3); margin-bottom: 6px; }
.editor-label em { font-style: normal; font-size: 11.5px; }
.editor-triggers { margin-bottom: 12px; }
.trigger-row { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.trigger-chip {
  display: inline-flex; align-items: center; gap: 6px; font-size: 11px;
  padding: 2px 8px; border-radius: 999px; border: 1px solid var(--line-strong); color: var(--ink-3);
}
.trigger-chip.removable { font-size: 12px; padding: 4px 10px; background: var(--surface-2); color: var(--ink); }
.chip-x { background: none; border: none; color: var(--ink-3); cursor: pointer; padding: 0; font-size: 11px; }
.chip-x:hover { color: var(--danger); }
.trigger-add {
  padding: 4px 10px; border-radius: 999px; background: transparent;
  border: 1px dashed var(--line-strong); color: var(--ink-2);
  font-size: 12px; font-family: inherit; outline: none; width: 90px;
}
.editor-body-wrap { margin-bottom: 12px; }
.editor-body {
  width: 100%; box-sizing: border-box; background: var(--sunken);
  border: 1.5px solid var(--line-strong); border-radius: 11px; color: var(--ink);
  padding: 12px 14px; font-size: 12px; line-height: 1.7; resize: vertical;
}
.editor-foot { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.polish-label { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--ink-3); cursor: pointer; }
.editor-error { margin: 8px 0 0; font-size: 12.5px; color: var(--danger); }

.suggest-banner {
  display: flex; align-items: center; gap: 10px; padding: 11px 14px;
  border: 1px solid var(--accent); border-radius: 11px; background: var(--accent-wash);
  margin-bottom: 14px; flex-wrap: wrap;
}
.suggest-icon { color: var(--accent); flex-shrink: 0; }
.suggest-text { font-size: 13px; flex: 1; min-width: 180px; }
.suggest-chip {
  padding: 5px 11px; border-radius: 8px; background: var(--surface);
  border: 1px solid var(--line-strong); color: var(--ink-2);
  font-size: 12px; font-weight: 600; cursor: pointer; font-family: inherit;
}
.suggest-chip em { font-style: normal; color: var(--accent); font-weight: 700; }
.suggest-chip.warn { border-color: var(--danger); color: var(--danger); }
.suggest-chip.warn em { color: inherit; }

.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(290px, 100%), 1fr)); gap: 10px; }
.card {
  border: 1px solid var(--line); border-radius: 12px; background: var(--surface);
  padding: 13px 15px; display: flex; flex-direction: column; gap: 7px; min-width: 0;
}
.card.off { opacity: 0.55; }
.card-head { display: flex; align-items: center; gap: 8px; }
.card-name { font-size: 14px; font-weight: 600; flex: 1; min-width: 0; }
.scope-pill {
  font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em;
  padding: 2px 7px; border-radius: 999px;
}
.scope-pill.person { background: var(--info-wash); color: var(--info); }
.scope-pill.mode { background: var(--warn-wash); color: var(--warn); }
.scope-pill.all { background: var(--sunken); color: var(--ink-3); }
.card-desc { margin: 0; font-size: 12.5px; color: var(--ink-2); line-height: 1.45; }
.card-triggers { display: flex; flex-wrap: wrap; gap: 5px; }
.card-foot { display: flex; align-items: center; gap: 8px; border-top: 1px solid var(--line); padding-top: 7px; }
.card-uses { font-size: 10.5px; color: var(--ink-3); }
.card-edit { background: none; border: none; color: var(--ink-3); cursor: pointer; padding: 2px; display: inline-flex; }
.card-edit:hover { color: var(--accent); }
</style>
