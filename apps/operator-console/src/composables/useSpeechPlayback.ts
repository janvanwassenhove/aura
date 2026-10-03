import { BRAIN_URL } from '../lib/endpoints'

/** U364: play his line through this laptop, in his own voice.
 *
 *  The console has had a "Laptop audio" switch since U209 and it reads the
 *  line with the browser's `speechSynthesis` — a Windows voice. That loses the
 *  character's own voice and speed (U349), and a line that changes persona
 *  halfway cannot survive it at all, because by then the line is text again.
 *
 *  The brain already synthesized the real thing. When the owner routes audio
 *  here, it holds that WAV under an id and publishes `SpeechAudioReady`; this
 *  fetches it once and plays it. Same bytes, so same voice.
 *
 *  U385: a queue, not a cut. The first version stopped whatever was playing
 *  when the next line arrived. That was survivable for whole lines and fatal
 *  for the live engine, whose reply arrives as a burst of ~1.4 s segments: the
 *  room would have heard the last fragment and nothing else. Lines now play in
 *  the order they arrived, each after the one before has finished.
 *
 *  And each line is fetched the moment it is announced, not when its turn
 *  comes. The brain holds only a handful of unfetched lines; a live reply
 *  queued behind a long one would otherwise age out before it was asked for.
 */

/** Ids already played. The brain serves each line once and 404s afterwards, so
 *  asking twice can only mean a replay — the last sentence again, into a quiet
 *  room. Guarded on both sides rather than relying on the server. */
const played = new Set<string>()

/** In arrival order. Each slot is the line's local blob URL once fetched, or
 *  null if it could not be — fetches finish in any order, slots do not. */
const queue: Promise<string | null>[] = []
let draining = false
let current: HTMLAudioElement | null = null
let finishCurrent: (() => void) | null = null
/** Bumped by every stop, so a fetch or a drain that started before it ends
 *  quietly instead of carrying the sentence on. */
let generation = 0

export function resetPlayback(): void {
  stopPlayback()
  played.clear()
}

/** U385: silence this laptop now and drop everything queued. Barge-in and the
 *  panic stop used to reach the robot's speaker only. */
export function stopPlayback(): void {
  generation += 1
  for (const slot of queue.splice(0)) {
    void slot.then((url) => { if (url) URL.revokeObjectURL(url) })
  }
  try { current?.pause() } catch { /* already gone */ }
  finishCurrent?.()
}

/** Queue one synthesized line. Resolves once it has been fetched (or could not
 *  be), never throws — audio is best-effort and must not break a turn or a
 *  beat. Playback happens in arrival order, after the line before it. */
export async function playUtterance(utteranceId: string): Promise<void> {
  if (!utteranceId || played.has(utteranceId)) return
  if (typeof Audio === 'undefined') return      // no audio in this browser
  played.add(utteranceId)
  const gen = generation
  const slot = fetchLine(utteranceId).then((url) => {
    if (url && gen !== generation) {             // stopped while it travelled
      URL.revokeObjectURL(url)
      return null
    }
    return url
  })
  queue.push(slot)
  if (!draining) void drain()
  await slot
}

/** What the event stream means for this laptop's speaker. Lives here rather
 *  than in the bus so the mapping can be tested where it is used. */
export function applySpeechEvent(raw: Record<string, unknown>): void {
  if (raw.event_type === 'SpeechAudioReady') {
    void playUtterance(String(raw.utterance_id ?? ''))
  } else if (raw.event_type === 'SpeechAudioStopped') {
    stopPlayback()
  }
}

async function fetchLine(utteranceId: string): Promise<string | null> {
  try {
    const r = await fetch(`${BRAIN_URL}/speech/${encodeURIComponent(utteranceId)}.wav`)
    if (!r.ok) return null
    return URL.createObjectURL(await r.blob())
  } catch {
    return null                                   // brain gone, line gone
  }
}

async function drain(): Promise<void> {
  draining = true
  try {
    while (queue.length > 0) {
      const gen = generation
      const url = await queue.shift()!
      if (!url) continue
      if (gen !== generation) { URL.revokeObjectURL(url); continue }
      await playOne(url)
    }
  } finally {
    draining = false
  }
}

function playOne(url: string): Promise<void> {
  return new Promise((resolve) => {
    const audio = new Audio(url)
    current = audio
    let done = false
    const finish = () => {
      if (done) return
      done = true
      URL.revokeObjectURL(url)
      if (current === audio) current = null
      if (finishCurrent === finish) finishCurrent = null
      resolve()
    }
    finishCurrent = finish
    audio.onended = finish
    audio.onerror = finish
    audio.play().catch(finish)                    // autoplay refused, device busy
  })
}
