<template>
  <div class="knowledge-overlay" @click.self="$emit('close')">
    <div class="knowledge-modal">
      <div class="knowledge-header">
        <span class="knowledge-title"><Brain :size="16" /> Knowledge — what AURA knows</span>
        <div class="knowledge-header-right">
          <span :class="['tier-badge', store.tier === 'sensitive' ? 'tier-sensitive' : 'tier-benign']">
            <LockOpen v-if="store.tier === 'sensitive'" :size="11" />
            <Lock v-else-if="store.omkLoaded" :size="11" />
            {{ store.tier === 'sensitive' ? 'sensitive' : store.omkLoaded ? 'locked' : 'dev (unencrypted)' }}
          </span>
          <button
            v-if="store.tier === 'sensitive'"
            class="btn-lock"
            title="Drop to benign tier (restart brain with KNOWLEDGE_PASSPHRASE to unlock)"
            @click="store.lock()"
          >Lock</button>
          <button class="btn-close" @click="$emit('close')"><X :size="15" /></button>
        </div>
      </div>

      <div v-if="store.error" class="knowledge-error">{{ store.error }}</div>

      <!-- Secure banner: shown until the knowledge store is encrypted -->
      <div v-if="!store.omkLoaded" class="secure-banner">
        <div class="secure-text">
          <ShieldAlert :size="15" class="secure-icon" />
          <div>
            <strong>Not yet secured.</strong> Set a passphrase to encrypt everything
            AURA knows — this also unlocks <strong>face recognition</strong> so the
            robot can greet you by name.
          </div>
        </div>
        <form class="secure-form" @submit.prevent="doSecure">
          <input v-model="securePass" type="password" class="field-input" placeholder="Choose a passphrase (min 8 chars)" autocomplete="new-password" />
          <label class="secure-remember">
            <input v-model="secureRemember" type="checkbox" /> Remember on this laptop (auto-unlock)
          </label>
          <button class="btn-apply" type="submit" :disabled="securePass.length < 8 || securing">
            {{ securing ? 'Securing…' : 'Secure & enable recognition' }}
          </button>
        </form>
      </div>

      <div class="knowledge-body">
        <!-- Left: people list -->
        <div class="people-col">
          <div class="col-title">People</div>
          <ul class="people-list">
            <li
              v-for="p in store.people"
              :key="p.person_id"
              :class="['person-row', store.detail?.person.person_id === p.person_id && 'person-row--active']"
              @click="store.inspectPerson(p.person_id)"
            >
              <span class="person-name">{{ p.display_name }}</span>
              <span :class="['role-badge', `role-${p.role}`]">{{ p.role }}</span>
            </li>
            <li v-if="store.people.length === 0 && !store.loading" class="empty-hint">
              No people yet. Add one below.
            </li>
          </ul>

          <!-- Unknown visitors (U36f): tag to train recognition -->
          <template v-if="store.sightings.length > 0">
            <div class="col-title">Unknown visitors</div>
            <p class="facts-hint">
              Seen by the robot but not recognized. Tag them to teach AURA —
              kept in memory only, gone after a restart.
            </p>
            <div v-for="s in store.sightings" :key="s.sighting_id" class="sighting-card">
              <img :src="store.sightingImageUrl(s.sighting_id)" class="sighting-img" alt="Unknown visitor" />
              <div class="sighting-meta">
                <span class="sighting-time">
                  {{ s.count }}× · {{ new Date(s.last_seen * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }}
                </span>
                <div class="sighting-actions">
                  <select v-model="tagTargets[s.sighting_id]" class="field-select sighting-select">
                    <option value="" disabled>Who is this?</option>
                    <option v-for="p in store.people" :key="p.person_id" :value="p.person_id">{{ p.display_name }}</option>
                  </select>
                  <button
                    class="btn-apply sighting-btn" :disabled="!tagTargets[s.sighting_id]"
                    title="Tag & train recognition"
                    @click="doTagSighting(s.sighting_id)"
                  ><UserPlus :size="12" /></button>
                  <button class="btn-delete" title="Dismiss" @click="store.dismissSighting(s.sighting_id)">
                    <X :size="12" />
                  </button>
                </div>
              </div>
            </div>
            <p v-if="tagMessage" class="teach-msg">{{ tagMessage }}</p>
          </template>

          <form class="add-person-form" @submit.prevent="addPerson">
            <input v-model="newPersonId" class="field-input" placeholder="id (e.g. jan)" required />
            <input v-model="newPersonName" class="field-input" placeholder="Display name" required />
            <select v-model="newPersonRole" class="field-select">
              <option value="owner">owner</option>
              <option value="family">family</option>
              <option value="guest">guest</option>
              <option value="minor">minor</option>
            </select>
            <button type="submit" class="btn-apply">Add person</button>
          </form>
        </div>

        <!-- Right: person detail -->
        <div class="detail-col">
          <template v-if="store.detail">
            <div class="detail-header">
              <span class="detail-name">{{ store.detail.person.display_name }}</span>
              <button class="btn-forget" @click="confirmForget">Forget person</button>
            </div>
            <p v-if="store.detail.person.role === 'minor'" class="minor-note">
              Minor — explicit facts only; no passive learning without consent (ADR-008 §10).
            </p>

            <!-- Teach face: look at the robot, click, done -->
            <div v-if="store.recognitionEnabled" class="teach-face-row">
              <button class="btn-teach" :disabled="teaching" @click="doTeachFace">
                <ScanFace :size="14" />
                {{ teaching ? 'Looking…' : `Teach ${store.detail.person.display_name}'s face` }}
              </button>
              <span class="teach-hint">Look straight at the robot's camera, then click.</span>
            </div>
            <p v-if="teachMessage" class="teach-msg">{{ teachMessage }}</p>

            <div class="col-title">Facts</div>
            <p class="facts-hint">
              Things AURA should remember — they make greetings and conversations
              personal. Example: <em>favorite coffee</em> → <em>espresso</em>.
            </p>
            <ul class="fact-list">
              <li v-for="f in store.detail.facts" :key="f.fact_id" class="fact-row">
                <span class="fact-key">{{ f.key }}</span>
                <span class="fact-value">{{ f.value }}</span>
                <button class="btn-delete" title="Delete fact (step-up when encrypted)" @click="store.deleteFact(f.fact_id, store.detail!.person.person_id)"><X :size="12" /></button>
              </li>
              <li v-if="store.detail.facts.length === 0" class="empty-hint">No facts recorded.</li>
            </ul>

            <div class="fact-suggestions">
              <button
                v-for="s in factSuggestions" :key="s" type="button" class="fact-chip"
                @click="newFactKey = s"
              >{{ s }}</button>
            </div>
            <form class="add-fact-form" @submit.prevent="addFact">
              <input v-model="newFactKey" class="field-input" placeholder="what (e.g. hobby)" required />
              <input v-model="newFactValue" class="field-input" placeholder="answer (e.g. cycling)" required />
              <button type="submit" class="btn-apply">Add</button>
            </form>

            <div class="col-title">Observed signals <span class="provenance-hint">(learned, decaying)</span></div>
            <ul class="fact-list">
              <li v-for="s in store.detail.signals" :key="s.signal_id" class="fact-row">
                <span class="fact-key">{{ s.kind }}</span>
                <span class="fact-value">{{ s.value }}</span>
                <span class="signal-meta">{{ Math.round(s.confidence * 100) }}% · {{ s.evidence_count }}×</span>
              </li>
              <li v-if="store.detail.signals.length === 0" class="empty-hint">No observed signals.</li>
            </ul>
          </template>
          <div v-else class="empty-hint detail-placeholder">
            Select a person to inspect everything AURA knows about them.
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { Brain, Lock, LockOpen, ScanFace, ShieldAlert, UserPlus, X } from 'lucide-vue-next'
import { useKnowledgeStore } from '../stores/knowledgeStore'

defineEmits<{ close: [] }>()

const store = useKnowledgeStore()

const newPersonId = ref('')
const newPersonName = ref('')
const newPersonRole = ref('guest')
const newFactKey = ref('')
const newFactValue = ref('')

const factSuggestions = ['favorite coffee', 'hobby', 'birthday', 'works on', 'favorite music']

const securePass = ref('')
const secureRemember = ref(true)
const securing = ref(false)
const teaching = ref(false)
const teachMessage = ref('')

async function doSecure() {
  securing.value = true
  try {
    const ok = await store.secure(securePass.value, secureRemember.value)
    if (ok) securePass.value = ''
  } finally {
    securing.value = false
  }
}

async function doTeachFace() {
  if (!store.detail) return
  teaching.value = true
  teachMessage.value = ''
  try {
    teachMessage.value = await store.teachFace(store.detail.person.person_id)
  } finally {
    teaching.value = false
  }
}

const tagTargets = ref<Record<string, string>>({})
const tagMessage = ref('')

async function doTagSighting(sightingId: string) {
  const personId = tagTargets.value[sightingId]
  if (!personId) return
  tagMessage.value = await store.tagSighting(sightingId, personId)
}

let sightingsTimer: ReturnType<typeof setInterval> | null = null

onMounted(async () => {
  await store.fetchTier()
  await store.fetchPeople()
  await store.fetchRecognition()
  await store.fetchSightings()
  sightingsTimer = setInterval(() => store.fetchSightings(), 15_000)
})

onUnmounted(() => { if (sightingsTimer) clearInterval(sightingsTimer) })

async function addPerson() {
  const ok = await store.upsertPerson(newPersonId.value.trim(), newPersonName.value.trim(), newPersonRole.value)
  if (ok) {
    newPersonId.value = ''
    newPersonName.value = ''
    newPersonRole.value = 'guest'
  }
}

async function addFact() {
  if (!store.detail) return
  const ok = await store.addFact(store.detail.person.person_id, newFactKey.value.trim(), newFactValue.value.trim())
  if (ok) {
    newFactKey.value = ''
    newFactValue.value = ''
  }
}

function confirmForget() {
  if (!store.detail) return
  const name = store.detail.person.display_name
  if (window.confirm(`Erase ${name} and ALL their data? This cannot be undone.`)) {
    store.forgetPerson(store.detail.person.person_id)
  }
}
</script>

<style scoped>
.knowledge-overlay {
  position: fixed; inset: 0; background: var(--overlay);
  display: flex; align-items: center; justify-content: center; z-index: 40;
}
.knowledge-modal {
  background: var(--surface); border: 1px solid var(--border-strong); border-radius: var(--radius-xl);
  width: 44rem; max-width: 95vw; max-height: 85vh;
  display: flex; flex-direction: column;
  box-shadow: var(--shadow-modal);
}
.knowledge-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0.85rem 1rem; border-bottom: 1px solid var(--border);
}
.knowledge-title { font-weight: 600; font-size: 0.95rem; display: inline-flex; align-items: center; gap: 0.4rem; }
.knowledge-header-right { display: flex; align-items: center; gap: 0.5rem; }
.tier-badge { font-size: 0.7rem; padding: 0.15rem 0.5rem; border-radius: 999px; font-weight: 600; display: inline-flex; align-items: center; gap: 0.25rem; }
.tier-sensitive { background: var(--ok-bg); color: var(--ok-text); }
.tier-benign { background: var(--surface-hover); color: var(--text-muted); }
.btn-lock {
  background: var(--warn-bg); color: var(--warn-text); border: none; border-radius: var(--radius-sm);
  font-size: 0.7rem; padding: 0.2rem 0.6rem; cursor: pointer;
}
.btn-lock:hover { filter: brightness(1.15); }
.btn-close { background: none; border: none; color: var(--text-muted); cursor: pointer; display: flex; }
.btn-close:hover { color: var(--text); }

