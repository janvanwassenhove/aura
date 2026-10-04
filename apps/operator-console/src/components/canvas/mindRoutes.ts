/** The Mind panel's reading of the event stream: which region lights up, and
 *  the word that travels. Moved out of MindCanvas.vue (U406) so it can be
 *  tested without an animation loop. */

export type Tone = 'ok' | 'warn' | 'info'
export interface Spike { from: string; to: string; word: string; evt: string; tone: Tone; start: number }

export function routeEvent(raw: Record<string, unknown>, opts: { atStand?: boolean } = {}): Omit<Spike, 'start'> | null {
  const t = raw.event_type as string
  const s = (v: unknown, n = 22) => String(v ?? '').slice(0, n)
  switch (t) {
    case 'PersonRecognized': {
      // U406: at a stand nobody on screen has a name — a face he knows is a
      // visitor too, and the panel is in view of whoever is standing there.
      const who = opts.atStand ? 'someone' : s(raw.display_name || raw.person_id || 'unknown', 14)
      return { from: 'eyes', to: 'mem', tone: 'info', evt: t, word: `${who} · ${Number(raw.confidence ?? 0).toFixed(2)}` }
    }
    case 'GestureDetected':
      return { from: 'eyes', to: 'lang', tone: 'info', evt: t, word: s(raw.gesture) }
    case 'TranscriptUpdated':
      return raw.is_final ? { from: 'ears', to: 'lang', tone: 'ok', evt: t, word: `“${s(raw.transcript, 18)}…”` } : null
    case 'IntentRecognized':
      return { from: 'lang', to: 'rules', tone: 'ok', evt: t, word: s(raw.tool_name || raw.intent) }
    case 'ToolCallRequested':
      return { from: 'rules', to: 'tools', tone: 'ok', evt: t, word: s(raw.tool_name) }
    case 'ToolCallSucceeded':
      return { from: 'tools', to: 'lang', tone: 'ok', evt: t, word: s(raw.tool_name) }
    case 'ToolCallFailed':
      return { from: 'tools', to: 'lang', tone: 'warn', evt: t, word: s(raw.error_code || raw.tool_name) }
    case 'ApprovalRequested':
      return { from: 'rules', to: 'voice', tone: 'warn', evt: `${t} · mode asks`, word: 'may I?' }
    case 'ApprovalGranted':
      return { from: 'voice', to: 'rules', tone: 'ok', evt: t, word: 'approved' }
    case 'ApprovalDenied':
      return { from: 'voice', to: 'rules', tone: 'warn', evt: t, word: 'denied' }
    case 'ResponseDrafted':
      return { from: 'lang', to: 'voice', tone: 'ok', evt: t, word: `“${s(raw.response_text, 16)}…”` }
    case 'MotionStarted':
      return { from: 'lang', to: 'body', tone: 'info', evt: t, word: s(raw.motion_id) }
    case 'SpeechPlaybackStarted':
    case 'SpeechStarted':
      return { from: 'voice', to: 'body', tone: 'ok', evt: t, word: 'speaking' }
    case 'MemoryRecalled':
      return { from: 'mem', to: 'lang', tone: 'info', evt: t, word: 'recall' }
    case 'AgentRoundStarted':
      return { from: 'lang', to: 'rules', tone: 'ok', evt: t, word: `round ${s(raw.round_no, 3)}` }
    default:
      return null
  }
}
