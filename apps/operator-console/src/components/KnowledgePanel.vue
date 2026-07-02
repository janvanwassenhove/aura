<template>
  <div class="knowledge-overlay" @click.self="$emit('close')">
    <div class="knowledge-modal">
      <div class="knowledge-header">
        <span class="knowledge-title">🧠 Knowledge — what AURA knows</span>
        <div class="knowledge-header-right">
          <span :class="['tier-badge', store.tier === 'sensitive' ? 'tier-sensitive' : 'tier-benign']">
            {{ store.tier === 'sensitive' ? '🔓 sensitive' : store.omkLoaded ? '🔒 locked' : 'dev (unencrypted)' }}
          </span>
          <button
            v-if="store.tier === 'sensitive'"
            class="btn-lock"
            title="Drop to benign tier (restart brain with KNOWLEDGE_PASSPHRASE to unlock)"
            @click="store.lock()"
          >Lock</button>
          <button class="btn-close" @click="$emit('close')">✕</button>
        </div>
      </div>

      <div v-if="store.error" class="knowledge-error">{{ store.error }}</div>

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

            <div class="col-title">Explicit facts</div>
            <ul class="fact-list">
              <li v-for="f in store.detail.facts" :key="f.fact_id" class="fact-row">
                <span class="fact-key">{{ f.key }}</span>
                <span class="fact-value">{{ f.value }}</span>
                <button class="btn-delete" title="Delete fact (step-up when encrypted)" @click="store.deleteFact(f.fact_id, store.detail!.person.person_id)">✕</button>
              </li>
              <li v-if="store.detail.facts.length === 0" class="empty-hint">No facts recorded.</li>
            </ul>

            <form class="add-fact-form" @submit.prevent="addFact">
              <input v-model="newFactKey" class="field-input" placeholder="key" required />
              <input v-model="newFactValue" class="field-input" placeholder="value" required />
              <button type="submit" class="btn-apply">Add fact</button>
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
import { onMounted, ref } from 'vue'
import { useKnowledgeStore } from '../stores/knowledgeStore'

defineEmits<{ close: [] }>()

const store = useKnowledgeStore()

const newPersonId = ref('')
const newPersonName = ref('')
const newPersonRole = ref('guest')
const newFactKey = ref('')
const newFactValue = ref('')

onMounted(async () => {
  await store.fetchTier()
  await store.fetchPeople()
})

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
  position: fixed; inset: 0; background: rgba(0, 0, 0, 0.6);
  display: flex; align-items: center; justify-content: center; z-index: 40;
}
.knowledge-modal {
  background: #1e293b; border: 1px solid #475569; border-radius: 0.75rem;
  width: 44rem; max-width: 95vw; max-height: 85vh;
  display: flex; flex-direction: column;
  box-shadow: 0 25px 50px rgba(0, 0, 0, 0.5);
}
.knowledge-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0.85rem 1rem; border-bottom: 1px solid #334155;
}
.knowledge-title { font-weight: 600; font-size: 0.95rem; }
.knowledge-header-right { display: flex; align-items: center; gap: 0.5rem; }
.tier-badge { font-size: 0.7rem; padding: 0.15rem 0.5rem; border-radius: 999px; font-weight: 600; }
.tier-sensitive { background: #14532d; color: #86efac; }
.tier-benign { background: #374151; color: #d1d5db; }
.btn-lock {
  background: #78350f; color: #fde68a; border: none; border-radius: 0.25rem;
  font-size: 0.7rem; padding: 0.2rem 0.6rem; cursor: pointer;
}
.btn-lock:hover { background: #92400e; }
.btn-close { background: none; border: none; color: #94a3b8; cursor: pointer; font-size: 0.9rem; }
.btn-close:hover { color: #e2e8f0; }

.knowledge-error {
  margin: 0.6rem 1rem 0; padding: 0.4rem 0.6rem; border-radius: 0.375rem;
  background: #450a0a; color: #fca5a5; font-size: 0.78rem;
}

.knowledge-body {
  display: grid; grid-template-columns: 16rem 1fr; gap: 1rem;
  padding: 1rem; overflow-y: auto; min-height: 20rem;
}

.col-title { font-size: 0.7rem; color: #64748b; text-transform: uppercase; margin: 0.5rem 0 0.35rem; }
.people-col { display: flex; flex-direction: column; border-right: 1px solid #334155; padding-right: 1rem; }
.people-list { list-style: none; padding: 0; flex: 1; overflow-y: auto; }
.person-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0.35rem 0.5rem; border-radius: 0.3rem; cursor: pointer; font-size: 0.85rem;
}
.person-row:hover { background: #0f172a; }
.person-row--active { background: #172033; border-left: 3px solid #3b82f6; }
.person-name { flex: 1; }
.role-badge { font-size: 0.65rem; padding: 0.1rem 0.4rem; border-radius: 999px; text-transform: uppercase; }
.role-owner { background: #1d4ed8; color: #bfdbfe; }
.role-family { background: #15803d; color: #bbf7d0; }
.role-guest { background: #374151; color: #d1d5db; }
.role-minor { background: #7e22ce; color: #e9d5ff; }

.add-person-form, .add-fact-form { display: flex; flex-direction: column; gap: 0.4rem; margin-top: 0.6rem; }
.add-fact-form { flex-direction: row; }
.add-fact-form .field-input { flex: 1; }

.field-input, .field-select {
  padding: 0.35rem 0.5rem; background: #0f172a; border: 1px solid #334155;
  border-radius: 0.3rem; color: #e2e8f0; font-size: 0.8rem; outline: none;
}
.field-input:focus, .field-select:focus { border-color: #60a5fa; }

.btn-apply {
  padding: 0.35rem 0.8rem; border-radius: 0.3rem; background: #2563eb;
  color: white; font-size: 0.8rem; cursor: pointer; border: none;
}
.btn-apply:hover { background: #1d4ed8; }

.detail-col { display: flex; flex-direction: column; min-width: 0; }
.detail-header { display: flex; align-items: center; justify-content: space-between; }
.detail-name { font-size: 1rem; font-weight: 600; }
.btn-forget {
  background: #7f1d1d; color: #fca5a5; border: none; border-radius: 0.3rem;
  font-size: 0.75rem; padding: 0.25rem 0.7rem; cursor: pointer;
}
.btn-forget:hover { background: #991b1b; }
.minor-note { font-size: 0.72rem; color: #c4b5fd; margin-top: 0.3rem; }

.fact-list { list-style: none; padding: 0; }
.fact-row {
  display: flex; align-items: center; gap: 0.5rem;
  padding: 0.3rem 0.4rem; border-radius: 0.25rem; font-size: 0.8rem;
}
.fact-row:hover { background: #0f172a; }
.fact-key { color: #93c5fd; font-family: monospace; }
.fact-value { flex: 1; word-break: break-word; }
.signal-meta { color: #64748b; font-size: 0.72rem; white-space: nowrap; }
.btn-delete { background: none; border: none; color: #64748b; cursor: pointer; font-size: 0.75rem; }
.btn-delete:hover { color: #fca5a5; }

.empty-hint { color: #64748b; font-size: 0.78rem; padding: 0.3rem 0; }
.detail-placeholder { margin: auto; }
.provenance-hint { text-transform: none; color: #475569; }
</style>
