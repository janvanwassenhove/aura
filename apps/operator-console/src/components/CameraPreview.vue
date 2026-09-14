<template>
  <div class="cam" :class="{ 'cam--off': camera.state.value === 'off' }">
    <img v-if="camera.frameSrc.value" :src="camera.frameSrc.value"
         :alt="alt" class="cam-img">
    <!-- U358: never a blank grey box. "Connecting" and "no picture" are
         different facts, and a face you are about to teach is exactly when
         you need to know which one you are looking at. -->
    <p v-else class="cam-note">
      {{ camera.state.value === 'off' ? 'No picture from the robot.' : 'Looking…' }}
    </p>
    <span v-if="camera.frameSrc.value" class="cam-tag">what he sees</span>
  </div>
</template>

<script setup lang="ts">
/** U358: the robot's live view, as a component you can mount and unmount.
 *
 *  `useCameraFeed` starts its frame loop on mount and stops it on unmount, so
 *  WHERE it is called decides how long the robot is polled. Calling it in a
 *  long-lived view means fetching frames over WiFi for as long as that page is
 *  open; wrapping it here means a `v-if` is the on/off switch, and the camera
 *  runs exactly while somebody is looking at it.
 */
import { useCameraFeed } from '../composables/useCameraFeed'

withDefaults(defineProps<{ alt?: string }>(), { alt: 'Robot camera' })

const camera = useCameraFeed()
defineExpose({ camera })
</script>

<style scoped>
.cam {
  position: relative; overflow: hidden; border-radius: 10px;
  background: var(--surface-2, rgba(127, 127, 127, 0.08));
  border: 1px solid var(--line); aspect-ratio: 4 / 3;
  display: flex; align-items: center; justify-content: center;
}
.cam--off { border-color: var(--danger, #e5484d); }
.cam-img { width: 100%; height: 100%; object-fit: cover; display: block; }
.cam-note { margin: 0; font-size: 12px; color: var(--ink-3); text-align: center; padding: 0 10px; }
.cam-tag {
  position: absolute; left: 6px; bottom: 6px; padding: 1px 6px; border-radius: 999px;
  background: rgba(0, 0, 0, 0.55); color: #fff; font-size: 10px; letter-spacing: 0.02em;
}
</style>
