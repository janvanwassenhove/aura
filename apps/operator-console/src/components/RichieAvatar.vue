<template>
  <!-- U78: Richie Mini — vector portrait of the robot (white head, coil
       antennas, dark goggles), used as the assistant avatar. Drop a real
       richie.png in src/assets and swap it here if you prefer the artwork. -->
  <svg :width="size" :height="size" viewBox="0 0 64 64" fill="none"
       xmlns="http://www.w3.org/2000/svg" aria-hidden="true" class="richie">
    <!-- antennas -->
    <g stroke="var(--text, #333)" stroke-width="1.6" stroke-linecap="round">
      <path d="M18 26 L13 6" />
      <path d="M46 26 L52 8" />
      <!-- coil springs -->
      <path d="M15.2 19 q3 1 .8 2.6 q3 1 .8 2.6" stroke-width="1.2" />
      <path d="M49.4 15 q-3 1 -.8 2.6 q-3 1 -.8 2.6" stroke-width="1.2" />
    </g>
    <circle cx="13" cy="5" r="2" fill="var(--text, #333)" />
    <circle cx="52.4" cy="7" r="2" fill="var(--text, #333)" />

    <!-- head -->
    <rect x="8" y="22" width="48" height="30" rx="13"
          fill="var(--surface, #f5f2ec)" stroke="var(--text, #333)" stroke-width="2" />
    <!-- head sheen -->
    <path d="M16 27 q16 -4 30 0" stroke="#ffffff" stroke-opacity="0.75"
          stroke-width="3" stroke-linecap="round" fill="none" />

    <!-- goggles -->
    <rect x="27" y="34" width="10" height="3.4" rx="1.6" fill="#20242b" />
    <circle cx="22.5" cy="36" r="8.2" fill="#20242b" stroke="#111" stroke-width="1.4" />
    <circle cx="41.5" cy="36" r="8.2" fill="#20242b" stroke="#111" stroke-width="1.4" />
    <!-- lens glints -->
    <circle cx="25.6" cy="32.8" r="2.1" fill="#ffffff" fill-opacity="0.9" />
    <circle cx="44.6" cy="32.8" r="2.1" fill="#ffffff" fill-opacity="0.9" />
    <path d="M18.5 39 a5 5 0 0 0 6 2.4" stroke="#4a5560" stroke-width="1.2"
          stroke-linecap="round" fill="none" />

    <!-- shoulders -->
    <path d="M12 62 q2 -9 12 -9 h16 q10 0 12 9 z"
          fill="var(--surface, #f5f2ec)" stroke="var(--text, #333)" stroke-width="2" />
    <circle cx="24" cy="55" r="1.6" fill="var(--text, #333)" fill-opacity="0.55" />
    <circle cx="29" cy="54" r="1.6" fill="var(--text, #333)" fill-opacity="0.55" />
  </svg>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ size?: number }>(), { size: 22 })
</script>

<style scoped>
.richie { display: inline-block; vertical-align: middle; }
</style>
