import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { readdirSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'

/** U370 (audit T4): every component under src/components mounts once.
 *
 *  Nine components had never been imported by any test — the setup wizard,
 *  the approval panel, both canvases, the confirm dialog, the nav rail. Some
 *  are reached transitively when a view mounts; several are behind a `v-if`
 *  that no test flips. With no `vue-tsc`, "never mounted" means "never
 *  compiled": a typo in a template is discovered by the person the dialog is
 *  shown to.
 *
 *  The list is the directory. A new component without a props entry below
 *  fails here with its path in the message, which is the reminder the working
 *  agreement asks for.
 */

const OK = (body: unknown) => Promise.resolve({
  ok: true, status: 200, json: () => Promise.resolve(body),
} as Response)

/** Required props, by path under src/components. Absent means "none". */
const PROPS: Record<string, Record<string, unknown>> = {
  'canvas/KnowledgeGraph.vue': { detail: null, peopleIds: [] },
  'ConfirmDialog.vue': { title: 'Sure?' },
  'WikiText.vue': { text: 'plain and [[linked]]' },
  'shell/AppHeader.vue': { wsStatus: 'closed' },
  'PhotoLightbox.vue': { src: 'data:image/png;base64,' },
  'shell/PickerMenu.vue': { open: false, items: [] },
}

function componentFiles(dir: string, base = dir): string[] {
  const out: string[] = []
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) out.push(...componentFiles(p, base))
    else if (name.endsWith('.vue')) out.push(relative(base, p).replace(/\\/g, '/'))
  }
  return out.sort()
}

const ROOT = resolve(__dirname, '../../src/components')
const modules = import.meta.glob('../../src/components/**/*.vue')

beforeEach(() => {
  vi.unstubAllGlobals()
  setActivePinia(createPinia())
  vi.stubGlobal('fetch', (url: string) => {
    const u = String(url)
    if (u.includes('/knowledge/people')) return OK([])
    if (u.includes('/capabilities')) return OK({ capabilities: [], allowed_apps: [] })
    if (u.includes('/orchestrator/policy')) return OK({ active_mode: 'work', modes: {}, quiet: false })
    if (u.includes('/setup/status')) return OK({ setup_done: false })
    if (u.includes('/setup/characters')) return OK([])
    if (u.includes('/robot/')) return OK({ connected: false })
    return OK({})
  })
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => setTimeout(() => cb(0), 0) as unknown as number)
  vi.stubGlobal('cancelAnimationFrame', (id: number) => clearTimeout(id))
  vi.stubGlobal('ResizeObserver', class { observe(): void {} unobserve(): void {} disconnect(): void {} })
})
afterEach(() => vi.unstubAllGlobals())

describe('every component under src/components', () => {
  const files = componentFiles(ROOT)

  it('is a real list, read from the directory', () => {
    expect(files.length).toBeGreaterThanOrEqual(9)
  })

  for (const file of files) {
    it(`mounts ${file}`, async () => {
      const loader = modules[`../../src/components/${file}`]
      expect(loader, `no module for ${file}`).toBeTruthy()
      const mod = await loader() as { default: unknown }

      const errors: unknown[] = []
      const err = vi.spyOn(console, 'error').mockImplementation(e => { errors.push(e) })
      const warn = vi.spyOn(console, 'warn').mockImplementation(w => {
        if (String(w).includes('[Vue warn]')) errors.push(w)
      })

      const w = mount(mod.default as never, { props: PROPS[file] ?? {} })
      await flushPromises()
      w.unmount()

      expect(errors, `${file} threw or warned — add its required props to PROPS if that is the cause`).toEqual([])
      warn.mockRestore(); err.mockRestore()
    })
  }
})
