// U75: whether the "AURA controls the screen" overlay is up. Moved out of
// main.cjs so it can be driven with a fake clock (U391); main.cjs supplies
// show/hide.
//
// U391: a dead-man's switch. The overlay registers Esc as a GLOBAL shortcut,
// so a warning that outlives the action steals Esc from every app — and in a
// PowerPoint slideshow Esc ends the show. The console confirms the warning
// every few seconds while the brain says he is still driving; when the
// confirmations stop (an "ended" that never arrived, a reloaded or crashed
// console), the warning lapses here on its own.

function createScreenControlWarning({
  show, hide, keepAliveMs = 15000,
  setTimeout: arm = setTimeout, clearTimeout: disarm = clearTimeout,
}) {
  let on = false
  let deadline = null

  function lapse() {
    deadline = null
    if (on) { on = false; hide() }
  }

  function set(active) {
    if (deadline) { disarm(deadline); deadline = null }
    if (active) {
      if (!on) { on = true; show() }
      deadline = arm(lapse, keepAliveMs)
    } else if (on) {
      on = false
      hide()
    }
  }

  return { set, isOn: () => on }
}

module.exports = { createScreenControlWarning }
