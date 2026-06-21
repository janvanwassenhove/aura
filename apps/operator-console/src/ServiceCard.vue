<template>
  <div class="card" :class="status">
    <div class="dot" />
    <span class="name">{{ name }}</span>
    <span class="status-label">{{ status }}</span>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const props = defineProps<{ name: string; url: string }>()
const status = ref<'checking' | 'ok' | 'error'>('checking')

let interval: ReturnType<typeof setInterval>

async function check() {
  try {
    const r = await fetch(props.url, { signal: AbortSignal.timeout(3000) })
    status.value = r.ok ? 'ok' : 'error'
  } catch {
    status.value = 'error'
  }
}

onMounted(() => { check(); interval = setInterval(check, 5000) })
onUnmounted(() => clearInterval(interval))
</script>

<style scoped>
.card {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  border-radius: 6px;
  background: #1e293b;
  border: 1px solid #334155;
}
.dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.ok .dot { background: #4ade80; }
.error .dot { background: #f87171; }
.checking .dot { background: #facc15; }
.name { font-size: 0.85rem; flex: 1; }
.status-label { font-size: 0.7rem; color: #64748b; }
</style>
