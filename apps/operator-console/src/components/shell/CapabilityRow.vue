<template>
  <button
    class="cap-row" :class="{ present: modeStore.mode === 'present' }"
    :title="canEdit ? 'Open the mode editor to change these boundaries'
      : 'Only the owner can change what he may do'"
    @click="onClick"
  >
    <span class="cap-mode mono">{{ MODE_META[modeStore.mode].label }}</span>
    <span
      v-for="g in modeStore.activeGroups" :key="g.id"
      class="cap-chip" :class="[g.state, { unreachable: g.unreachable }]" :title="chipHint(g)"
    >{{ chipText(g) }}</span>
    <span class="cap-spacer" />
    <span class="cap-edit">
      {{ canEdit ? 'Edit boundaries' : 'Set by the owner' }}
      <ChevronRight :size="12" />
    </span>
  </button>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ChevronRight } from 'lucide-vue-next'
import { MODE_META, useModeStore, type PolicyGroup } from '../../stores/modeStore'
import { useKnowledgeStore } from '../../stores/knowledgeStore'
import { useNavStore } from '../../stores/navStore'

const modeStore = useModeStore()
const knowledge = useKnowledgeStore()
const nav = useNavStore()

/** Owner (or an unconfigured install) may edit; everyone else gets told who
 * can. Never render a rule with no route to its source. */
const canEdit = computed(() => {
  if (!knowledge.people.length) return true
  const s = knowledge.speaker
  if (s === null) return true // nobody claimed the session — the laptop is the owner's
  if (s === 'guest') return false
  return knowledge.people.find(p => p.person_id === s)?.role === 'owner'
})

function onClick(): void {
  if (canEdit.value) nav.go('modes')
  // Non-owners keep the tooltip explanation; the row does not navigate.
}

// U254: a group can be allowed by the mode and still have nothing behind it —
// no mail account means no mail, whatever the boundary says. Saying "no
// account" is the honest word; a green chip there is a promise he cannot keep.
function chipText(g: PolicyGroup): string {
  if (g.unreachable) return `${g.id} · no account`
  return g.state === 'asks' ? `${g.id} · asks` : g.id
}

function chipHint(g: PolicyGroup): string {
  if (g.unreachable) {
    return `${g.label} — ${g.detail}. This mode allows it, but no account is `
      + 'connected for it, so he cannot. Connect one in Settings › Connections.'
  }
  const base = g.state === 'allows'
    ? 'Runs without asking'
    : g.state === 'asks'
      ? (g.source === 'override'
        ? 'You set this to asks — every use needs your approval'
        : 'Available; anything sensitive in it asks first')
      : 'Refused in this mode'
  return `${g.label} — ${g.detail}. ${base}.`
}
</script>

<style scoped>
.cap-row {
  display: flex; align-items: center; gap: 7px; flex-wrap: wrap; width: 100%;
  text-align: left; padding: 8px 16px; background: var(--surface-2);
  border: none; border-bottom: 1px solid var(--line);
  cursor: pointer; font-family: inherit; flex-shrink: 0;
}
.cap-row.present { background: var(--present-wash); }
.cap-mode {
  font-size: 10.5px; font-weight: 700; letter-spacing: 0.1em;
  text-transform: uppercase; color: var(--ink-3); flex-shrink: 0;
}
.mono { font-family: var(--font-mono); }
.cap-chip {
  display: inline-flex; align-items: center; font-size: 11.5px; font-weight: 600;
  padding: 2px 10px; border-radius: 999px;
}
.cap-chip.allows { background: var(--ok-wash); color: var(--ok); border: 1px solid transparent; }
.cap-chip.asks { background: var(--warn-wash); color: var(--warn); border: 1px solid transparent; }
.cap-chip.unreachable {
  background: var(--sunken); color: var(--ink-3);
  border: 1px dashed var(--line-strong); text-decoration: none;
}
.cap-chip.blocked {
  background: transparent; color: var(--ink-3);
  border: 1px dashed var(--line-strong); text-decoration: line-through;
}
.cap-spacer { flex: 1; }
.cap-edit {
  display: inline-flex; align-items: center; gap: 5px;
  font-size: 11.5px; font-weight: 600; color: var(--ink-3); flex-shrink: 0;
}
</style>
