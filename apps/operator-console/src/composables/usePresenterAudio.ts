// U209: laptop audio + laptop-mic keyword recognition for the presenter.
//
// Two browser capabilities, both optional and both about making the co-presenter
// dependable in a room:
//
//   Laptop speakers — read each of the robot's lines aloud through the laptop
//   (speechSynthesis), so a room hears them even when the robot's own speaker is
//   small. It's the laptop's voice, not the robot's exact audio, but it's audible
//   and needs no backend audio routing.
//
//   Laptop microphone — recognise the PRESENTER's speech on the laptop mic
//   (SpeechRecognition) and push it to keyword beats. This sidesteps the robot's
//   echo-cancellation problem: the laptop mic is near you, not the robot's
//   speaker, and we PAUSE recognition whenever the laptop is speaking so it can
//   never hear its own chime-ins as new speech.

// Resolved at CALL time, not module load — so support is checked against the
// live window (and a test can install a fake recogniser after import).
function speechRecognition(): any {
  if (typeof window === 'undefined') return null
  return (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition || null
}

export function laptopAudioSupported(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window
}

export function laptopMicSupported(): boolean {
  return speechRecognition() !== null
}

/** Speak a line through the laptop. Returns when it finishes (or right away on
 *  failure), so the caller can un-mute the mic only after we've stopped talking. */
export function speakOnLaptop(text: string, lang = 'nl-NL'): Promise<void> {
  return new Promise((resolve) => {
    if (!text || !laptopAudioSupported()) { resolve(); return }
    try {
      const u = new SpeechSynthesisUtterance(text)
      u.lang = lang
      u.onend = () => resolve()
      u.onerror = () => resolve()
      window.speechSynthesis.speak(u)
    } catch { resolve() }
  })
}

export function cancelLaptopSpeech(): void {
  try { window.speechSynthesis?.cancel() } catch { /* ignore */ }
}

export interface MicController {
  start: () => void
  stop: () => void
  /** Pause recognition (e.g. while the laptop/robot is speaking). */
  setMuted: (muted: boolean) => void
}

/**
 * Continuous laptop-mic recognition. Every final transcript is handed to
 * `onText`. Muting drops results (used while speaking) instead of tearing the
 * recogniser down, so it resumes instantly.
 */
export function createMic(onText: (text: string) => void, lang = 'nl-NL'): MicController | null {
  const SR = speechRecognition()
  if (!SR) return null
  const rec = new SR()
  rec.lang = lang
  rec.continuous = true
  rec.interimResults = false
  let running = false
  let muted = false

  rec.onresult = (ev: any) => {
    if (muted) return
    for (let i = ev.resultIndex; i < ev.results.length; i++) {
      const res = ev.results[i]
      if (res.isFinal) {
        const text = String(res[0]?.transcript ?? '').trim()
        if (text) onText(text)
      }
    }
  }
  // Chrome stops recognition periodically; restart while we still want it.
  rec.onend = () => { if (running) { try { rec.start() } catch { /* already starting */ } } }
  rec.onerror = () => { /* no-network / no-speech — onend will restart */ }

  return {
    start() { if (!running) { running = true; try { rec.start() } catch { /* ignore */ } } },
    stop() { running = false; try { rec.stop() } catch { /* ignore */ } },
    setMuted(m: boolean) { muted = m },
  }
}
