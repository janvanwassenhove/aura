/** How a scenario's beats read on screen.
 *
 * U269: this lived inside PresentView, which meant the overlay — a separate
 * window with a separate Pinia store — had no way to describe a beat at all.
 * Its "next cue" row read a beat array that is only ever filled by the window
 * that pressed Start, so in the overlay it was permanently empty and the row
 * never rendered. Reported as "nor for the overlay did i see cues".
 *
 * Both windows now build their rows from the same scenario, fetched from the
 * brain, through this one function — so a cue cannot mean one thing on the
 * console and something else on the projector.
 */

export interface RawBeat {
  id?: string
  mode?: string
  text?: string
  topic?: string
  motion?: string
  gesture?: string | null
  /** The builder and the brain both write this as a STRING: "manual",
   *  "slide:4", "keyword:Java". U266: reading it as an object threw a
   *  TypeError that killed the whole handler before anything was sent. */
  trigger?: unknown
}

export interface BeatRow {
  id: string
  cue: string
  kind: 'manual' | 'slide' | 'keyword'
  say: string
  do: string
}

export function triggerOf(b: RawBeat): string {
  return typeof b.trigger === 'string' ? b.trigger : 'manual'
}

/** U267: three kinds, not two. Everything that was not a keyword used to be
 *  labelled "slide" — so a beat that waits for the presenter wore the badge
 *  of one that fires by itself, which is exactly the confusion behind
 *  "do i need to advance beat? should be triggered automatically". */
export function kindOf(b: RawBeat): BeatRow['kind'] {
  const t = triggerOf(b)
  if (t.startsWith('keyword:')) return 'keyword'
  if (t.startsWith('slide:')) return 'slide'
  return 'manual'
}

/** The cue, said as the thing that makes it happen — not as a row number. */
export function cueOf(b: RawBeat): string {
  const t = triggerOf(b)
  if (t.startsWith('keyword:')) return `“${t.slice('keyword:'.length)}”`
  if (t.startsWith('slide:')) return `Slide ${t.slice('slide:'.length)}`
  return 'You press Advance beat'
}

export function toRows(beats: RawBeat[] | undefined): BeatRow[] {
  return (beats ?? []).map((b, i) => ({
    id: b.id ?? `beat-${i + 1}`,
    cue: cueOf(b),
    kind: kindOf(b),
    say: b.text || b.topic || '',
    do: b.motion ?? b.gesture ?? b.mode ?? '',
  }))
}
