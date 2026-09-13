import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import SettingsView from '../../src/views/SettingsView.vue'

/** U342: moving him to another laptop, from a screen that exists on a machine
 *  that knows nobody yet.
 *
 *  The old "Export the brain (JSON)" button lives inside a person's detail
 *  pane. That is survivable for export and impossible for import: a fresh
 *  install has no people, so there is no pane to open, so there is nowhere to
 *  put the file. The transfer belongs in Settings, which is reachable on an
 *  empty machine.
 *
 *  The passphrase is the owner's, typed here, and never stored — losing it
 *  costs an export file, not a knowledge base.
 */

const OK = (body: unknown) => Promise.resolve({
  ok: true, status: 200, json: () => Promise.resolve(body),
  text: () => Promise.resolve(JSON.stringify(body)),
} as Response)

type Posted = { url: string; body: Record<string, unknown> }

function stubFetch(posted: Posted[]): void {
  vi.stubGlobal('fetch', (url: string, init?: RequestInit) => {
    const u = String(url)
    if (init?.method === 'POST') {
      let body: Record<string, unknown> = {}
      try { body = JSON.parse(String(init.body ?? '{}')) } catch { /* not json */ }
      posted.push({ url: u, body })
    }
    if (u.includes('/connector/health')) return OK({ status: 'ok', connectors: {} })
    if (u.includes('/identity/status/')) return OK({ connected: false })
    if (u.includes('/capabilities')) return OK({ capabilities: [], allowed_apps: [] })
    if (u.includes('/config/llm/models')) return OK({ models: [] })
    if (u.includes('/config/llm')) return OK({ provider: 'openai', model: 'gpt-4o-mini' })
    if (u.includes('/transfer/export')) {
      return Promise.resolve({
        ok: true, status: 200,
        blob: () => Promise.resolve(new Blob(['{"format":"aura-brain-export"}'])),
        json: () => Promise.resolve({}),
        text: () => Promise.resolve('{"format":"aura-brain-export"}'),
      } as unknown as Response)
    }
    if (u.includes('/transfer/import')) return OK({ people: 2, facts: 7, faces: 3, skills: 1, skills_kept: 0 })
    return OK({})
  })
}

beforeEach(() => {
  vi.unstubAllGlobals()
  setActivePinia(createPinia())
  // jsdom has no object URLs and no real downloads.
  URL.createObjectURL = vi.fn(() => 'blob:test')
  URL.revokeObjectURL = vi.fn()
})
afterEach(() => vi.unstubAllGlobals())

describe('taking him to another laptop', () => {
  it('is offered in Settings, where a machine with no people can still reach it', async () => {
    stubFetch([])
    const w = mount(SettingsView)
    await flushPromises()

    expect(w.text()).toContain('Move him to another laptop')
    expect(w.find('[data-test="transfer-export"]').exists()).toBe(true)
    expect(w.find('[data-test="transfer-import"]').exists()).toBe(true)
  })

  it('will not export without a passphrase long enough to be one', async () => {
    const posted: Posted[] = []
    stubFetch(posted)
    const w = mount(SettingsView)
    await flushPromises()

    const btn = w.find('[data-test="transfer-export"]')
    expect(btn.attributes('disabled')).toBeDefined()

    await w.find('input[aria-label="Export passphrase"]').setValue('short')
    expect(btn.attributes('disabled')).toBeDefined()

    await w.find('input[aria-label="Export passphrase"]').setValue('long enough to be one')
    expect(btn.attributes('disabled')).toBeUndefined()
  })

  it('seals the export with the passphrase that was typed', async () => {
    const posted: Posted[] = []
    stubFetch(posted)
    const w = mount(SettingsView)
    await flushPromises()

    await w.find('input[aria-label="Export passphrase"]').setValue('long enough to be one')
    await w.find('[data-test="transfer-export"]').trigger('click')
    await flushPromises()

    const call = posted.find(p => p.url.includes('/transfer/export'))
    expect(call, 'nothing was exported').toBeTruthy()
    expect(call!.body.passphrase).toBe('long enough to be one')
    expect(w.html(), 'the passphrase stayed in the DOM').not.toContain('long enough to be one')
  })

  it('says what actually arrived on import, not just "done"', async () => {
    const posted: Posted[] = []
    stubFetch(posted)
    const w = mount(SettingsView)
    await flushPromises()

    await w.find('input[aria-label="Export passphrase"]').setValue('long enough to be one')
    const file = new File(['{"format":"aura-brain-export"}'], 'aura-brain.aura')
    const input = w.find('input[aria-label="Bundle file"]')
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change')
    await flushPromises()

    const call = posted.find(p => p.url.includes('/transfer/import'))
    expect(call, 'the file went nowhere').toBeTruthy()
    const said = w.text()
    expect(said).toContain('2')
    expect(said).toContain('7')
    expect(said.toLowerCase()).toMatch(/face/)
  })
})
