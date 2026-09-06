<template>
  <div v-if="open" ref="root" class="picker" role="menu" :aria-label="title">
    <p v-if="title" class="picker-title">{{ title }}</p>
    <button
      v-for="(item, i) in items" :key="item.id"
      ref="rows"
      class="picker-row" :class="{ active: item.active }"
      role="menuitem" :title="item.hint"
      @click="$emit('pick', item.id)"
      @keydown.down.prevent="focusRow(i + 1)"
      @keydown.up.prevent="focusRow(i - 1)"
    >
      <span v-if="item.art" class="picker-art" v-html="item.art" />
      <span v-else-if="item.initials" class="picker-initials" :class="{ muted: item.muted }">
        {{ item.initials }}
      </span>
      <span class="picker-text">
        <span class="picker-label">{{ item.label }}</span>
        <span v-if="item.sub" class="picker-sub">{{ item.sub }}</span>
      </span>
      <Check v-if="item.active" :size="14" class="picker-tick" />
    </button>
    <!-- Only when the list is genuinely empty. It rendered under a populated
         list at first — "Nobody is in the brain yet" printed directly beneath
         a person's name, which is the console asserting something it could
         see was false (constitution XI). -->
    <p v-if="empty && !items.length" class="picker-empty">{{ empty }}</p>
    <button v-if="footer" class="picker-footer" @click="$emit('footer')">{{ footer }}</button>
  </div>
</template>

<script setup lang="ts">
/** U319: choose directly, instead of pressing a thing until it lands.
 *
 *  Reported as "'who is this' -> tapping will cycle, but via arrow we should
 *  be able to choose directly", and the same for the robot on the Talk screen.
 *  Cycling is fine for two options and hostile for ten: to reach the last one
 *  you press nine times, and you cannot see what you are choosing between.
 *
 *  A shared component rather than two dropdowns, because the two places have
 *  the same job — show the options, mark the current one, pick one — and one
 *  of the recurring defects in this console is two surfaces drifting apart.
 */
import { nextTick, onUnmounted, ref, watch } from 'vue'
import { Check } from 'lucide-vue-next'

export interface PickerItem {
  id: string
  label: string
  sub?: string
  hint?: string
  /** Inline SVG for a character mark. */
  art?: string
  /** Or two letters, for a person. */
  initials?: string
  muted?: boolean
  active?: boolean
}

const props = defineProps<{
  open: boolean
  items: PickerItem[]
  title?: string
  /** Shown when there is nothing to choose from — an empty menu explains
   *  nothing, and "no people yet" is a state with an obvious next step. */
  empty?: string
  /** An action under the list: "Teach a face", "See all characters". */
  footer?: string
}>()

const emit = defineEmits<{
  (e: 'pick', id: string): void
  (e: 'close'): void
  (e: 'footer'): void
}>()

const root = ref<HTMLElement | null>(null)
const rows = ref<HTMLElement[]>([])

function focusRow(i: number): void {
  const list = rows.value
  if (!list.length) return
  list[(i + list.length) % list.length]?.focus()
}

function onDocument(e: MouseEvent): void {
  // A click inside the menu is a choice; anywhere else means "never mind".
  // The trigger button handles its own toggle, so ignore clicks it owns.
  const el = root.value
  if (el && !el.contains(e.target as Node)) emit('close')
}

function onKey(e: KeyboardEvent): void {
  if (e.key === 'Escape') emit('close')
}

function unlisten(): void {
  if (typeof document === 'undefined') return
  document.removeEventListener('click', onDocument)
  document.removeEventListener('keydown', onKey)
}

// `immediate`: a lazy watcher never runs for a menu that is mounted ALREADY
// open, which leaves Escape and click-outside dead — the two ways out. In the
// app it happens to mount closed, so this would have been a trap waiting for
// the first caller who did it differently.
watch(() => props.open, async (open) => {
  if (typeof document === 'undefined') return
  if (!open) {
    unlisten()
    return
  }
  await nextTick()
  focusRow(Math.max(0, props.items.findIndex(i => i.active)))
  // `click` rather than `mousedown`: the trigger's own click must land first,
  // or opening the menu immediately closes it again.
  document.addEventListener('click', onDocument)
  document.addEventListener('keydown', onKey)
}, { immediate: true })

onUnmounted(unlisten)
</script>

<style scoped>
.picker {
  position: absolute; top: calc(100% + 6px); right: 0; z-index: 60;
  min-width: 210px; max-width: 280px; max-height: 60vh; overflow-y: auto;
  padding: 5px; border-radius: 12px;
  background: var(--surface); border: 1.5px solid var(--line);
  box-shadow: 0 10px 28px rgb(0 0 0 / 0.16);
  text-align: left;
}
.picker-title {
  margin: 3px 8px 5px; font-size: 10.5px; font-weight: 700;
  letter-spacing: 0.06em; text-transform: uppercase; color: var(--ink-3);
}
.picker-row {
  display: flex; align-items: center; gap: 9px; width: 100%;
  padding: 6px 8px; border: 0; border-radius: 8px;
  background: none; color: var(--ink); font: inherit; text-align: left;
  cursor: pointer;
}
.picker-row:hover, .picker-row:focus-visible { background: var(--sunken); }
.picker-row.active { background: var(--accent-wash); }
.picker-art { display: flex; flex-shrink: 0; width: 26px; justify-content: center; }
.picker-initials {
  width: 26px; height: 26px; border-radius: 50%; flex-shrink: 0;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 10.5px; font-weight: 700;
  background: var(--accent); color: var(--on-accent);
}
.picker-initials.muted { background: var(--sunken); color: var(--ink-3); }
.picker-text { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.picker-label { font-size: 13px; font-weight: 600; }
.picker-sub { font-size: 11px; color: var(--ink-3); }
.picker-tick { color: var(--accent); flex-shrink: 0; }
.picker-empty { margin: 6px 8px; font-size: 12px; color: var(--ink-3); }
.picker-footer {
  display: block; width: 100%; margin-top: 3px; padding: 7px 8px;
  border: 0; border-top: 1px solid var(--line); border-radius: 0 0 8px 8px;
  background: none; color: var(--accent); font: inherit; font-size: 12px;
  text-align: left; cursor: pointer;
}
.picker-footer:hover { background: var(--sunken); }
</style>
