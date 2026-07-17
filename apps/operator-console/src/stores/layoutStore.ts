import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

/** U76: VS Code-like workspace layout — toggleable, resizable side panels,
 *  persisted across sessions. */
export type RightTab = 'brain' | 'events'

const KEY = 'aura-layout-v2'
const OLD_KEY = 'aura-layout-v1'

function load(): Partial<{
  showLeft: boolean; showRight: boolean; rightTab: RightTab
  leftWidth: number; rightWidth: number
}> {
  try {
    const v2 = localStorage.getItem(KEY)
    if (v2) return JSON.parse(v2)
    // U113 migration: carry widths/visibility over from v1, but DROP the old
    // showBottom so everyone gets the new closed-by-default Event Log dock.
    const v1 = JSON.parse(localStorage.getItem(OLD_KEY) ?? '{}')
    delete v1.showBottom
    return v1
  } catch { return {} }
}

export const useLayoutStore = defineStore('layout', () => {
  const saved = load()
  const showLeft = ref(saved.showLeft ?? true)
  const showRight = ref(saved.showRight ?? true)
  const rightTab = ref<RightTab>(saved.rightTab ?? 'events')
  const leftWidth = ref(saved.leftWidth ?? 300)
  const rightWidth = ref(saved.rightWidth ?? 340)
  // U113: the Event Log is a debug surface — closed by default, one click away.
  const showBottom = ref((saved as any).showBottom ?? false)
  const bottomHeight = ref((saved as any).bottomHeight ?? 200)

  watch([showLeft, showRight, rightTab, leftWidth, rightWidth, showBottom, bottomHeight], () => {
    localStorage.setItem(KEY, JSON.stringify({
      showLeft: showLeft.value, showRight: showRight.value,
      rightTab: rightTab.value, leftWidth: leftWidth.value,
      rightWidth: rightWidth.value, showBottom: showBottom.value,
      bottomHeight: bottomHeight.value,
    }))
  })

  /** Open (and reveal) the right dock on a specific tab. */
  function openRight(tab: RightTab): void {
    rightTab.value = tab
    showRight.value = true
    if (tab === 'brain' && rightWidth.value < 420) rightWidth.value = 480
  }

  return { showLeft, showRight, rightTab, leftWidth, rightWidth,
           showBottom, bottomHeight, openRight }
})
