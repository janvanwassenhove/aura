import { describe, it, expect } from 'vitest'
import { splitCues, timeCues } from '../../src/lib/subtitleCues'

/** U400: "subtitles are not following fluently with talking, should be in
 *  sync". A whole line in one block, held for a guess, is not a subtitle — it
 *  is a caption. These cut a line where a reader would, and give each piece
 *  its share of the time he actually takes to say it. */

describe('U400 — cutting a line into subtitles', () => {
  it('keeps a short line whole', () => {
    expect(splitCues('Goedemorgen. Ik ben de junior dev.')).toEqual(
      ['Goedemorgen. Ik ben de junior dev.'])
  })

  it('gives every long sentence its own subtitle', () => {
    const a = 'Today I want to show you a robot that helps a developer through the day.'
    const b = 'It listens, it looks things up, and it never pretends to know what it does not.'
    expect(splitCues(`${a} ${b}`)).toEqual([a, b])
  })

  it('cuts a sentence too long to read at a comma', () => {
    const line = 'When the demo starts he stands perfectly still, because the room should watch the screen and not a robot following you around the stage.'
    const cues = splitCues(line)
    expect(cues.length).toBeGreaterThan(1)
    expect(cues.join(' ')).toBe(line)
    expect(cues.every(c => c.length <= 84)).toBe(true)
  })

  it('cuts a run-on with no punctuation between words, never inside one', () => {
    const line = 'een heel lange zin zonder enige leesteken die maar doorgaat en doorgaat tot niemand meer weet waar hij begon of waar hij eindigt'
    const cues = splitCues(line)
    expect(cues.length).toBeGreaterThan(1)
    expect(cues.every(c => c.length <= 84)).toBe(true)
    expect(cues.join(' ')).toBe(line)
  })

  it('gives each piece its share of how long he speaks', () => {
    const timed = timeCues(['x'.repeat(40), 'y'.repeat(20)], 1000, 6000)
    expect(timed[0]).toMatchObject({ from: 1000 })
    expect(timed[1].to).toBe(7000)
    expect(timed[0].to).toBe(timed[1].from)
    expect(timed[0].to - timed[0].from).toBeGreaterThan(timed[1].to - timed[1].from)
  })
})
