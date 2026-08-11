/**
 * Where the backend is — decided once, here.
 *
 * U234. This used to be answered independently at twenty call sites, each with
 * its own fallback (`localhost:8000`, `:8003`, `:8020`…), which meant the
 * question "which port is the brain on?" had no single answer to change. It
 * also meant the port had to be known when the console was *built*, so the
 * desktop app could never move off a busy one.
 *
 * Three sources, in order:
 *
 *   1. `window.__AURA_RUNTIME__` — injected into index.html by whatever is
 *      serving the console. The desktop shell writes the port it actually got,
 *      which is how a dynamic port reaches a static build.
 *   2. `VITE_*` build-time env — how docker-compose and `npm run dev` say it.
 *   3. The documented defaults, for anyone opening the dist by hand.
 *
 * Prefer `127.0.0.1` over `localhost` in every default: on Windows the name
 * resolves to `::1` first, so "localhost" can reach a different process that
 * happens to hold the same port on the other address family. That is not
 * hypothetical — it shipped, and the window loaded somebody else's app (U229).
 */

export interface AuraRuntimeConfig {
  brainUrl?: string
  robotEventsWs?: string
}

declare global {
  interface Window {
    __AURA_RUNTIME__?: AuraRuntimeConfig
  }
}

const runtime: AuraRuntimeConfig =
  (typeof window !== 'undefined' && window.__AURA_RUNTIME__) || {}

const env = import.meta.env

/** The one process on the laptop: orchestrator, conversation, memory, identity, knowledge. */
export const BRAIN_URL: string =
  runtime.brainUrl ??
  env.VITE_BRAIN_URL ??
  env.VITE_ORCHESTRATOR_URL ??
  'http://127.0.0.1:8020'

/** The event stream the console subscribes to. Derived from the brain unless overridden. */
export const ROBOT_EVENTS_WS: string =
  runtime.robotEventsWs ??
  env.VITE_ROBOT_RUNTIME_WS ??
  `${BRAIN_URL.replace(/^http/, 'ws')}/ws/events`

/** For diagnostics — the About dialog and the logs both want to say where they looked. */
export const endpointSource = (): 'runtime' | 'build' | 'default' => {
  if (runtime.brainUrl) return 'runtime'
  if (env.VITE_BRAIN_URL || env.VITE_ORCHESTRATOR_URL) return 'build'
  return 'default'
}
