import { describe, it, expect, beforeEach } from 'vitest'
import { useDragHeight } from '../../src/composables/useDragHeight'

/** U390: the Talk screen's activity log can be made taller or shorter by
 *  dragging its top edge. Reported as "i should be able to drag/resize bottom
 *  window in talk screen", with the log squeezed to two lines. */

const KEY = 'test-strip'
const pe = (clientY: number) => ({ clientY, pointerId: 1, currentTarget: null, preventDefault() {} }) as unknown as PointerEvent
const key = (k: string) => ({ key: k, preventDefault() {} }) as unknown as KeyboardEvent

beforeEach(() => localStorage.clear())

describe('useDragHeight', () => {
  it('dragging the top edge up makes the panel taller', () => {
    const d = useDragHeight({ key: KEY, initial: 150, min: 60, max: () => 0 })
    d.onPointerDown(pe(500))
    d.onPointerMove(pe(400))
    expect(d.height.value).toBe(250)
    d.onPointerMove(pe(560))
    expect(d.height.value).toBe(90)
  })

  it('never leaves less than the tab bar and a couple of lines', () => {
    const d = useDragHeight({ key: KEY, initial: 150, min: 60, max: () => 0 })
    d.onPointerDown(pe(500)); d.onPointerMove(pe(900))
    expect(d.height.value).toBe(60)
  })

  it('never takes the room the conversation needs', () => {
    const d = useDragHeight({ key: KEY, initial: 150, min: 60, max: () => 300 })
    d.onPointerDown(pe(500)); d.onPointerMove(pe(0))
    expect(d.height.value).toBe(300)
  })

  it('remembers the height on this machine, once the drag ends', () => {
    const d = useDragHeight({ key: KEY, initial: 150, min: 60, max: () => 0 })
    d.onPointerDown(pe(500)); d.onPointerMove(pe(380))
    expect(localStorage.getItem(KEY)).toBeNull()          // not mid-drag
    d.onPointerUp(pe(380))
    expect(localStorage.getItem(KEY)).toBe('270')
    expect(useDragHeight({ key: KEY, initial: 150, min: 60, max: () => 0 }).height.value).toBe(270)
  })

  it('moving the pointer without pressing does nothing', () => {
    const d = useDragHeight({ key: KEY, initial: 150, min: 60, max: () => 0 })
    d.onPointerMove(pe(10))
    expect(d.height.value).toBe(150)
  })

  it('works from the keyboard as well', () => {
    const d = useDragHeight({ key: KEY, initial: 150, min: 60, max: () => 400 })
    d.onKeydown(key('ArrowUp'))
    expect(d.height.value).toBe(174)
    d.onKeydown(key('ArrowDown')); d.onKeydown(key('ArrowDown'))
    expect(d.height.value).toBe(126)
    d.onKeydown(key('End'))
    expect(d.height.value).toBe(400)
    d.onKeydown(key('Home'))
    expect(d.height.value).toBe(60)
  })

  it('a double-click puts it back where it started', () => {
    const d = useDragHeight({ key: KEY, initial: 150, min: 60, max: () => 0 })
    d.onPointerDown(pe(500)); d.onPointerMove(pe(300)); d.onPointerUp(pe(300))
    d.reset()
    expect(d.height.value).toBe(150)
    expect(localStorage.getItem(KEY)).toBe('150')
  })

  it('a remembered height that no longer fits is clamped, and given back later', () => {
    localStorage.setItem(KEY, '500')
    let room = 200
    const d = useDragHeight({ key: KEY, initial: 150, min: 60, max: () => room })
    expect(d.height.value).toBe(200)
    room = 800
    d.reclamp()
    expect(d.height.value).toBe(500)
  })
})
