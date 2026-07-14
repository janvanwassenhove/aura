<template>
  <div v-if="approvalStore.pending.length > 0" class="approval-overlay">
    <div
      v-for="request in approvalStore.pending"
      :key="request.approvalId"
      class="approval-modal"
    >
      <div class="approval-header">
        <span class="approval-icon"><TriangleAlert :size="20" /></span>
        <h3>Approval Required</h3>
      </div>
      <div class="approval-body">
        <div class="approval-field">
          <span class="field-label">Action</span>
          <code class="field-value">{{ request.toolName }}</code>
        </div>
        <div v-if="request.argumentsSummary" class="approval-field">
          <span class="field-label">Arguments</span>
          <span class="field-value text-sm">{{ request.argumentsSummary }}</span>
        </div>
        <div class="approval-field">
          <span class="field-label">Requested</span>
          <span class="field-value">{{ fmtTime(request.requestedAt) }}</span>
        </div>
        <div class="approval-countdown">
          Expires at {{ fmtTime(request.timeoutAt) }}
        </div>
        <label class="approval-remember">
          <input v-model="remember[request.approvalId]" type="checkbox" />
          Always allow “{{ request.toolName }}” (manage in Capabilities)
        </label>
      </div>
      <div class="approval-actions">
        <button class="btn-deny" @click="approvalStore.deny(request.approvalId)">Deny</button>
        <button class="btn-grant" @click="approvalStore.grant(request.approvalId, remember[request.approvalId] === true)">Grant</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { TriangleAlert } from 'lucide-vue-next'
import { useApprovalStore } from '../stores/approvalStore'

const approvalStore = useApprovalStore()
const remember = ref<Record<string, boolean>>({})

let expiryTimer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  expiryTimer = setInterval(() => approvalStore.expireOld(), 1_000)
})

onUnmounted(() => {
  if (expiryTimer) clearInterval(expiryTimer)
})

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString()
}
</script>