.knowledge-error {
  margin: 0.6rem 1rem 0; padding: 0.4rem 0.6rem; border-radius: var(--radius);
  background: var(--danger-bg); color: var(--danger-text); font-size: 0.78rem;
}

.knowledge-body {
  display: grid; grid-template-columns: 16rem 1fr; gap: 1rem;
  padding: 1rem; overflow-y: auto; min-height: 20rem;
}

.col-title { font-size: 0.7rem; color: var(--text-faint); text-transform: uppercase; margin: 0.5rem 0 0.35rem; }
.people-col { display: flex; flex-direction: column; border-right: 1px solid var(--border); padding-right: 1rem; }
.people-list { list-style: none; padding: 0; flex: 1; overflow-y: auto; }
.person-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0.35rem 0.5rem; border-radius: var(--radius-sm); cursor: pointer; font-size: 0.85rem;
}
.person-row:hover { background: var(--surface-3); }
.person-row--active { background: var(--surface-2); border-left: 3px solid var(--accent); }
.person-name { flex: 1; }
.role-badge { font-size: 0.65rem; padding: 0.1rem 0.4rem; border-radius: 999px; text-transform: uppercase; }
.role-owner { background: var(--accent); color: var(--on-accent); }
.role-family { background: var(--ok-bg); color: var(--ok-text); }
.role-guest { background: var(--surface-hover); color: var(--text-muted); }
.role-minor { background: var(--info-bg); color: var(--info-text); }

