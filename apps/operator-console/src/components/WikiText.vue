<template>
  <span class="wikitext">
    <template v-for="(seg, i) in segments" :key="i">
      <button
        v-if="seg.target"
        type="button"
        class="wikilink"
        :title="`Open ${seg.target}`"
        @click="$emit('open', seg.target)"
      >{{ seg.target }}</button>
      <template v-else>{{ seg.text }}</template>
    </template>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

/** U68: renders text with Obsidian-style [[links]] as clickable chips.
 *  The parent decides what a target IS (person or skill) via @open. */
const props = defineProps<{ text: string }>()
defineEmits<{ (e: 'open', target: string): void }>()

interface Segment { text?: string; target?: string }

const segments = computed<Segment[]>(() => {
  const out: Segment[] = []
  const re = /\[\[([^\]]+)\]\]/g
  let last = 0
  let m: RegExpExecArray | null
  const text = props.text ?? ''
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push({ text: text.slice(last, m.index) })
    out.push({ target: m[1].trim() })
    last = m.index + m[0].length
  }
  if (last < text.length) out.push({ text: text.slice(last) })
  return out
})
</script>

<style scoped>
.wikitext { white-space: pre-wrap; }
.wikilink {
  display: inline; padding: 0 0.15rem; margin: 0;
  background: none; border: none; cursor: pointer;
  color: var(--accent); font: inherit;
  text-decoration: underline; text-decoration-style: dotted;
  text-underline-offset: 2px;
}
.wikilink:hover { text-decoration-style: solid; }
</style>
