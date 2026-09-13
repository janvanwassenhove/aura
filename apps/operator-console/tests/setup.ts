import { Storage } from 'happy-dom'

/** U350: put Web Storage back, because the environment stopped providing it.
 *
 *  Vitest builds the happy-dom environment by copying the window's properties
 *  onto Node's `globalThis`, and `getWindowKeys` drops any name that is
 *  *already* on `globalThis` unless that name is on vitest's own hard-coded
 *  list. `localStorage` is not on that list — not in 4.1.5, not in 4.1.11 —
 *  and for the whole life of this repository that did not matter, because Node
 *  had no `localStorage` to collide with.
 *
 *  Node 25 has one. Verified on this machine: `'localStorage' in globalThis`
 *  is false on Node 20.20.2, 22.23.2 and 24.21.0, and true on 25.8.0. So on
 *  Node 25 the copy is skipped, happy-dom's real Storage never reaches the
 *  tests, and what the console talks to is Node's own Web Storage — inert
 *  without a `--localstorage-file`, an object with no `getItem`, no `setItem`
 *  and no `clear`. Nine test files open with `localStorage.clear()`; 57 tests
 *  died on that line, having asserted nothing about the product.
 *
 *  CI pins Node 20 (`.github/workflows/ci.yml`) and never saw any of it. That
 *  is the part worth remembering: this was green everywhere it was measured
 *  and red on the only machine anyone actually develops on.
 *
 *  Two deliberate choices:
 *
 *  - **happy-dom's own `Storage`, not a hand-written stand-in.** It is the
 *    exact class the environment was supposed to install, so the tests keep
 *    browser semantics — a miss is `null`, a value is coerced to a string —
 *    rather than a lookalike's. It is already in `package.json`; nothing new
 *    is being installed, here or anywhere else.
 *  - **Unconditionally, not `if (!globalThis.localStorage.clear)`.** The suite
 *    should not run one environment on the laptop and a different one in CI.
 *    A fresh instance per test file also comes free, since setup files re-run
 *    per file — which is what `tests/environment.test.ts` pins.
 */
for (const name of ['localStorage', 'sessionStorage'] as const) {
  Object.defineProperty(globalThis, name, {
    value: new Storage(),
    writable: true,
    configurable: true,
    enumerable: true,
  })
}
