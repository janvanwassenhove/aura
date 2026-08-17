import { onMounted, onUnmounted, ref, watch } from 'vue'
import { BRAIN_URL } from '../lib/endpoints'
import { useRobotStore } from '../stores/robotStore'

/** U195: the live view, one frame at a time — shared by Talk and Robot.
 *
 * The MJPEG stream pushed frames at a fixed rate whether or not the link could
 * carry them, and TCP delays rather than drops — so the picture drifted further
 * behind the longer it ran (measured 0.6s → 2.5s and climbing). Asking for one
 * frame and only requesting the next once it has decoded means at most one
 * frame is ever in flight: no queue can form, and the rate settles at whatever
 * the link actually sustains. Measured flat at ~0.25s.
 */
export function useCameraFeed() {
  const frameSrc = ref('')
  const state = ref<'connecting' | 'live' | 'off'>('connecting')
  const robotStore = useRobotStore()

  const MIN_FRAME_MS = 66     // ~15 fps ceiling; the link decides the real rate
  const STALE_OFF_MS = 2500   // keep the last frame this long before 'off'
  let loopId = 0
  let currentUrl = ''

  async function startFrameLoop() {
    const myLoop = ++loopId   // any older loop sees the mismatch and stops
    let lastGoodAt = performance.now()
    while (myLoop === loopId) {
      const started = performance.now()
      try {
        // U212: cap a single request so a stalled frame can't hang the loop.
        const ctrl = new AbortController()
        const to = setTimeout(() => ctrl.abort(), 4000)
        const resp = await fetch(`${BRAIN_URL}/robot/camera/frame.jpg`,
                                 { cache: 'no-store', signal: ctrl.signal })
        clearTimeout(to)
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
        const blob = await resp.blob()
        if (myLoop !== loopId) break
        const next = URL.createObjectURL(blob)
        // Revoke the PREVIOUS url only after swapping, so the <img> is never
        // pointed at a blob that has already been freed.
        const prev = currentUrl
        currentUrl = next
        frameSrc.value = next
        if (prev) URL.revokeObjectURL(prev)
        state.value = 'live'
        lastGoodAt = performance.now()
        const left = MIN_FRAME_MS - (performance.now() - started)
        if (left > 0) await new Promise(r => setTimeout(r, left))
      } catch {
        if (myLoop !== loopId) break
        // U212: a single blip must NOT blank the feed.
        if (performance.now() - lastGoodAt > STALE_OFF_MS) state.value = 'off'
        await new Promise(r => setTimeout(r, state.value === 'off' ? 1500 : 400))
      }
    }
  }

  function stop() {
    loopId++
    if (currentUrl) { URL.revokeObjectURL(currentUrl); currentUrl = '' }
  }

  function bump() {
    state.value = 'connecting'
    startFrameLoop()
  }

  onMounted(startFrameLoop)
  onUnmounted(stop)
  // Brain restarted (WS reconnected) or robot came back → remount the stream.
  watch(() => robotStore.wsGeneration, (n, old) => {
    if (old !== undefined && old > 0 && n > old) bump()
  })
  watch(() => robotStore.connected, (now, was) => {
    if (now && was === false) bump()
  })

  return { frameSrc, state, bump }
}
