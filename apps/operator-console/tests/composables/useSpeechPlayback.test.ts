import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { playUtterance, resetPlayback } from '../../src/composables/useSpeechPlayback'

/** U364: his real voice, out of this laptop.
 *
 *  The brain synthesizes once. When the owner sends audio here instead of the
 *  robot, it holds that WAV under an id and says so on the bus; this plays it.
 *  Same voice, same speed, same mid-line persona switch — because it is the
 *  same bytes, not a second reading by the browser (which is all U209 could do).
 */

class FakeAudio {
  static made: FakeAudio[] = []
  src = ''
  volume = 1
  played = 0
  onended: (() => void) | null = null
  onerror: (() => void) | null = null
  constructor(src?: string) { this.src = src ?? ''; FakeAudio.made.push(this) }
  play() { this.played += 1; return Promise.resolve() }
  pause() { /* nothing */ }
}

beforeEach(() => {
  setActivePinia(createPinia())
  FakeAudio.made = []
  resetPlayback()
  vi.stubGlobal('Audio', FakeAudio as unknown as typeof Audio)
})
afterEach(() => vi.unstubAllGlobals())

describe('useSpeechPlayback', () => {
  it('fetches the line the brain is holding and plays it', async () => {
    await playUtterance('abc123')

    expect(FakeAudio.made).toHaveLength(1)
    expect(FakeAudio.made[0].src).toContain('/speech/abc123.wav')
    expect(FakeAudio.made[0].played).toBe(1)
  })

  it('plays one line at a time', async () => {
    // Two beats on one slide run back to back. Overlapping them would be two
    // voices talking over each other out of the same speaker.
    await playUtterance('one')
    await playUtterance('two')

    expect(FakeAudio.made).toHaveLength(2)
    expect(FakeAudio.made[0].src).toContain('one')
    expect(FakeAudio.made[1].src).toContain('two')
  })

  it('ignores an utterance with no id rather than fetching nonsense', async () => {
    await playUtterance('')
    expect(FakeAudio.made).toHaveLength(0)
  })

  it('never plays the same line twice', async () => {
    // The brain serves each line once and 404s afterwards; a console that
    // asked again would be trying to replay the last sentence into the room.
    await playUtterance('abc123')
    await playUtterance('abc123')

    expect(FakeAudio.made).toHaveLength(1)
  })

  it('survives a browser with no Audio at all', async () => {
    vi.stubGlobal('Audio', undefined)
    await expect(playUtterance('abc123')).resolves.toBeUndefined()
  })
})
