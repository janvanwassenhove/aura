import { describe, it, expect } from 'vitest'
import { filterGraph, type GraphInput } from '../../src/lib/graphFilter'

// U214: filtering the brain graph by person.

const INPUT: GraphInput = {
  people: [
    { person_id: 'jan', display_name: 'Jan' },
    { person_id: 'tycho', display_name: 'Tycho' },
    { person_id: 'mila', display_name: 'Mila' },
  ],
  skills: [
    { name: 'jan-morning', description: '', person: 'jan', body: '' },
    { name: 'tycho-homework', description: '', person: 'tycho', body: '' },
    { name: 'desktop-spotify', description: '', person: '', body: '' },   // general
  ],
  facts: [
    { person_id: 'jan', key: 'hobby', value: 'hockey' },
    { person_id: 'tycho', key: 'school', value: 'x' },
    { person_id: 'mila', key: 'lang', value: 'java' },
  ],
}

describe('filterGraph', () => {
  it('returns everything untouched when nothing is selected', () => {
    expect(filterGraph(INPUT, [])).toBe(INPUT)
  })

  it('keeps only the selected person, their skills and their facts', () => {
    const out = filterGraph(INPUT, ['jan'])
    expect(out.people.map(p => p.person_id)).toEqual(['jan'])
    expect(out.facts.map(f => f.person_id)).toEqual(['jan'])
    expect(out.skills.map(s => s.name)).toContain('jan-morning')
    expect(out.skills.map(s => s.name)).not.toContain('tycho-homework')
  })

  it('keeps GENERAL skills — they apply to everyone', () => {
    // Dropping these would make the shared library vanish the moment you focus
    // on someone, which reads as data loss rather than a filter.
    const out = filterGraph(INPUT, ['jan'])
    expect(out.skills.map(s => s.name)).toContain('desktop-spotify')
  })

  it('supports comparing several people at once', () => {
    const out = filterGraph(INPUT, ['jan', 'mila'])
    expect(out.people.map(p => p.person_id).sort()).toEqual(['jan', 'mila'])
    expect(out.facts.map(f => f.person_id).sort()).toEqual(['jan', 'mila'])
  })

  it('matches person ids case-insensitively', () => {
    const out = filterGraph(INPUT, ['JAN'])
    expect(out.people.map(p => p.person_id)).toEqual(['jan'])
  })

  it('an unknown id yields an empty constellation, not everything', () => {
    const out = filterGraph(INPUT, ['nobody'])
    expect(out.people).toEqual([])
    expect(out.facts).toEqual([])
    expect(out.skills.map(s => s.name)).toEqual(['desktop-spotify'])  // general only
  })
})
