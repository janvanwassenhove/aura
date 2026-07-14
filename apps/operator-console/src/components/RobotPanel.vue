<template>
  <section class="panel">
    <h2 class="panel-title">Robot State</h2>

    <div class="status-row">
      <span class="label">Mode</span>
      <span :class="['badge', robotStore.statusBadgeClass]">{{ robotStore.mode }}</span>
    </div>

    <div class="status-row">
      <span class="label">Behavior</span>
      <span class="value">{{ robotStore.behaviorState }}</span>
    </div>

    <div class="status-row">
      <span class="label">Speaking</span>
      <span :class="['indicator', robotStore.isSpeaking ? 'indicator-active' : 'indicator-idle']">
        <Volume2 v-if="robotStore.isSpeaking" :size="14" />
        <VolumeX v-else :size="14" />
        {{ robotStore.isSpeaking ? 'Speaking' : 'Silent' }}
      </span>
    </div>

    <div v-if="robotStore.isSpeaking && robotStore.currentTranscript" class="transcript-box">
      {{ robotStore.currentTranscript }}
    </div>

    <div v-if="robotStore.lastRecognized" class="status-row">
      <span class="label">Recognized</span>
      <span v-if="robotStore.lastRecognized.known" class="value">
        {{ robotStore.lastRecognized.display_name }}
        <span class="text-gray-400 text-xs">({{ Math.round(robotStore.lastRecognized.confidence * 100) }}%)</span>
      </span>
      <span v-else class="value text-gray-400">Unknown face</span>
    </div>

    <div class="mt-3">
      <h3 class="section-label">Motion Log</h3>
      <ul class="motion-log">
        <li v-for="entry in robotStore.motionLog" :key="entry.id" class="motion-entry">
          <span :class="['status-dot', `dot-${entry.status}`]" />
          <span class="motion-name">{{ entry.name }}</span>
          <span class="motion-time">{{ fmtTime(entry.timestamp) }}</span>
        </li>
        <li v-if="robotStore.motionLog.length === 0" class="text-gray-400 text-sm">No motions yet</li>
      </ul>
    </div>
  </section>
</template>

<script setup lang="ts">
import { Volume2, VolumeX } from 'lucide-vue-next'
import { useRobotStore } from '../stores/robotStore'

const robotStore = useRobotStore()

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString()
}
</script>
