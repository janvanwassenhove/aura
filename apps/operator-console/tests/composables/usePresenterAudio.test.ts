import { describe, it, expect, beforeEach } from 'vitest'
import { createMic, laptopMicSupported, laptopAudioSupported } from '../../src/composables/usePresenterAudio'

// U209: the laptop-mic keyword path. A fake SpeechRecognition proves the muting
// contract (what the laptop speaks must never be heard as a keyword) without a
// real microphone.

class FakeRecognition {
  lang = ''; continuous = false; interimResults = false
  onresult: ((e: any) => void) | null = null
  onend: (() => void) | null = null
  onerror: (() => void) | null = null
  started = 0; stopped = 0
  start() { this.started++ }
  stop() { this.stopped++ }
  emit(text: string) {
    this.onresult?.({ resultIndex: 0, results: [{ 0: { transcript: text }, isFinal: true }] })
  }
}

let fake: FakeRecognition
beforeEach(() => {
  fake = new FakeRecognition()
  ;(window as any).SpeechRecognition = function () { return fake }
  ;(window as any).webkitSpeechRecognition = undefined
  ;(window as any).speechSynthesis = { speak() {}, cancel() {} }
})

describe('usePresenterAudio', () => {
  it('reports support from the browser APIs', () => {
    expect(laptopMicSupported()).toBe(true)
    expect(laptopAudioSupported()).toBe(true)
  })

  it('final transcripts reach onText', () => {
    const heard: string[] = []
    const mic = createMic(t => heard.push(t))!
    mic.start()
    fake.emit('our agents run in parallel')
    expect(heard).toEqual(['our agents run in parallel'])
  })

  it('drops results while muted — so it never hears the laptop speaking', () => {
    const heard: string[] = []
    const mic = createMic(t => heard.push(t))!
    mic.start()
    mic.setMuted(true)
    fake.emit('the robot is talking now')
    expect(heard).toEqual([])
    mic.setMuted(false)
    fake.emit('back to the presenter')
    expect(heard).toEqual(['back to the presenter'])
  })

  it('restarts recognition when the browser ends it mid-talk', () => {
    const mic = createMic(() => {})!
    mic.start()
    expect(fake.started).toBe(1)
    fake.onend?.()
    expect(fake.started).toBe(2)
    mic.stop()
    fake.onend?.()
    expect(fake.started).toBe(2)
  })
})
