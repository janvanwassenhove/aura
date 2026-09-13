/** U349: inline persona markers, read from the console's side.
 *
 *  `[persona:some_id]` inside a beat's text hands the line to another
 *  character mid-sentence; `[persona]` hands it back. The brain owns the
 *  grammar (shared_schemas/presentation/vocals.py) and the fallback when an id
 *  turns out to name nobody — but that fallback happens on stage, which is the
 *  wrong moment to discover a typo. This is the same pattern, used at a desk,
 *  to say so while it is still cheap to fix.
 *
 *  Keep the expression below in step with `_MARKER` in that module.
 */
const MARKER = /\[\s*(\/?)\s*persona\s*(?::\s*([A-Za-z0-9_.\-]+)\s*)?\]/gi

/** Every distinct persona a line hands over to, in the order it first speaks.
 *  The closing marker names nobody, so it contributes nothing. */
export function personaIdsIn(text: string): string[] {
  const found: string[] = []
  for (const m of String(text ?? '').matchAll(MARKER)) {
    const [, closing, id] = m
    if (closing || !id) continue
    if (!found.includes(id)) found.push(id)
  }
  return found
}
