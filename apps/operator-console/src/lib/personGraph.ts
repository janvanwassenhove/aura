/**
 * The node/link set behind one person's knowledge graph — U348.
 *
 * This was built inside the canvas component, which meant two things: nothing
 * could test it, and the cache that made it fast ("same person? keep the nodes
 * you have") made it wrong. A fact read off a website never appeared until the
 * view was reopened, and the picture kept looking authoritative while it was
 * out of date. `graphSignature` is the answer to "is this drawing still the
 * truth", and it is cheap enough to ask on every frame.
 *
 * Layout is deterministic (a fixed seed), so the same knowledge always draws
 * the same picture. A rebuild carries over the position of every node that
 * already existed — the layout settles over a few seconds, and a node the
 * owner dragged somewhere is a decision, not a coordinate.
 */

import type { PersonDetail } from '../stores/knowledgeStore'
import { memoryGraph, memoryLabel, memoryText } from './memoryGraph'

export interface GNode {
  id: string
  label: string
  kind: 'person' | 'fact' | 'skill' | 'topic' | 'memory'
  r: number
  x: number
  y: number
  vx: number
  vy: number
  fixed?: boolean
  personId?: string
  /** U272: the full sentence behind a keyword label, shown on hover. */
  detail?: string
}

export interface Graph {
  pid: string
  /** What the nodes were built from — see `graphSignature`. */
  sig: string
  nodes: GNode[]
  links: [number, number, number][]
}

/** What he knows right now, as one short string. Different knowledge, different
 *  string — which is the whole question the canvas needs answered. */
export function graphSignature(detail: PersonDetail | null): string {
  if (!detail) return ''
  const facts = detail.facts.map(f => `${f.fact_id}:${f.value.length}`).join(',')
  const skills = (detail.skills ?? []).map(s => s.name).join(',')
  const signals = detail.signals.map(s => s.signal_id).join(',')
  return `${detail.person.person_id}|${facts}|${skills}|${signals}`
}

export function buildPersonGraph(
  detail: PersonDetail | null,
  peopleIds: string[],
  previous?: Graph | null,
): Graph | null {
  const d = detail
  if (!d) return null
  const pid = d.person.person_id

  // Positions to inherit — but only from the same person's graph. Another
  // person is another graph, and reusing coordinates across them would put
  // Ada's nodes wherever Jan's happened to settle.
  const held = new Map<string, GNode>()
  if (previous && previous.pid === pid) {
    for (const n of previous.nodes) held.set(n.id, n)
  }

  let seed = 99
  const rnd = () => ((seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648)
  const nodes: GNode[] = []
  const links: [number, number, number][] = []
  const add = (id: string, label: string, kind: GNode['kind'], r: number,
               personId?: string, nodeDetail?: string) => {
    const a = rnd() * 6.28, rad = 60 + rnd() * 130
    const was = held.get(id)
    nodes.push({
      id, label, kind, r, personId, detail: nodeDetail,
      x: was ? was.x : Math.cos(a) * rad,
      y: was ? was.y : Math.sin(a) * rad,
      vx: was ? was.vx : 0,
      vy: was ? was.vy : 0,
      fixed: was?.fixed,
    })
    return nodes.length - 1
  }

  const root = add(pid, d.person.display_name, 'person', 22, pid)
  const topicIdx: Record<string, number> = {}
  for (const f of d.facts) {
    // U272: long-term memory is stored as ONE fact whose value is the entire
    // bullet list, so it arrived here as a single dot labelled
    // "memory: - Jan is actief en geniet van…", truncated at 40 characters —
    // everything he had learned about someone, as one bullet. It gets its own
    // treatment below instead.
    if (f.key === 'memory') continue
    const refs = [...f.value.matchAll(/\[\[([^\]]+)\]\]/g)].map(m => m[1])
    const clean = f.value.replace(/\[\[([^\]]+)\]\]/g, '$1')
    const i = add(`f${f.fact_id}`, `${f.key}: ${clean}`, 'fact', 9)
    links.push([root, i, 1])
    // [[topics]] are SHARED nodes — one node per target, whatever mentions it.
    for (const name of refs) {
      if (topicIdx[name] === undefined) {
        const isPerson = peopleIds.includes(name)
        topicIdx[name] = add(`t${name}`, name, isPerson ? 'person' : 'topic', isPerson ? 14 : 11, isPerson ? name : undefined)
      }
      links.push([i, topicIdx[name], 0.9])
    }
  }
  for (const sk of d.skills ?? []) {
    const i = add(`s${sk.name}`, sk.name, 'skill', 12)
    links.push([root, i, 1])
  }
  for (const sig of d.signals.slice(0, 8)) {
    const i = add(`g${sig.signal_id}`, `${sig.kind}: ${sig.value}`.slice(0, 40), 'topic', 8)
    links.push([root, i, 0.7])
  }

  // ── U272: what he REMEMBERS, one node per thing remembered ───────────────
  // Each line is labelled with the words that distinguish it rather than the
  // whole sentence (the sentence is on hover), and words that several lines
  // share become their own nodes — so you can see at a glance that three
  // separate things he remembers are all about the same subject. That is the
  // difference between a list and a graph.
  // U279: the NEWEST note. Saving used to append (U278), so a store can hold
  // several — the owner's had eight — and first-match would graph the oldest,
  // which is the very note they had already corrected.
  const notes = d.facts.filter(f => f.key === 'memory')
  const note = notes.length ? notes[notes.length - 1].value : ''
  const { lines, shared } = memoryGraph(note, [d.person.display_name, pid])
  const sharedIdx: Record<string, number> = {}
  for (const w of shared) sharedIdx[w] = add(`k${w}`, w, 'topic', 10)
  for (const line of lines) {
    const i = add(line.id, memoryLabel(line), 'memory', 8, undefined, memoryText(line))
    links.push([root, i, 0.85])
    for (const w of line.keywords) {
      if (sharedIdx[w] !== undefined) links.push([i, sharedIdx[w], 0.7])
    }
    // U280: a remembered line that NAMES someone he knows becomes an edge to
    // that person, reusing the same shared node the facts link to. Without
    // this the distiller's [[jappe]] was just characters inside a sentence,
    // and two people in one household stayed unconnected on the canvas.
    for (const name of line.refs) {
      if (topicIdx[name] === undefined) {
        const isPerson = peopleIds.includes(name)
        topicIdx[name] = add(`t${name}`, name, isPerson ? 'person' : 'topic',
                             isPerson ? 14 : 11, isPerson ? name : undefined)
      }
      links.push([i, topicIdx[name], 0.9])
    }
  }
  // Cross-links so it reads as a web, not a star.
  for (let i = 1; i < nodes.length; i++) {
    if (rnd() > 0.72 && nodes.length > 2) links.push([i, 1 + Math.floor(rnd() * (nodes.length - 1)), 0.4])
  }
  return { pid, sig: graphSignature(d), nodes, links }
}
