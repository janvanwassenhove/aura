<template>
  <section class="panel flex flex-col h-full">
    <h2 class="panel-title">Conversation</h2>

    <div ref="scrollEl" class="conversation-scroll flex-1 overflow-y-auto space-y-2 mb-3">
      <div
        v-for="turn in conversationStore.turns"
        :key="turn.id"
        :class="['turn', turn.role === 'user' ? 'turn-user' : 'turn-assistant']"
      >
        <div class="turn-header">
          <span class="turn-role">{{ turn.role === 'user' ? 'You' : 'AURA' }}</span>
          <span class="turn-time">{{ fmtTime(turn.timestamp) }}</span>
        </div>
        <div class="turn-text">{{ turn.text }}</div>
        <div v-if="turn.toolCall" :class="['tool-badge', `tool-${turn.toolCall.status}`]">
          <Wrench :size="11" /> {{ turn.toolCall.name }} — {{ turn.toolCall.status }}
        </div>
      </div>
      <div v-if="conversationStore.isProcessing" class="turn turn-assistant">
        <div class="turn-text animate-pulse">AURA is thinking…</div>
      </div>
      <div v-if="conversationStore.turns.length === 0" class="getting-started">
        <h3 class="gs-title"><Sparkles :size="14" /> Talk to your robot</h3>
        <p class="gs-line">Type below and press <strong>Send</strong> — the reply appears here.</p>
        <div class="gs-suggestions">
          <button v-for="s in suggestions" :key="s" class="gs-chip" @click="trySuggestion(s)">{{ s }}</button>
        </div>
        <p class="gs-line gs-muted">
          Make the robot move with the <strong>Quick Actions</strong> on the left, watch what it
          sees in <strong>Robot Camera</strong>, and teach it your face with <strong>This is me</strong>.
        </p>
      </div>
    </div>

    <div v-if="conversationStore.lastLatency" class="latency-bar text-xs text-gray-400 mb-2">
      Last turn: {{ conversationStore.lastLatency.total_ms.toFixed(0) }}ms total
      (LLM {{ conversationStore.lastLatency.llm_ms.toFixed(0) }}ms
      + tools {{ conversationStore.lastLatency.tool_ms.toFixed(0) }}ms)
    </div>

    <form class="input-row" @submit.prevent="submit">
      <input
        v-model="conversationStore.pendingText"
        type="text"
        placeholder="Type a message…"
        :disabled="conversationStore.isProcessing"
        class="chat-input"
      />
      <button
        type="submit"
        :disabled="conversationStore.isProcessing || !conversationStore.pendingText.trim()"
        class="btn-primary"
      >
        {{ conversationStore.isProcessing ? '…' : 'Send' }}
      </button>
    </form>
  </section>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { Sparkles, Wrench } from 'lucide-vue-next'
import { useConversationStore } from '../stores/conversationStore'

const conversationStore = useConversationStore()
const scrollEl = ref<HTMLElement | null>(null)

const suggestions = [
  'What can you do?',
  'What meetings do I have today?',
  'Tell me a fun fact',
]

async function trySuggestion(text: string) {
  conversationStore.pendingText = text
  await submit()
}

async function submit() {
  const text = conversationStore.pendingText.trim()
  if (!text) return
  conversationStore.pendingText = ''
  await conversationStore.submitTurn(text)
}

watch(
  () => conversationStore.turns.length,
  async () => {
    await nextTick()
    if (scrollEl.value) scrollEl.value.scrollTop = scrollEl.value.scrollHeight
  },
)

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString()
}
</script>

<style scoped>
.getting-started {
  border: 1px dashed var(--border); border-radius: var(--radius);
  padding: 0.9rem 1rem; color: var(--text-muted); font-size: 0.82rem;
}
.gs-title { display: flex; align-items: center; gap: 0.4rem; font-weight: 600; color: var(--text); margin-bottom: 0.4rem; }
.gs-line { margin: 0.25rem 0; }
.gs-muted { color: var(--text-faint); font-size: 0.76rem; }
.gs-suggestions { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0.5rem 0; }
.gs-chip {
  background: var(--surface-3); border: 1px solid var(--border); border-radius: 999px;
  color: var(--text-muted); font-size: 0.75rem; padding: 0.25rem 0.7rem; cursor: pointer;
}
.gs-chip:hover { color: var(--text); border-color: var(--accent-border); }
</style>
