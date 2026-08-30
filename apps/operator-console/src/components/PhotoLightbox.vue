<template>
  <div
    class="lb" role="dialog" aria-modal="true" :aria-label="caption || 'Photo'"
    @click.self="$emit('close')"
  >
    <div class="lb-panel">
      <img :src="src" :alt="caption || 'Photo'" class="lb-img">
      <div class="lb-bar">
        <span class="lb-caption">{{ caption }}</span>
        <span class="lb-spacer" />
        <!-- Whatever this photo is FOR. A face you enlarged in order to
             recognise is a face you want to tag without hunting for the tiny
             row again, so the decision belongs beside the evidence. -->
        <slot name="actions" />
        <button class="lb-close" title="Close (Esc)" @click="$emit('close')">✕</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/** U271: a photo big enough to recognise a face in.
 *
 * The unknown-visitor thumbnails are 34×26 px — and the one thing the row
 * asks you to do is decide WHO that is. Reported as "photos are quite small,
 * on click picture ad larger preview to more easily recognize". The same
 * applies to the "recently seen" snapshots, where the question is whether a
 * shot belongs to this person at all.
 *
 * Deliberately not a gallery: one photo, the thing it is for, and a way out.
 */
import { onMounted, onUnmounted } from 'vue'

defineProps<{ src: string; caption?: string }>()
const emit = defineEmits<{ close: [] }>()

function onKey(e: KeyboardEvent): void {
  if (e.key === 'Escape') emit('close')
}
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

<style scoped>
.lb {
  position: fixed; inset: 0; z-index: 900;
  display: flex; align-items: center; justify-content: center;
  background: rgba(10, 12, 14, 0.78);
  padding: 5vh 5vw;
}
.lb-panel {
  display: flex; flex-direction: column; max-width: min(760px, 90vw);
  background: var(--surface); border: 1px solid var(--line);
  border-radius: 14px; overflow: hidden;
  box-shadow: 0 18px 60px rgba(0, 0, 0, 0.45);
}
.lb-img {
  display: block; max-width: 100%; max-height: 72vh;
  object-fit: contain; background: #0d0f11;
  /* A face captured at low resolution stays a face — let the browser smooth
     it rather than hand the viewer a grid of pixels to squint at. */
  image-rendering: auto;
}
.lb-bar {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 12px; border-top: 1px solid var(--line);
}
.lb-caption { font-size: 12.5px; color: var(--ink-2); }
.lb-spacer { flex: 1; }
.lb-close {
  background: transparent; border: 1px solid var(--border-strong, var(--line));
  border-radius: 8px; color: var(--ink-2); cursor: pointer;
  width: 30px; height: 28px; font-size: 13px; flex-shrink: 0;
}
.lb-close:hover { color: var(--ink); border-color: var(--accent); }
</style>
