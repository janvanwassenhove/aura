import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import UpdateBanner from '../../src/components/UpdateBanner.vue'

/** U197: the banner is the whole point of the new update flow — the installer
 *  is already on disk by the time it appears, so "install" is one click. */

type Ready = { version: string; tag: string }

function stubBridge(overrides: Record<string, unknown> = {}) {
  let fire: ((i: Ready) => void) | null = null
  const bridge = {
    isElectron: true,
    onUpdateReady: (cb: (i: Ready) => void) => { fire = cb; return () => { fire = null } },
    installUpdate: vi.fn(async () => ({ ok: true })),
    dismissUpdate: vi.fn(async () => ({ ok: true })),
    ...overrides,
  }
  ;(window as any).aura = bridge
  return { bridge, announce: (i: Ready) => fire?.(i) }
}

beforeEach(() => { delete (window as any).aura })

describe('UpdateBanner', () => {
  it('stays out of the way until an update is actually staged', () => {
    stubBridge()
    const w = mount(UpdateBanner)
    expect(w.text()).toBe('')
  })

  it('names the version once the installer is downloaded', async () => {
    const { announce } = stubBridge()
    const w = mount(UpdateBanner)
    announce({ version: '2.1.0', tag: 'v2.1.0' })
    await w.vm.$nextTick()
    expect(w.text()).toContain('2.1.0')
    expect(w.text()).toContain('staat klaar om te installeren')
  })

  it('installs on click', async () => {
    const { bridge, announce } = stubBridge()
    const w = mount(UpdateBanner)
    announce({ version: '2.1.0', tag: 'v2.1.0' })
    await w.vm.$nextTick()
    await w.find('.upd-btn--go').trigger('click')
    expect(bridge.installUpdate).toHaveBeenCalled()
  })

  it('shows why it failed instead of quietly doing nothing', async () => {
    const { announce } = stubBridge({
      installUpdate: vi.fn(async () => ({ ok: false, error: 'installer ontbreekt' })),
    })
    const w = mount(UpdateBanner)
    announce({ version: '2.1.0', tag: 'v2.1.0' })
    await w.vm.$nextTick()
    await w.find('.upd-btn--go').trigger('click')
    await new Promise(r => setTimeout(r))
    expect(w.text()).toContain('installer ontbreekt')
    // Still usable: a failed install must not leave the button dead.
    expect((w.find('.upd-btn--go').element as HTMLButtonElement).disabled).toBe(false)
  })

  it('"Later" hides the banner without skipping the version', async () => {
    const { bridge, announce } = stubBridge()
    const w = mount(UpdateBanner)
    announce({ version: '2.1.0', tag: 'v2.1.0' })
    await w.vm.$nextTick()
    await w.findAll('.upd-btn')[1].trigger('click')
    await w.vm.$nextTick()
    expect(w.text()).toBe('')
    expect(bridge.dismissUpdate).toHaveBeenCalled()
  })

  it('is silent in a plain browser, where nothing can stage an installer', () => {
    const w = mount(UpdateBanner)     // no window.aura at all
    expect(w.text()).toBe('')
  })
})
