// U386: "Take it down" stopped working.
//
// Reported as "taking down overlay does no longer respond neither".
//
// Showing the overlay again — pressing Show twice, or ticking "Show what he
// sees", which re-shows it so the camera lands at once — closed window A and
// created window B straight away. `close()` is asynchronous: A's 'closed'
// event arrived a moment later, and its handler set the ONE shared reference
// to null. That reference was B's by then. B stayed on the beamer with nothing
// pointing at it, so every later "Take it down" found nothing to close, and
// the state reported "not shown" over a live overlay.
//
// Plain node — run with `node apps/desktop/test-present-overlay.cjs`.
const assert = require('assert')
const { EventEmitter } = require('events')
const { createPresentOverlay } = require('./present-overlay.cjs')

/** A window whose close, like Electron's, reports back LATER. */
class FakeWindow extends EventEmitter {
  constructor(name) { super(); this.name = name; this.alive = true }
  close() { setImmediate(() => this.die()) }      // async, like Electron
  destroy() { this.die() }                        // immediate, cannot be refused
  die() { if (this.alive) { this.alive = false; this.emit('closed') } }
}

function overlay() {
  const made = []
  const ov = createPresentOverlay({
    makeWindow: () => { const w = new FakeWindow(`w${made.length + 1}`); made.push(w); return w },
  })
  return { ov, made }
}
const tick = () => new Promise((r) => setImmediate(r))
const BEAMER = { id: 2 }

async function main() {
  // --- the reported one: show, show again, then take it down ----------------
  {
    const { ov, made } = overlay()
    ov.show(BEAMER)
    ov.show(BEAMER)              // re-show: camera toggled, or Show pressed twice
    await tick(); await tick()   // the first window's late 'closed' arrives
    assert.strictEqual(ov.window(), made[1],
      "the first window's late 'closed' must not orphan the second")
    assert.ok(ov.state().shown, 'a live overlay must not be reported as not shown')

    ov.hide()
    await tick(); await tick()
    assert.ok(made.every((w) => !w.alive), `still on the beamer: ${made.filter((w) => w.alive).map((w) => w.name)}`)
    assert.strictEqual(ov.state().shown, false)
    console.log('ok  showing it twice still leaves one overlay that Take it down removes')
  }

  // --- hide is immediate: nothing is left for a late event to undo ---------
  {
    const { ov, made } = overlay()
    ov.show(BEAMER)
    ov.hide()
    assert.strictEqual(made[0].alive, false, 'Take it down must remove the window now, not later')
    console.log('ok  Take it down removes the window at once')
  }

  // --- the user closing it some other way is still noticed -----------------
  {
    const { ov, made } = overlay()
    ov.show(BEAMER)
    made[0].die()
    assert.strictEqual(ov.state().shown, false)
    console.log('ok  an overlay that went away by itself is reported as gone')
  }

  // --- and the state says where it is ------------------------------------------
  {
    const { ov } = overlay()
    const r = ov.show(BEAMER, { mode: 'presenter' })
    assert.deepStrictEqual(r, { shown: true, mode: 'presenter', displayId: 2, display: 2 })
    console.log('ok  the state names the mode and the display')
  }
}

main().catch((e) => { console.error(e.message); process.exit(1) })
