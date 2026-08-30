import { describe, it, expect } from 'vitest'
import { CHARACTERS, DEFAULT_CHARACTER, type CharacterAct } from '../../src/lib/characters'

/** U268: an animation that silently does nothing looks exactly like a
 *  deliberate stillness, and nothing in a suite of unit tests notices.
 *
 *  Two characters — including Scout, the DEFAULT, the one on the overlay —
 *  animated `ry` on a `<circle>`. SVG circles have `r`; there is no `ry` to
 *  animate, so the browser accepted the element, ignored the attribute, and
 *  the eyes never blinked once. Reported as "the overlay robot should be
 *  animated like eyes rolling/moving".
 *
 *  On a projector next to a live slideshow, a face holding perfectly still
 *  does not read as calm — it reads as a window that has hung.
 */

const ACTS: CharacterAct[] = ['idle', 'speak', 'move']
const IDS = Object.keys(CHARACTERS)

/** Every `<animate attributeName="X">` paired with the element it animates.
 *
 *  A stack, not a lookahead: `<animate>` is written INSIDE its target
 *  (`<circle ...><animate .../></circle>`), so the target is whatever element
 *  is currently open. Getting this wrong is how a test like this quietly
 *  checks nothing at all — which is the same disease it is here to catch.
 */
function animatedAttrs(svg: string): { tag: string; attr: string }[] {
  const out: { tag: string; attr: string }[] = []
  const open: string[] = []
  for (const m of svg.matchAll(/<(\/?)(\w+)([^>]*?)(\/?)>/g)) {
    const [, closing, tag, attrs, selfClosing] = m
    if (closing) { open.pop(); continue }
    if (tag === 'animate' || tag === 'animateTransform') {
      const a = /attributeName="([^"]+)"/.exec(attrs)
      const target = open[open.length - 1]
      if (a && target) out.push({ tag: target, attr: a[1] })
      continue
    }
    if (!selfClosing) open.push(tag)
  }
  return out
}

/** Attributes an element actually HAS, per SVG — animating anything else is
 *  a no-op the browser will not complain about. */
const GEOMETRY: Record<string, string[]> = {
  circle: ['cx', 'cy', 'r', 'opacity', 'fill', 'fill-opacity', 'stroke', 'transform'],
  ellipse: ['cx', 'cy', 'rx', 'ry', 'opacity', 'fill', 'stroke', 'transform'],
  rect: ['x', 'y', 'width', 'height', 'rx', 'ry', 'opacity', 'fill', 'stroke', 'transform'],
  path: ['d', 'opacity', 'fill', 'stroke', 'stroke-width', 'transform'],
}

describe('U268 — character art animates attributes that exist', () => {
  it.each(IDS)('%s animates nothing a browser would ignore', (id) => {
    for (const act of ACTS) {
      for (const { tag, attr } of animatedAttrs(CHARACTERS[id].art(120, act))) {
        const allowed = GEOMETRY[tag]
        if (!allowed) continue          // an element we have no rules for
        expect(allowed, `${id} (${act}): <${tag}> has no "${attr}" to animate`)
          .toContain(attr)
      }
    }
  })

  it.each(IDS)('%s is alive while idle, not frozen', (id) => {
    // Idle is the state the overlay spends nearly all of a talk in. If it
    // carries no animation at all, the projector shows a still image.
    const idle = CHARACTERS[id].art(120, 'idle')
    expect(idle, `${id} has no motion at all when idle`).toMatch(/<animate/)
  })

  it.each(IDS)('%s looks different when speaking than when idle', (id) => {
    const c = CHARACTERS[id]
    expect(c.art(120, 'speak')).not.toBe(c.art(120, 'idle'))
  })

  it('the default character blinks', () => {
    // The specific regression: Scout is what the overlay shows unless the
    // owner picks otherwise, and its blink animated an attribute a circle
    // does not have.
    const art = CHARACTERS[DEFAULT_CHARACTER].art(120, 'idle')
    expect(art).toMatch(/<circle[^>]*r="8\.4"[^>]*>\s*<animate attributeName="r"/)
  })
})
