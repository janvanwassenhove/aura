<template>
  <main class="graphview">
    <div class="graph-bar">
      <button class="d2-ghost-btn" title="Back to People" @click="nav.go('people')">← People</button>
      <h2 v-if="detail">{{ detail.person.display_name }}'s knowledge</h2>
      <span v-if="detail" class="mono graph-count">{{ graphCount }}</span>
      <span class="bar-spacer" />
      <span v-for="l in LEGEND" :key="l.label" class="legend">
        <span class="legend-dot" :style="{ background: l.color }" />{{ l.label }}
      </span>
      <button class="d2-ghost-btn" @click="graphRef?.reset()">Reset view</button>
    </div>
    <div class="graph-body">
      <KnowledgeGraph
        v-if="detail" ref="graphRef"
        :detail="detail" :people-ids="peopleIds" @open-person="openPerson"
      />
      <p v-else class="graph-empty">Pick a person in People first.</p>
      <span class="mono graph-hint">drag a node to move it · drag the background to pan · scroll to zoom</span>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import KnowledgeGraph from '../components/canvas/KnowledgeGraph.vue'
import { MEMORY_COLOUR } from '../lib/memoryGraph'
import { useKnowledgeStore } from '../stores/knowledgeStore'
import { useNavStore } from '../stores/navStore'

const knowledge = useKnowledgeStore()
const nav = useNavStore()

const detail = computed(() => knowledge.detail)
const peopleIds = computed(() => knowledge.people.map(p => p.person_id))
const graphRef = ref<InstanceType<typeof KnowledgeGraph> | null>(null)

const LEGEND = [
  { label: 'People', color: 'var(--accent)' },
  { label: 'Facts', color: 'var(--info)' },
  // U279: memory nodes have had their own colour since U272 and nothing said
  // so — asked for as "pas styling aan wanneer het memory item betreft".
  { label: 'Memory', color: MEMORY_COLOUR },
  { label: 'Skills', color: 'var(--present)' },
  { label: 'Topics', color: 'var(--warn)' },
]

// Derived, never hand-written.
const graphCount = computed(() => {
  const d = detail.value
  if (!d) return ''
  const facts = d.facts.filter(f => f.key !== 'memory' && !f.key.startsWith('source:')).length
  return `${facts} facts · ${(d.skills ?? []).length} skills · ${d.signals.length} signals`
})

function openPerson(id: string): void {
  knowledge.selectedPerson = id
  knowledge.inspectPerson(id)
}
</script>

<style scoped>
.graphview { flex: 1; min-width: 0; display: flex; flex-direction: column; min-height: 0; background: var(--sunken); }
.mono { font-family: var(--font-mono); }
.graph-bar {
  display: flex; align-items: center; gap: 11px; padding: 11px 16px;
  border-bottom: 1px solid var(--line); background: var(--surface);
  flex-shrink: 0; flex-wrap: wrap;
}
.graph-bar h2 { margin: 0; font-size: 16px; }
.graph-count { font-size: 11px; color: var(--ink-3); }
.bar-spacer { flex: 1; }
.legend { display: inline-flex; align-items: center; gap: 5px; font-size: 11.5px; color: var(--ink-3); }
.legend-dot { width: 7px; height: 7px; border-radius: 50%; }
.graph-body { flex: 1; min-height: 0; position: relative; }
.graph-empty { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; color: var(--ink-3); font-size: 13px; }
.graph-hint { position: absolute; left: 14px; bottom: 12px; font-size: 11px; color: var(--ink-3); pointer-events: none; }
</style>
