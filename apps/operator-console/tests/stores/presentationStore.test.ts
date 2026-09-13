import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { usePresentationStore } from '../../src/stores/presentationStore'

/** U349: with two characters in one show, a subtitle that does not say who is
 *  talking is worse than no attribution at all — so the beat event carries the
 *  persona and the store keeps it beside the line. */

beforeEach(() => { setActivePinia(createPinia()) })

describe('presentationStore — who said the line', () => {
  it('keeps the persona that spoke alongside the subtitle', () => {
    const s = usePresentationStore()
    s.applyEvent({
      event_type: 'PresentationBeatFired', beat_id: 'butler', mode: 'speak',
      spoken: 'Goedendag.', persona: 'dry_tech_butler',
    })
    expect(s.subtitle).toBe('Goedendag.')
    expect(s.lastPersona).toBe('dry_tech_butler')
  })

  it('reads an unattributed beat as the presentation voice, not as the last one', () => {
    const s = usePresentationStore()
    s.applyEvent({
      event_type: 'PresentationBeatFired', beat_id: 'a', mode: 'speak',
      spoken: 'Eerst.', persona: 'kids_companion',
    })
    s.applyEvent({
      event_type: 'PresentationBeatFired', beat_id: 'b', mode: 'speak',
      spoken: 'Daarna.',
    })
    expect(s.lastPersona).toBe('')
  })

  it('ignores events that are not ours', () => {
    const s = usePresentationStore()
    s.applyEvent({ event_type: 'SomethingElse', persona: 'kids_companion' })
    expect(s.lastPersona).toBe('')
  })

  it('survives a beat event with no persona field at all', () => {
    // The brain may be older than this console — an absent field is not a crash.
    const s = usePresentationStore()
    s.applyEvent({ event_type: 'PresentationBeatFired', beat_id: 'a', spoken: 'Hoi.' })
    expect(s.lastPersona).toBe('')
    expect(s.subtitle).toBe('Hoi.')
  })
})

/** U352: the overlay is a separate window, so a beat that moves it crosses an
 *  explicit channel. The store is where both channels land on one field. */
describe('presentationStore — where the overlay belongs', () => {
  it('takes the overlay off when a beat says so', () => {
    const s = usePresentationStore()
    s.applyEvent({
      event_type: 'PresentationOverlayChanged', visible: false, beat_id: 'demo',
    })
    expect(s.status.overlay_visible).toBe(false)
  })

  it('brings it back on the next change', () => {
    const s = usePresentationStore()
    s.applyEvent({ event_type: 'PresentationOverlayChanged', visible: false })
    s.applyEvent({ event_type: 'PresentationOverlayChanged', visible: true })
    expect(s.status.overlay_visible).toBe(true)
  })

  it('leaves the subtitle alone — it is a different kind of event', () => {
    const s = usePresentationStore()
    s.applyEvent({
      event_type: 'PresentationBeatFired', beat_id: 'a', mode: 'speak', spoken: 'Hallo.',
    })
    s.applyEvent({ event_type: 'PresentationOverlayChanged', visible: false })
    expect(s.subtitle).toBe('Hallo.')
    expect(s.lastBeat).toBe('a')
  })
})
