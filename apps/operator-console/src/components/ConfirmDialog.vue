<template>
  <div class="cd-overlay" @click.self="$emit('cancel')">
    <div ref="modalRoot" class="cd-modal" role="alertdialog" aria-modal="true"
         aria-labelledby="cd-title" tabindex="-1">
      <h3 id="cd-title" class="cd-title">{{ title }}</h3>
      <p v-if="body" class="cd-body">{{ body }}</p>
      <div class="cd-actions">
        <button ref="cancelBtn" class="cd-btn" @click="$emit('cancel')">{{ cancelLabel }}</button>
        <button :class="['cd-btn', danger ? 'cd-btn--danger' : 'cd-btn--go']" @click="$emit('confirm')">
          {{ confirmLabel }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// U223: the app's most destructive action — forgetting a person, which erases
// their profile AND their face — sat behind a native confirm(): unthemed,
// unstyled, ignoring dark mode, and inconsistent with the ApprovalPanel that
// already does this properly. One dialog, used everywhere that used to call
// confirm()/alert().
import { ref } from 'vue'
import { useModal } from '../composables/useModal'

withDefaults(defineProps<{
  title: string
  body?: string
  confirmLabel?: string
  cancelLabel?: string
  danger?: boolean
}>(), { body: '', confirmLabel: 'Confirm', cancelLabel: 'Cancel', danger: false })

const emit = defineEmits<{ confirm: []; cancel: [] }>()

const modalRoot = ref<HTMLElement | null>(null)
const cancelBtn = ref<HTMLElement | null>(null)
// Focus Cancel, not Confirm: a stray Enter on a destructive prompt should do
// nothing. Escape cancels (useModal).
useModal({ onClose: () => emit('cancel'), root: modalRoot, initialFocus: cancelBtn })
</script>

<style scoped>
.cd-overlay {
  position: fixed; inset: 0; background: var(--overlay);
  display: flex; align-items: center; justify-content: center; z-index: 80;
}
.cd-modal {
  width: min(420px, 92vw); padding: 1.1rem 1.2rem;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius-lg); box-shadow: var(--shadow-modal);
}
.cd-title { margin: 0 0 0.5rem; font-size: 0.95rem; }
.cd-body { margin: 0 0 1rem; font-size: 0.82rem; color: var(--text-muted); line-height: 1.5; }
.cd-actions { display: flex; justify-content: flex-end; gap: 0.5rem; }
.cd-btn {
  background: transparent; color: var(--text);
  border: 1px solid var(--border-strong); border-radius: var(--radius-md);
  padding: 0.4rem 0.9rem; font-size: 0.82rem; cursor: pointer;
}
.cd-btn--go { background: var(--accent); color: var(--on-accent); border-color: var(--accent); font-weight: 600; }
.cd-btn--danger { background: var(--danger); color: #fff; border-color: var(--danger); font-weight: 600; }
</style>
