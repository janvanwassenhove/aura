import { describe, it, expect } from 'vitest'
import { memoryGraph, memoryLabel, memoryText, splitMemory } from '../../src/lib/memoryGraph'

/** U272: "is graph only taking skills into account or also showing memory?"
 *  followed by "currently memory is single bullet in graph".
 *
 *  It was. Long-term memory is ONE ProfileFact with key "memory" whose value
 *  is the whole bullet list, and the graph draws one node per fact — so
 *  everything he had learned about a person arrived as a single dot labelled
 *  "memory: - Jan is actief en geniet van…", cut off at 40 characters.
 */

const NOTE = `
- Jan is actief en geniet van sporten, waaronder hardlopen en voetballen.
- Jan volgt de wedstrijden van de Red Panthers.
- Jan heeft interesse in taal en is nieuwsgierig naar betekenissen van woorden.
- Jan speelt af en toe spelletjes en heeft daar plezier in.
`

describe('U272 — memory becomes a web, not one bullet', () => {
  it('splits the note into the lines it is made of', () => {
    expect(splitMemory(NOTE)).toHaveLength(4)
    // Hand-edited notes are a plain textarea, so other bullet marks parse too.
    expect(splitMemory('* one\n• two\n- three')).toEqual(['one', 'two', 'three'])
    expect(splitMemory('')).toEqual([])
  })

  it('labels a line by what distinguishes it, not by the whole sentence', () => {
    const { lines } = memoryGraph(NOTE, ['Jan'])
    expect(lines).toHaveLength(4)
    for (const l of lines) {
      // A sentence makes a terrible node label; keywords are the point.
      expect(memoryLabel(l).length).toBeLessThan(l.text.length)
      expect(l.keywords.length).toBeGreaterThan(0)
    }
  })

  it("never labels every node with the person's own name", () => {
    // The name appears in nearly every line he writes, so without ignoring it
    // it wins every ranking and every node reads identically.
    const { lines, shared } = memoryGraph(NOTE, ['Jan'])
    expect(shared).not.toContain('jan')
    for (const l of lines) expect(l.keywords).not.toContain('jan')
  })

  it('finds the words that tie separate memories together', () => {
    const shared = memoryGraph(
      '- hij houdt van voetballen met vrienden\n'
      + '- voetballen op zondag is zijn gewoonte\n'
      + '- hij leest graag over geschiedenis',
      [],
    ).shared
    // Two lines mention it, one does not — that is exactly a shared node.
    expect(shared).toContain('voetballen')
    expect(shared).not.toContain('geschiedenis')
  })

  it('counts a word once per line, so repetition is not a theme', () => {
    const { shared } = memoryGraph('- fiets fiets fiets fiets\n- iets anders', [])
    expect(shared).not.toContain('fiets')
  })

  it('is stable: the same note gives the same labels every render', () => {
    // This runs on every frame of a graph being dragged around.
    const a = memoryGraph(NOTE, ['Jan'])
    const b = memoryGraph(NOTE, ['Jan'])
    expect(b.lines.map(memoryLabel)).toEqual(a.lines.map(memoryLabel))
    expect(b.shared).toEqual(a.shared)
  })

  it('survives an empty or junk note without inventing nodes', () => {
    expect(memoryGraph('', []).lines).toEqual([])
    expect(memoryGraph('- \n-  \n', []).lines).toEqual([])
  })

  it('falls back to the text when a line has no usable keywords', () => {
    const { lines } = memoryGraph('- hij is er', [])
    expect(memoryLabel(lines[0])).toContain('hij is er')
  })
})

describe('U280 — a remembered relationship links two people', () => {
  it('picks up the [[links]] the distiller writes', () => {
    const { lines } = memoryGraph("- Jan's son [[jappe]] turns 13 in November", ['Jan'])
    expect(lines[0].refs).toEqual(['jappe'])
  })

  it('shows the sentence without its markup', () => {
    const { lines } = memoryGraph('- his son [[jappe]] plays football', [])
    // The canvas must read as prose; the brackets are wiring, not writing.
    expect(memoryText(lines[0])).toBe('his son jappe plays football')
    expect(memoryText(lines[0])).not.toContain('[[')
  })

  it('leaves a line with no links alone', () => {
    const { lines } = memoryGraph('- he likes running', [])
    expect(lines[0].refs).toEqual([])
  })

  it('keeps a linked name available as a keyword too', () => {
    // The link is an edge to a person; the name is still what the line is
    // about, so it may also earn its place on the label.
    const { lines } = memoryGraph('- [[jappe]] speelt voetbal en houdt van muziek', ['Jan'])
    expect(lines[0].refs).toContain('jappe')
    expect(lines[0].keywords.length).toBeGreaterThan(0)
  })
})
