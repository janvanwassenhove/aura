import { ref } from 'vue'

/** U390: a panel the owner can make taller or shorter by dragging its top
 *  edge — the activity log under the conversation on the Talk screen.
 *
 *  Reported as "i should be able to drag/resize bottom window in talk screen",
 *  with a screenshot of the log squeezed to two lines. It was `flex: 0 1
 *  150px`: shrinkable, so whenever the conversation wanted room the log gave
 *  it up, and there was no way to ask for it back.
 *
 *  The height is remembered on this machine, like the other layout choices
 *  (`aura-density`, `aura-overlay`): it is how this person likes this screen,
 *  not something the brain needs to know.
 */

export interface DragHeightOptions {
  /** localStorage key the height is kept under. */
  key: string
  /** Where it starts, and where a double-click puts it back. */
  initial: number
  /** Never smaller than this: the tab bar plus a couple of lines. */
  min: number
  /** The most it may take given the space there is right now. Zero or less
   *  means "unknown" (not laid out yet), which limits nothing. */
  max: () => number
  /** How far one arrow-key press moves it. */
  step?: number
}

export function useDragHeight(opts: DragHeightOptions) {
  const step = opts.step ?? 24

  function limit(): number {
    const m = opts.max()
    return m > opts.min ? m : Infinity
  }
  function clamp(h: number): number {
    return Math.round(Math.max(opts.min, Math.min(h, limit())))
  }
  function read(): number {
    try {
      const v = Number(localStorage.getItem(opts.key))
      if (Number.isFinite(v) && v > 0) return v
    } catch { /* storage blocked: start from the default */ }
    return opts.initial
  }
  function save(): void {
    try { localStorage.setItem(opts.key, String(height.value)) } catch { /* session-only */ }
  }

  const height = ref(clamp(read()))
  let dragging = false
  let startY = 0
  let startH = 0

  function onPointerDown(ev: PointerEvent): void {
    dragging = true
    startY = ev.clientY
    startH = height.value
    try { (ev.currentTarget as HTMLElement | null)?.setPointerCapture?.(ev.pointerId) } catch { /* fine */ }
    ev.preventDefault()        // no text selection while dragging
  }
  function onPointerMove(ev: PointerEvent): void {
    if (!dragging) return
    // The grip sits on the panel's TOP edge: moving up makes it taller.
    height.value = clamp(startH + (startY - ev.clientY))
  }
  function onPointerUp(ev: PointerEvent): void {
    if (!dragging) return
    dragging = false
    try { (ev.currentTarget as HTMLElement | null)?.releasePointerCapture?.(ev.pointerId) } catch { /* fine */ }
    save()
  }
  /** Keyboard too: a resize handle you can only use with a mouse is half a
   *  control. Up grows, Down shrinks, Home/End go to the limits. */
  function onKeydown(ev: KeyboardEvent): void {
    const next = ev.key === 'ArrowUp' ? height.value + step
      : ev.key === 'ArrowDown' ? height.value - step
        : ev.key === 'Home' ? opts.min
          : ev.key === 'End' ? limit()
            : null
    if (next == null) return
    ev.preventDefault()
    height.value = clamp(Number.isFinite(next) ? next : height.value)
    save()
  }
  function reset(): void {
    height.value = clamp(opts.initial)
    save()
  }
  /** After the window shrinks, a remembered height may no longer fit. Not
   *  saved: making the window bigger again should give it back. */
  function reclamp(): void {
    height.value = clamp(read())
  }

  return { height, onPointerDown, onPointerMove, onPointerUp, onKeydown, reset, reclamp }
}
