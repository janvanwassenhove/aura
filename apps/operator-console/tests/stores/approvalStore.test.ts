import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useApprovalStore } from '../../src/stores/approvalStore'

describe('approvalStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    // Mock fetch so grant/deny don't fail in test
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true } as Response)
  })

  it('starts with no pending approvals', () => {
    const store = useApprovalStore()
    expect(store.pending).toHaveLength(0)
  })

  it('applyEvent ApprovalRequested adds a pending entry', () => {
    const store = useApprovalStore()
    store.applyEvent({
      event_type: 'ApprovalRequested',
      approval_id: 'abc-123',
      tool_name: 'send_mail',
      arguments_summary: 'to: alice@example.com',
      timestamp: new Date().toISOString(),
    })
    expect(store.pending).toHaveLength(1)
    expect(store.pending[0].toolName).toBe('send_mail')
    expect(store.pending[0].approvalId).toBe('abc-123')
  })

  it('applyEvent ApprovalGranted removes the pending entry', () => {
    const store = useApprovalStore()
    store.applyEvent({ event_type: 'ApprovalRequested', approval_id: 'xyz', tool_name: 'send_mail', timestamp: new Date().toISOString() })
    store.applyEvent({ event_type: 'ApprovalGranted', approval_id: 'xyz' })
    expect(store.pending).toHaveLength(0)
  })

  it('applyEvent ApprovalDenied removes the pending entry', () => {
    const store = useApprovalStore()
    store.applyEvent({ event_type: 'ApprovalRequested', approval_id: 'xyz', tool_name: 'send_mail', timestamp: new Date().toISOString() })
    store.applyEvent({ event_type: 'ApprovalDenied', approval_id: 'xyz' })
    expect(store.pending).toHaveLength(0)
  })

  it('grant() calls fetch and removes the entry', async () => {
    const store = useApprovalStore()
    store.applyEvent({ event_type: 'ApprovalRequested', approval_id: 'grant-id', tool_name: 'post_teams_message', timestamp: new Date().toISOString() })
    await store.grant('grant-id')
    expect(store.pending).toHaveLength(0)
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/grant-id/grant'), expect.any(Object))
  })

  it('deny() calls fetch and removes the entry', async () => {
    const store = useApprovalStore()
    store.applyEvent({ event_type: 'ApprovalRequested', approval_id: 'deny-id', tool_name: 'delete_task', timestamp: new Date().toISOString() })
    await store.deny('deny-id')
    expect(store.pending).toHaveLength(0)
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/deny-id/deny'), expect.any(Object))
  })

  it('expireOld removes timed-out entries', () => {
    const store = useApprovalStore()
    // Add one already expired (timeout in the past)
    store.pending.push({
      approvalId: 'old',
      toolName: 'send_mail',
      argumentsSummary: '',
      requestedAt: new Date(Date.now() - 60_000).toISOString(),
      timeoutAt: new Date(Date.now() - 1_000).toISOString(),
    })
    store.expireOld()
    expect(store.pending).toHaveLength(0)
  })
})
