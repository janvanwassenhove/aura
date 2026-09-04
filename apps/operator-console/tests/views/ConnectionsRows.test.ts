import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useConnectionsStore } from '../../src/stores/connectionsStore'

/** U298: "app-ids is enige manier? er niks gebruiksvriendelijker?"
 *
 *  No. A calendar can be connected by pasting its published .ics link, which
 *  needs no app, no consent screen and no sign-in — so the panel has a row
 *  for it, and the brain has a connector behind it.
 */
describe('U298 — the connection that registers nothing', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('offers a calendar-by-link row', () => {
    const store = useConnectionsStore()
    const row = store.providers.find(p => p.provider === 'calendar')
    expect(row).toBeDefined()
    expect(row!.label).toContain('link')
  })

  it('lists it before the ones that need an app registration', () => {
    const store = useConnectionsStore()
    const order = store.providers.map(p => p.provider)
    expect(order.indexOf('calendar')).toBeLessThan(order.indexOf('microsoft'))
  })

  it('maps it to the connector key the brain reports under', async () => {
    const store = useConnectionsStore()
    // The brain answers about "calendar_link"; the console calls the row
    // "calendar". If that mapping is missing the row stays "unknown" forever.
    globalThis.fetch = (async () => ({
      ok: true,
      json: async () => ({
        connectors: { calendar_link: 'ok' },
        details: [{ key: 'calendar_link', status: 'ok', detail: 'Connected.', domains: ['calendar'] }],
        live_domains: ['calendar'],
      }),
    })) as unknown as typeof fetch
    await store.refreshAllStatuses()
    expect(store.providers.find(p => p.provider === 'calendar')!.status).toBe('ok')
  })

  it('never asks identity whether a pasted link is signed in', async () => {
    const store = useConnectionsStore()
    const asked: string[] = []
    globalThis.fetch = (async (url: string) => {
      asked.push(String(url))
      // Health says nothing about any connector, so identity is asked about
      // every row it is allowed to ask about.
      return { ok: true, json: async () => ({}) }
    }) as unknown as typeof fetch
    await store.refreshAllStatuses()
    // A link is not an account; asking would report "not signed in" forever.
    expect(asked.some(u => u.includes('/identity/') && u.includes('calendar_link')))
      .toBe(false)
    expect(asked.some(u => u.includes('/identity/') && u.includes('m365')))
      .toBe(true)   // the ones that ARE accounts are still asked
  })
})