.add-person-form, .add-fact-form { display: flex; flex-direction: column; gap: 0.4rem; margin-top: 0.6rem; }
.add-fact-form { flex-direction: row; }
.add-fact-form .field-input { flex: 1; }

.field-input, .field-select {
  padding: 0.35rem 0.5rem; background: var(--surface-3); border: 1px solid var(--border);
  border-radius: var(--radius-sm); color: var(--text); font-size: 0.8rem; outline: none;
}
.field-input:focus, .field-select:focus { border-color: var(--accent-border); }

.btn-apply {
  padding: 0.35rem 0.8rem; border-radius: var(--radius-sm); background: var(--accent);
  color: var(--on-accent); font-size: 0.8rem; cursor: pointer; border: none;
}
.btn-apply:hover { background: var(--accent-hover); }

.detail-col { display: flex; flex-direction: column; min-width: 0; }
.detail-header { display: flex; align-items: center; justify-content: space-between; }
.detail-name { font-size: 1rem; font-weight: 600; }
.btn-forget {
  background: var(--danger-bg-hover); color: var(--danger-text); border: none; border-radius: var(--radius-sm);
  font-size: 0.75rem; padding: 0.25rem 0.7rem; cursor: pointer;
}
.btn-forget:hover { background: var(--danger); color: #fff; }
.minor-note { font-size: 0.72rem; color: var(--info-text); margin-top: 0.3rem; }

.fact-list { list-style: none; padding: 0; }
.fact-row {
  display: flex; align-items: center; gap: 0.5rem;
  padding: 0.3rem 0.4rem; border-radius: var(--radius-sm); font-size: 0.8rem;
}
.fact-row:hover { background: var(--surface-3); }
.fact-key { color: var(--accent-soft); font-family: monospace; }
.fact-value { flex: 1; word-break: break-word; }
.signal-meta { color: var(--text-faint); font-size: 0.72rem; white-space: nowrap; }
.btn-delete { background: none; border: none; color: var(--text-faint); cursor: pointer; display: flex; }
.btn-delete:hover { color: var(--danger-text); }

.empty-hint { color: var(--text-faint); font-size: 0.78rem; padding: 0.3rem 0; }
.detail-placeholder { margin: auto; }
.provenance-hint { text-transform: none; color: var(--text-faint); }

/* Secure banner */
.secure-banner {
  margin: 0.6rem 1rem 0; padding: 0.7rem 0.85rem; border-radius: var(--radius);
  background: var(--warn-bg); border: 1px solid var(--warn);
}
.secure-text { display: flex; gap: 0.5rem; color: var(--warn-text); font-size: 0.78rem; }
.secure-icon { flex-shrink: 0; margin-top: 0.1rem; }
.secure-form { display: flex; gap: 0.5rem; align-items: center; margin-top: 0.55rem; flex-wrap: wrap; }
.secure-form .field-input { flex: 1; min-width: 12rem; }
.secure-remember { display: inline-flex; align-items: center; gap: 0.3rem; font-size: 0.72rem; color: var(--warn-text); }

/* Teach face */
.teach-face-row { display: flex; align-items: center; gap: 0.5rem; margin-top: 0.5rem; }
.btn-teach {
  display: inline-flex; align-items: center; gap: 0.35rem;
  background: var(--accent); color: var(--on-accent); border: none;
  border-radius: var(--radius-sm); font-size: 0.78rem; padding: 0.35rem 0.75rem; cursor: pointer;
}
.btn-teach:hover:not(:disabled) { background: var(--accent-hover); }
.btn-teach:disabled { opacity: 0.6; }
.teach-hint { font-size: 0.7rem; color: var(--text-faint); }
.teach-msg { font-size: 0.74rem; color: var(--ok); margin-top: 0.3rem; }

/* Facts UX */
.facts-hint { font-size: 0.72rem; color: var(--text-faint); margin: 0 0 0.35rem; }
.fact-suggestions { display: flex; flex-wrap: wrap; gap: 0.3rem; margin-bottom: 0.35rem; }
.fact-chip {
  background: var(--surface-3); border: 1px solid var(--border); border-radius: 999px;
  color: var(--text-muted); font-size: 0.68rem; padding: 0.15rem 0.55rem; cursor: pointer;
}
.fact-chip:hover { color: var(--text); border-color: var(--accent-border); }

/* Unknown visitors (U36f) */
.sighting-card {
  display: flex; gap: 0.5rem; align-items: center;
  border: 1px solid var(--border); border-radius: var(--radius);
  padding: 0.35rem; margin-bottom: 0.4rem; background: var(--surface-2);
}
.sighting-img { width: 74px; height: 42px; object-fit: cover; border-radius: var(--radius-sm); }
.sighting-meta { flex: 1; min-width: 0; }
.sighting-time { font-size: 0.68rem; color: var(--text-faint); }
.sighting-actions { display: flex; gap: 0.3rem; align-items: center; margin-top: 0.25rem; }
.sighting-select { flex: 1; font-size: 0.72rem; padding: 0.2rem 0.35rem; }
.sighting-btn { display: inline-flex; padding: 0.3rem 0.45rem; }
.sighting-btn:disabled { opacity: 0.45; cursor: not-allowed; }
</style>
