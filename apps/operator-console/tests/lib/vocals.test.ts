import { describe, it, expect } from 'vitest'
import { personaIdsIn } from '../../src/lib/vocals'

/** U349: the console cannot resolve a persona id — characters live in the
 *  brain — but it CAN tell the presenter, at a desk, that a line names one
 *  that does not exist. The brain's own fallback happens on stage, which is
 *  the wrong place to find out. */

describe('personaIdsIn', () => {
  it('finds nothing in a line that never switches', () => {
    expect(personaIdsIn('Hallo allemaal.')).toEqual([])
  })

  it('finds each persona a line hands over to', () => {
    expect(personaIdsIn('a [persona:kids_companion] b [persona:dry_tech_butler] c'))
      .toEqual(['kids_companion', 'dry_tech_butler'])
  })

  it('reports a persona once however often it speaks', () => {
    expect(personaIdsIn('[persona:x]a[persona]b[persona:x]c')).toEqual(['x'])
  })

  it('ignores the closing marker, which names nobody', () => {
    expect(personaIdsIn('a[persona]b')).toEqual([])
    expect(personaIdsIn('a[/persona]b')).toEqual([])
  })

  it('tolerates spacing and case, like the brain does', () => {
    expect(personaIdsIn('a[ PERSONA : Kids_Companion ]b')).toEqual(['Kids_Companion'])
  })

  it('leaves prose that merely mentions a persona alone', () => {
    expect(personaIdsIn('we praten over [de persona van de robot]')).toEqual([])
  })

  it('never returns a half-written marker as if it were an id', () => {
    expect(personaIdsIn('a[persona:]b')).toEqual([])
  })
})
