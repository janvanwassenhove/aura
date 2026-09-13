import { describe, it, expect } from 'vitest'
import { buildPersonGraph, graphSignature } from '../../src/lib/personGraph'
import type { PersonDetail } from '../../src/stores/knowledgeStore'

/** U348: the graph went stale the moment he learned something.
 *
 *  Reported as: "when reading sources, should knowledge graph not be updated
 *  then?" — and then precisely: "het doet die wel bij openen, maar bij
 *  toevoegen wordt rechts geen update gaan (in kleine venster)".
 *
 *  Exactly right, and the cause was one line. The canvas cached its node set
 *  per person and the ONLY thing that threw that cache away was switching to
 *  somebody else. Read eight facts off a website and the store updated, the
 *  list updated, and the picture beside it kept drawing the graph from before
 *  — with no hint that it was out of date. Reopening the view rebuilt it,
 *  which is why it looked like it worked.
 *
 *  A drawing that used to be true is worse than no drawing, because it is
 *  believed. The same rule the repository applies to its own diagrams.
 *
 *  Rebuilding naively would have cost the arrangement: the layout settles, and
 *  a node the owner dragged somewhere is a decision they made. So a rebuild
 *  carries over the position of every node that already existed, and only new
 *  ones arrive at a fresh spot.
 */

function detail(facts: { id: string; key: string; value: string }[],
                skills: string[] = []): PersonDetail {
  return {
    person: { person_id: 'jan', display_name: 'Jan', role: 'owner' },
    facts: facts.map(f => ({ fact_id: f.id, person_id: 'jan', key: f.key, value: f.value })),
    signals: [],
    skills: skills.map(name => ({ name })),
  } as unknown as PersonDetail
}

const ONE = detail([{ id: '1', key: 'project', value: 'Builds a [[Reachy Mini]]' }])

describe('the graph follows what he knows', () => {
  it('changes its signature when a fact is added', () => {
    const more = detail([
      { id: '1', key: 'project', value: 'Builds a [[Reachy Mini]]' },
      { id: '2', key: 'writes', value: 'Blogs at [[mityjohn]]' },
    ])
    expect(graphSignature(more)).not.toBe(graphSignature(ONE))
  })

  it('changes its signature when a skill is learned', () => {
    expect(graphSignature(detail([], ['spotify']))).not.toBe(graphSignature(detail([])))
  })

  it('is the same signature for the same knowledge', () => {
    expect(graphSignature(ONE)).toBe(graphSignature(
      detail([{ id: '1', key: 'project', value: 'Builds a [[Reachy Mini]]' }])))
  })

  it('draws the new fact and its topic', () => {
    const before = buildPersonGraph(ONE, ['jan'])
    const after = buildPersonGraph(detail([
      { id: '1', key: 'project', value: 'Builds a [[Reachy Mini]]' },
      { id: '2', key: 'writes', value: 'Blogs at [[mityjohn]]' },
    ]), ['jan'], before)

    const labels = after.nodes.map(n => n.label)
    expect(labels.some(l => l.includes('Blogs at'))).toBe(true)
    expect(labels).toContain('mityjohn')
    expect(after.nodes.length).toBeGreaterThan(before.nodes.length)
  })

  it('keeps where the settled — or dragged — nodes already are', () => {
    const before = buildPersonGraph(ONE, ['jan'])
    const root = before.nodes.find(n => n.id === 'jan')!
    root.x = 123; root.y = -45; root.fixed = true      // the owner moved him

    const after = buildPersonGraph(detail([
      { id: '1', key: 'project', value: 'Builds a [[Reachy Mini]]' },
      { id: '2', key: 'writes', value: 'Blogs at [[mityjohn]]' },
    ]), ['jan'], before)

    const moved = after.nodes.find(n => n.id === 'jan')!
    expect([moved.x, moved.y, moved.fixed]).toEqual([123, -45, true])
  })

  it('a fact that is gone leaves the graph', () => {
    const before = buildPersonGraph(detail([
      { id: '1', key: 'project', value: 'Builds a [[Reachy Mini]]' },
      { id: '2', key: 'writes', value: 'Blogs at [[mityjohn]]' },
    ]), ['jan'])
    const after = buildPersonGraph(ONE, ['jan'], before)

    expect(after.nodes.map(n => n.label).some(l => l.includes('Blogs at'))).toBe(false)
  })

  it('another person is another graph, not a merge of two', () => {
    const ada = {
      person: { person_id: 'ada', display_name: 'Ada', role: 'family' },
      facts: [], signals: [], skills: [],
    } as unknown as PersonDetail
    const after = buildPersonGraph(ada, ['jan', 'ada'], buildPersonGraph(ONE, ['jan']))

    expect(after.pid).toBe('ada')
    expect(after.nodes.map(n => n.label)).not.toContain('Reachy Mini')
  })

  it('links never point past the end of the node list', () => {
    /** A stale index draws a line to nowhere, or throws in the render loop. */
    const g = buildPersonGraph(detail([
      { id: '1', key: 'a', value: 'one [[topic]]' },
      { id: '2', key: 'b', value: 'two [[topic]]' },
      { id: '3', key: 'c', value: 'three' },
    ], ['spotify']), ['jan'])

    for (const [a, b] of g.links) {
      expect(a).toBeGreaterThanOrEqual(0)
      expect(b).toBeLessThan(g.nodes.length)
    }
  })
})
