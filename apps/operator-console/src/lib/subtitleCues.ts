/** U400: a spoken line as subtitles — cut where a reader would, timed to how
 *  long he actually takes to say it.
 *
 *  Reported as "subtitles are not following fluently with talking, should be
 *  in sync". The overlay showed a whole line at once, for a guess. These are
 *  the cinema convention instead: at most two short lines on screen, the next
 *  piece when he gets to it. Without word timings from the speech engine, each
 *  piece gets the share of the time its length earns — the same pace he reads
 *  at, which is close enough for the eye to follow the ear.
 */

/** Two lines of ~42 characters: what a room can read in one glance. */
export const MAX_CUE = 84

export interface Cue {
  text: string
  from: number
  to: number
}

/** Cut a line into pieces no longer than `max`: by sentence, a long sentence
 *  at its commas, a run-on between words — never inside a word. Short
 *  neighbours are put back together so a quick line is not a flicker. */
export function splitCues(text: string, max = MAX_CUE): string[] {
  const clean = (text || '').replace(/\s+/g, ' ').trim()
  if (!clean) return []
  const sentences = clean.split(/(?<=[.!?…])\s+/)
  const pieces: string[] = []
  for (const s of sentences) {
    if (s.length <= max) { pieces.push(s); continue }
    for (const clause of s.split(/(?<=[,;:—–])\s+/)) {
      if (clause.length <= max) { pieces.push(clause); continue }
      let line = ''
      for (const word of clause.split(' ')) {
        if (line && (line + ' ' + word).length > max) { pieces.push(line); line = word }
        else line = line ? line + ' ' + word : word
      }
      if (line) pieces.push(line)
    }
  }
  const merged: string[] = []
  for (const p of pieces) {
    const last = merged[merged.length - 1]
    if (last !== undefined && (last + ' ' + p).length <= max) merged[merged.length - 1] = last + ' ' + p
    else merged.push(p)
  }
  return merged
}

/** Give each piece its share of `durationMs`, starting at `startMs`. A small
 *  allowance per piece stands in for the breath between them. */
export function timeCues(cues: string[], startMs: number, durationMs: number): Cue[] {
  if (!cues.length) return []
  const weights = cues.map(c => c.length + 8)
  const total = weights.reduce((a, b) => a + b, 0)
  const out: Cue[] = []
  let at = startMs
  cues.forEach((text, i) => {
    const to = i === cues.length - 1 ? startMs + durationMs
      : at + Math.round(durationMs * weights[i] / total)
    out.push({ text, from: at, to })
    at = to
  })
  return out
}
