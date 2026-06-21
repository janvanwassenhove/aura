<template>
  <section class="panel flex flex-col h-full">
    <div class="flex items-center justify-between mb-2">
      <h2 class="panel-title mb-0">Event Log</h2>
      <button class="btn-ghost text-xs" @click="eventStore.clearEvents()">Clear</button>
    </div>

    <input
      v-model="eventStore.filter"
      type="text"
      placeholder="Filter by event type…"
      class="filter-input mb-2"
    />

    <ul class="event-list flex-1 overflow-y-auto space-y-1">
      <li
        v-for="event in eventStore.filteredEvents"
        :key="event.id"
        class="event-row"
      >
        <span class="event-type">{{ event.event_type }}</span>
        <span v-if="event.session_id" class="event-session">{{ event.session_id.slice(0, 8) }}</span>
        <span class="event-time">{{ fmtTime(event.timestamp) }}</span>
      </li>
      <li v-if="eventStore.filteredEvents.length === 0" class="text-gray-400 text-sm p-2">
        {{ eventStore.filter ? 'No events match filter.' : 'No events yet.' }}
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
import { useEventStore } from '../stores/eventStore'

const eventStore = useEventStore()

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
</script>
