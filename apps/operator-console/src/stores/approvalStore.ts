import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface PendingApproval {
  approvalId: string
  toolName: string
  argumentsSummary: string
  requestedAt: string
  timeoutAt: string
}

export const useApprovalStore = defineStore('approval', () => {
  const pending = ref<PendingApproval[]>([])

  const orchestratorUrl = import.meta.env.VITE_ORCHESTRATOR_URL ?? 'http://localhost:8003'

  function applyEvent(event: Record<string, unknown>) {
    const type = event.event_type as string
    if (type === 'ApprovalRequested') {
      const requestedAt = (event.timestamp as string) ?? new Date().toISOString()
      const timeoutAt = new Date(new Date(requestedAt).getTime() + 30_000).toISOString()
      pending.value.push({
        approvalId: event.approval_id as string,
        toolName: event.tool_name as string,
        argumentsSummary: (event.arguments_summary as string) ?? '',
        requestedAt,
        timeoutAt,
      })
    } else if (type === 'ApprovalGranted' || type === 'ApprovalDenied') {
      const id = event.approval_id as string
      pending.value = pending.value.filter(p => p.approvalId !== id)
    }
  }

  async function grant(approvalId: string): Promise<void> {
    try {
      await fetch(`${orchestratorUrl}/orchestrator/approval/${approvalId}/grant`, { method: 'POST' })
    } finally {
      pending.value = pending.value.filter(p => p.approvalId !== approvalId)
    }
  }

  async function deny(approvalId: string): Promise<void> {
    try {
      await fetch(`${orchestratorUrl}/orchestrator/approval/${approvalId}/deny`, { method: 'POST' })
    } finally {
      pending.value = pending.value.filter(p => p.approvalId !== approvalId)
    }
  }

  function expireOld() {
    const now = Date.now()
    pending.value = pending.value.filter(p => new Date(p.timeoutAt).getTime() > now)
  }

  function $reset() {
    pending.value = []
  }

  return { pending, applyEvent, grant, deny, expireOld, $reset }
})
