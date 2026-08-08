import { onMounted, onUnmounted, type Ref } from 'vue'

// U222 (a11y): every overlay in this app opened with no keyboard path out.
// `@click.self="close"` is mouse-only, nothing took focus, and nothing gave it
// back — so a keyboard or screen-reader user landed in a dialog they could not
// dismiss, with the page still tabbable behind it (WCAG 2.1.2, 2.4.3, 2.4.7).
//
// One composable rather than five copies: the behaviour is identical everywhere
// and a per-component version is exactly how three of the five drifted apart.

export interface ModalOptions {
  /** Called on Escape. Usually the component's close emit. */
  onClose: () => void
  /** The dialog root — focused on open so the screen reader lands inside it. */
  root?: Ref<HTMLElement | null>
  /** Focus this instead of the root (e.g. the safest button in a destructive
   *  prompt). */
  initialFocus?: Ref<HTMLElement | null>
}

export function useModal(opts: ModalOptions): void {
  let previouslyFocused: HTMLElement | null = null

  function onKeydown(ev: KeyboardEvent): void {
    if (ev.key !== 'Escape') return
    ev.stopPropagation()
    opts.onClose()
  }

  onMounted(() => {
    previouslyFocused = document.activeElement as HTMLElement | null
    // Keep focus INSIDE the dialog: a plain focus() on a div needs tabindex="-1",
    // which the callers set on their root.
    const target = opts.initialFocus?.value ?? opts.root?.value
    target?.focus?.()
    document.addEventListener('keydown', onKeydown)
  })

  onUnmounted(() => {
    document.removeEventListener('keydown', onKeydown)
    // Return focus where it came from, so closing a dialog doesn't dump the
    // user back at the top of the document.
    previouslyFocused?.focus?.()
  })
}
