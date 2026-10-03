// U265/U266: the presentation overlay's bookkeeping — which window is on the
// beamer, and what the console is told about it. Moved out of main.cjs so it
// can be exercised with fake windows (U386); main.cjs supplies the factory.

function createPresentOverlay({ makeWindow }) {
  let win = null
  let state = { shown: false, mode: 'audience', displayId: null }

  // U386: destroy(), not close(). close() is asynchronous and a page may
  // refuse it; destroy() is immediate and cannot be refused — the same choice
  // the U75 screen-control overlay made. "Take it down" has to mean now.
  function hide() {
    const w = win
    win = null
    state = { ...state, shown: false }
    if (w) {
      try { w.destroy() } catch { /* already gone */ }
    }
  }

  function show(target, opts = {}) {
    const { mode = 'audience' } = opts
    hide()
    const w = makeWindow(target, opts)
    win = w
    // U386: only the window that IS current may clear the reference. A
    // re-show used to let the OLD window's late 'closed' null out the NEW
    // one, which then stayed on the beamer with nothing able to take it down.
    w.on('closed', () => {
      if (win !== w) return
      win = null
      state = { ...state, shown: false }
    })
    state = { shown: true, mode, displayId: target.id }
    return { ...state, display: target.id }
  }

  function current() {
    return { ...state, shown: state.shown && !!win }
  }

  return { show, hide, state: current, window: () => win }
}

module.exports = { createPresentOverlay }
