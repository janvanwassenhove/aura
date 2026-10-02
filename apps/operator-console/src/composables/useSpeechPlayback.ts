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
 *  Served as WAV precisely so this can be an `<audio>` element rather than
 *  hand-decoded PCM through the Web Audio API.
 */

/** Ids already played. The brain serves each line once and 404s afterwards, so
 *  asking twice can only mean a replay — the last sentence again, into a quiet
 *  room. Guarded on both sides rather than relying on the server. */
const played = new Set<string>()
let current: HTMLAudioElement | null = null

export function resetPlayback(): void {
  stopPlayback()
  played.clear()
}

export function stopPlayback(): void {
  try { current?.pause() } catch { /* already gone */ }
  current = null
}

/** Play one synthesized line. Resolves when playback has been started (or
 *  could not be), never throws — audio is best-effort and must not break a
 *  turn or a beat. */
export async function playUtterance(utteranceId: string): Promise<void> {
  if (!utteranceId || played.has(utteranceId)) return
  if (typeof Audio === 'undefined') return      // no audio in this browser
  played.add(utteranceId)
  try {
    // One at a time: two beats on one slide run back to back, and overlapping
    // them is two voices out of one speaker.
    stopPlayback()
    const audio = new Audio(`${BRAIN_URL}/speech/${encodeURIComponent(utteranceId)}.wav`)
    current = audio
    audio.onended = () => { if (current === audio) current = null }
    audio.onerror = () => { if (current === audio) current = null }
    await audio.play()
  } catch {
    current = null      // autoplay refused, file gone, device busy
  }
}
