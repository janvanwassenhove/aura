import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import PhotoLightbox from '../../src/components/PhotoLightbox.vue'

/** U271: "photos are quite small, on click picture ad larger preview to more
 *  easily recognize."
 *
 *  The unknown-visitor thumbnails are 34×26 px, and the only thing that row
 *  asks of the owner is to decide WHO that is. A face is not identifiable at
 *  that size, so the one required action was the one thing the UI made hard.
 */

describe('U271 — a photo big enough to recognise a face in', () => {
  it('shows the image and its caption', () => {
    const w = mount(PhotoLightbox, {
      props: { src: 'data:image/jpeg;base64,AAAA', caption: 'Unknown visitor — seen 3×' },
    })
    expect(w.find('.lb-img').attributes('src')).toBe('data:image/jpeg;base64,AAAA')
    expect(w.text()).toContain('Unknown visitor — seen 3×')
  })

  it('closes on the button, on the backdrop and on Escape', async () => {
    const w = mount(PhotoLightbox, { props: { src: 'x', caption: 'c' }, attachTo: document.body })

    await w.find('.lb-close').trigger('click')
    expect(w.emitted('close')).toHaveLength(1)

    // Clicking the backdrop closes; clicking the photo itself must NOT —
    // dragging to look at a face would otherwise dismiss the thing you opened.
    await w.find('.lb').trigger('click')
    expect(w.emitted('close')).toHaveLength(2)
    await w.find('.lb-panel').trigger('click')
    expect(w.emitted('close')).toHaveLength(2)

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(w.emitted('close')).toHaveLength(3)
  })

  it('stops listening for Escape once it is gone', () => {
    const remove = vi.spyOn(window, 'removeEventListener')
    const w = mount(PhotoLightbox, { props: { src: 'x' } })
    w.unmount()
    expect(remove).toHaveBeenCalledWith('keydown', expect.any(Function))
  })

  it('carries the actions the photo was opened for', () => {
    // You enlarge an unknown visitor precisely to decide who it is; making
    // that decision should not mean closing this and hunting for the tiny row.
    const w = mount(PhotoLightbox, {
      props: { src: 'x', caption: 'c' },
      slots: { actions: '<button class="tag-here">Tag as…</button>' },
    })
    expect(w.find('.tag-here').exists()).toBe(true)
  })
})
