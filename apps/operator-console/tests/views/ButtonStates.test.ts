import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, resolve } from 'path'

/** U356: the ghost button is the app's workhorse — 17 of them across ten views
 *  are `:disabled` under some condition — and it had no disabled styling at
 *  all. Reported as "brain import -> clicking button does not work": the
 *  button was disabled, looked exactly like a live one, kept `cursor: pointer`
 *  and still lit up accent on hover, so the only way to discover it was gated
 *  was to keep clicking.
 *
 *  There is no `vue-tsc` here and jsdom applies none of this CSS, so the rule
 *  is checked where it lives. A style test is a poor substitute for seeing it,
 *  but it is far better than the nothing that let this ship.
 */
const css = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../../src/App.vue'), 'utf-8')

describe('U356 — disabled buttons look disabled', () => {
  it('dims the ghost button and refuses the cursor', () => {
    expect(css).toMatch(/\.d2-ghost-btn:disabled\s*\{[^}]*opacity/)
    expect(css).toMatch(/\.d2-ghost-btn:disabled\s*\{[^}]*not-allowed/)
  })

  it('stops it lighting up on hover once it is dead', () => {
    // The hover rule is what actively LIED — accent border on something that
    // would do nothing. It has to exclude :disabled.
    const hover = css.match(/\.d2-ghost-btn:hover[^{]*\{/)
    expect(hover, 'the ghost hover rule went missing').toBeTruthy()
    expect(hover![0]).toContain(':not(:disabled)')
  })

  it('leaves the primary button as it already was', () => {
    // It had this right from the start; this test exists so a tidy-up of the
    // rules above cannot quietly take it away.
    expect(css).toMatch(/\.d2-primary-btn:disabled\s*\{[^}]*opacity/)
    expect(css).toMatch(/\.d2-primary-btn:hover:not\(:disabled\)/)
  })
})
