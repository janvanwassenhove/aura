import { ref } from 'vue'
import { BRAIN_URL } from '../lib/endpoints'
import { setPlaybackVolume } from './useSpeechPlayback'

/** U399: his volume, in one place — the robot's speaker and this laptop alike.
 *
 *  Reported as "the volume slider has no effect" (translated). It set a gain
 *  on the robot's own speech only, while his words went through this laptop
 *  and his emotions through the robot's mixer at 100 %. And the Talk screen's
 *  slider began at 80 whatever the robot said — a guess dressed as a reading.
 *
 *  Module-level, so the Talk and Robot sliders are one slider.
 */
const level = ref(80)

async function load(): Promise<void> {
  try {
    const r = await fetch(`${BRAIN_URL}/robot/volume`)
    if (r.ok) {
      const v = (await r.json()).volume
      if (typeof v === 'number') level.value = Math.round(v * 100)
    }
  } catch { /* robot away: keep what the slider shows */ }
  setPlaybackVolume(level.value / 100)
}

async function save(): Promise<void> {
  // This laptop first: it is here even when the robot is not.
  setPlaybackVolume(level.value / 100)
  try {
    await fetch(`${BRAIN_URL}/robot/volume`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ volume: level.value / 100 }),
    })
  } catch { /* robot away */ }
}

export function useVolume() {
  return { level, load, save }
}
