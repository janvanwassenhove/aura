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
          🔧 {{ turn.toolCall.name }} — {{ turn.toolCall.status }}
        </div>
      </div>
      <div v-if="conversationStore.isProcessing" class="turn turn-assistant">
        <div class="turn-text animate-pulse">AURA is thinking…</div>
      </div>
      <div v-if="conversationStore.turns.length === 0" class="text-gray-400 text-sm">
        No conversation yet. Type below to start.
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
import { useConversationStore } from '../stores/conversationStore'

const conversationStore = useConversationStore()
const scrollEl = ref<HTMLElement | null>(null)

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
