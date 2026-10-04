import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { usePresentationStore } from '../../src/stores/presentationStore'

/** U400: the projector's subtitle starts when his voice does and moves at his
 *  pace. On the robot that is the moment the line is announced; through the
 *  laptop it is the moment the playing window says it started — which may be
 *  the other window, so it arrives through the brain. */

const LINE = 'Today I want to show you a robot that helps a developer through the day. It listens, it looks things up, and it never pretends to know what it does not.'

describe('U400 — subtitles on his voice', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
    vi.setSystemTime(100_000)
  })
  afterEach(() => { vi.useRealTimers() })

  it('on the robot it starts at once and steps through the line', () => {
    const p = usePresentationStore()
    p.applyEvent({ event_type: 'PresentationSubtitle', text: LINE, duration_s: 8, persona: '' })
    expect(p.cueAt(Date.now())).toMatch(/^Today I want/)
    expect(p.cueAt(Date.now() + 6_000)).toMatch(/^It listens/)
    expect(p.subtitle).toBe(LINE)          // the presenter's "saying now"
  })

  it('it is gone a moment after he stops', () => {
    const p = usePresentationStore()
    p.applyEvent({ event_type: 'PresentationSubtitle', text: 'Kort.', duration_s: 1 })
    expect(p.cueAt(Date.now() + 1_000)).toBe('Kort.')
    expect(p.cueAt(Date.now() + 1_000 + 3_000)).toBe('')
  })

  it('through the laptop it waits until the line starts playing', () => {
    const p = usePresentationStore()
    p.applyEvent({ event_type: 'PresentationSubtitle', text: 'Via de laptop.', duration_s: 2,
                   utterance_id: 'u1' })
    expect(p.cueAt(Date.now())).toBe('')
    vi.advanceTimersByTime(700)                         // fetching the audio
    p.applyEvent({ event_type: 'SpeechLineStarted', utterance_id: 'u1', duration_s: 2.4 })
    expect(p.cueAt(Date.now())).toBe('Via de laptop.')
    expect(p.cueAt(Date.now() + 2_300)).toBe('Via de laptop.')   // the player's length
  })

  it("someone else's line starting does not start this one", () => {
    const p = usePresentationStore()
    p.applyEvent({ event_type: 'PresentationSubtitle', text: 'Deze.', duration_s: 2, utterance_id: 'u1' })
    p.applyEvent({ event_type: 'SpeechLineStarted', utterance_id: 'other', duration_s: 1 })
    expect(p.cueAt(Date.now())).toBe('')
  })

  it('if no window reports the start, it shows anyway — late beats never', () => {
    const p = usePresentationStore()
    p.applyEvent({ event_type: 'PresentationSubtitle', text: 'Toch.', duration_s: 2, utterance_id: 'u1' })
    vi.advanceTimersByTime(3_100)
    expect(p.cueAt(Date.now())).toBe('Toch.')
  })

  it('the beat finishing afterwards does not bring the line back', () => {
    const p = usePresentationStore()
    p.applyEvent({ event_type: 'PresentationSubtitle', text: 'Eén keer.', duration_s: 1 })
    vi.advanceTimersByTime(5_000)
    p.applyEvent({ event_type: 'PresentationBeatFired', beat_id: 'b', mode: 'speak', spoken: 'Eén keer.' })
    expect(p.cueAt(Date.now())).toBe('')
  })
})
