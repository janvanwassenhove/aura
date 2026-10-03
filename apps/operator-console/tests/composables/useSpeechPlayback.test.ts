import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import {
  applySpeechEvent, playUtterance, resetPlayback, stopPlayback,
} from '../../src/composables/useSpeechPlayback'

/** U364: his real voice, out of this laptop.
 *
 *  The brain synthesizes once. When the owner sends audio here instead of the
 *  robot, it holds that WAV under an id and says so on the bus; this plays it.
 *  Same voice, same speed, same mid-line persona switch — because it is the
 *  same bytes, not a second reading by the browser (which is all U209 could do).
 *
 *  U385: and the live engine's reply arrives as a burst of segments, so lines
 *  queue rather than cut each other off, are fetched the moment they are
 *  announced, and stop when he is told to stop.
 */

class FakeAudio {
  static made: FakeAudio[] = []
  src = ''
  played = 0
  paused = 0
  onended: (() => void) | null = null
  onerror: (() => void) | null = null
  constructor(src?: string) { this.src = src ?? ''; FakeAudio.made.push(this) }
  play() { this.played += 1; return Promise.resolve() }
  pause() { this.paused += 1 }
  end() { this.onended?.() }
}

/** fetch that answers each line only when the test says so, in any order. */
let fetched: string[] = []
let release: Record<string, () => void> = {}
function holdingFetch() {
  vi.stubGlobal('fetch', (url: string) => {
    const id = String(url).replace(/^.*\/speech\//, '').replace(/\.wav$/, '')
    fetched.push(id)
    return new Promise((resolve) => {
      release[id] = () => resolve({ ok: true, blob: async () => new Blob([id]) } as Response)
    })
  })
}
function answeringFetch() {
  vi.stubGlobal('fetch', async (url: string) => {
    const id = String(url).replace(/^.*\/speech\//, '').replace(/\.wav$/, '')
    fetched.push(id)
    return { ok: true, blob: async () => new Blob([id]) } as Response
  })
}

const flush = () => new Promise((r) => setTimeout(r, 0))
const playedIds = () => FakeAudio.made.map((a) => a.src.replace('blob:', ''))

beforeEach(() => {
  setActivePinia(createPinia())
  FakeAudio.made = []
  fetched = []
  release = {}
  resetPlayback()
  vi.stubGlobal('Audio', FakeAudio as unknown as typeof Audio)
  // A blob URL that says which line it holds, so order is visible.
  let n = 0
  vi.stubGlobal('URL', {
    createObjectURL: (b: Blob & { _id?: string }) => `blob:${(b as unknown as { id: string }).id ?? n++}`,
    revokeObjectURL: () => {},
  })
  // Blob in jsdom does not expose its parts; carry the id alongside.
  vi.stubGlobal('Blob', class { id: string; constructor(parts: string[]) { this.id = parts[0] } })
  answeringFetch()
})
afterEach(() => vi.unstubAllGlobals())

describe('useSpeechPlayback', () => {
  it('fetches the line the brain is holding and plays it', async () => {
    await playUtterance('abc123')
    await flush()

    expect(fetched).toEqual(['abc123'])
    expect(playedIds()).toEqual(['abc123'])
    expect(FakeAudio.made[0].played).toBe(1)
  })

  it('lets a line finish before the next one starts (U385)', async () => {
    // The first version stopped the current line when the next arrived. For
    // the live engine, whose reply is a burst of segments, that meant hearing
    // only the last fragment.
    await playUtterance('one')
    await playUtterance('two')
    await flush()

    expect(playedIds()).toEqual(['one'])
    expect(FakeAudio.made[0].paused).toBe(0)        // not cut off

    FakeAudio.made[0].end()
    await flush()
    expect(playedIds()).toEqual(['one', 'two'])
  })

  it('plays a burst in the order it was announced, whatever order it arrives in', async () => {
    holdingFetch()
    void playUtterance('s1'); void playUtterance('s2'); void playUtterance('s3')
    release.s3(); release.s2(); await flush()
    expect(playedIds()).toEqual([])                  // s1 is still on its way

    release.s1(); await flush()
    expect(playedIds()).toEqual(['s1'])
    FakeAudio.made[0].end(); await flush()
    FakeAudio.made[1].end(); await flush()
    expect(playedIds()).toEqual(['s1', 's2', 's3'])
  })

  it('fetches every line the moment it is announced, not when its turn comes', async () => {
    // The brain holds only a few unfetched lines. A segment waiting behind a
    // long sentence would age out there before anyone asked for it.
    void playUtterance('long')
    void playUtterance('next')
    void playUtterance('after')
    await flush()

    expect(fetched).toEqual(['long', 'next', 'after'])
    expect(playedIds()).toEqual(['long'])
  })

  it('stops the line that is playing and drops the rest (U385)', async () => {
    await playUtterance('one'); await playUtterance('two'); await playUtterance('three')
    await flush()

    stopPlayback()
    await flush()

    expect(FakeAudio.made[0].paused).toBe(1)
    expect(playedIds()).toEqual(['one'])             // two and three never start
  })

  it('a stop that lands while a line is still on its way still wins', async () => {
    holdingFetch()
    void playUtterance('late')
    stopPlayback()
    release.late(); await flush()

    expect(playedIds()).toEqual([])
  })

  it('speaks again after a stop', async () => {
    await playUtterance('before'); await flush()
    stopPlayback(); await flush()

    await playUtterance('after'); await flush()
    expect(playedIds()).toEqual(['before', 'after'])
  })

  it('obeys the event stream: a line to play, and the order to stop', async () => {
    applySpeechEvent({ event_type: 'SpeechAudioReady', utterance_id: 'x1' })
    applySpeechEvent({ event_type: 'SpeechAudioReady', utterance_id: 'x2' })
    await flush(); await flush()
    expect(playedIds()).toEqual(['x1'])

    applySpeechEvent({ event_type: 'SpeechAudioStopped' })
    await flush()
    expect(FakeAudio.made[0].paused).toBe(1)
    expect(playedIds()).toEqual(['x1'])
  })

  it('ignores an utterance with no id rather than fetching nonsense', async () => {
    await playUtterance('')
    expect(fetched).toEqual([])
    expect(FakeAudio.made).toHaveLength(0)
  })

  it('never plays the same line twice', async () => {
    // The brain serves each line once and 404s afterwards; a console that
    // asked again would be trying to replay the last sentence into the room.
    await playUtterance('abc123')
    await playUtterance('abc123')
    await flush()

    expect(fetched).toEqual(['abc123'])
  })

  it('skips a line the brain no longer has, and carries on', async () => {
    vi.stubGlobal('fetch', async (url: string) => {
      const id = String(url).replace(/^.*\/speech\//, '').replace(/\.wav$/, '')
      return id === 'gone'
        ? ({ ok: false } as Response)
        : ({ ok: true, blob: async () => new Blob([id]) } as Response)
    })
    await playUtterance('gone'); await playUtterance('here'); await flush()
    expect(playedIds()).toEqual(['here'])
  })

  it('survives a browser with no Audio at all', async () => {
    vi.stubGlobal('Audio', undefined)
    await expect(playUtterance('abc123')).resolves.toBeUndefined()
  })
})
