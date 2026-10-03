// U391: the "AURA controls the screen" overlay must never outlive the action.
//
// U75's overlay draws a ring round the cursor, shows a banner, and registers
// Esc as a GLOBAL shortcut that aborts the run — whatever app has focus.
// Until U391 it never appeared, because the events that switch it were not
// broadcast. Switching it on made one failure matter: if the console misses
// the "ended" event — a dropped socket, a reloaded window, a crashed renderer —
// the overlay stays up and keeps Esc. In a PowerPoint slideshow, Esc is the
// key that ends the show.
//
// So it is a dead-man's switch: the console keeps confirming it while the
// brain says he is still driving, and the shell takes it down by itself when
// the confirmations stop.
//
// Plain node — run with `node apps/desktop/test-screen-control.cjs`.
const assert = require('assert')
const { createScreenControlWarning } = require('./screen-control.cjs')

/** A clock the test moves by hand. */
function fakeClock() {
  let now = 0
  let timers = []
  return {
    setTimeout: (fn, ms) => { const t = { at: now + ms, fn }; timers.push(t); return t },
    clearTimeout: (t) => { timers = timers.filter((x) => x !== t) },
    advance(ms) {
      now += ms
      const due = timers.filter((t) => t.at <= now)
      timers = timers.filter((t) => t.at > now)
      due.forEach((t) => t.fn())
    },
  }
}

function warning(clock) {
  const log = []
  const w = createScreenControlWarning({
    show: () => log.push('show'), hide: () => log.push('hide'),
    keepAliveMs: 15000, setTimeout: clock.setTimeout, clearTimeout: clock.clearTimeout,
  })
  return { w, log }
}

// --- the reported failure: an "ended" that never arrives --------------------
{
  const clock = fakeClock()
  const { w, log } = warning(clock)
  w.set(true)
  clock.advance(16000)
  assert.deepStrictEqual(log, ['show', 'hide'],
    'with nobody confirming it, the overlay must come down by itself and free Esc')
  assert.strictEqual(w.isOn(), false)
  console.log('ok  an unconfirmed warning lapses on its own')
}

// --- while the console keeps confirming, it stays ---------------------------
{
  const clock = fakeClock()
  const { w, log } = warning(clock)
  w.set(true)
  for (let i = 0; i < 20; i++) { clock.advance(3000); w.set(true) }   // a minute of polls
  assert.deepStrictEqual(log, ['show'], 'confirmed every 3 s, it must neither flicker nor drop')
  console.log('ok  a confirmed warning stays up without flickering')
}

// --- and an explicit end takes it down at once ------------------------------
{
  const clock = fakeClock()
  const { w, log } = warning(clock)
  w.set(true)
  w.set(false)
  clock.advance(60000)
  assert.deepStrictEqual(log, ['show', 'hide'], 'ended means down now, and nothing fires later')
  console.log('ok  an end takes it down at once')
}

// --- a stale "off" from a console that just started is harmless -------------
{
  const clock = fakeClock()
  const { w, log } = warning(clock)
  w.set(false)
  assert.deepStrictEqual(log, [])
  console.log('ok  clearing nothing does nothing')
}
