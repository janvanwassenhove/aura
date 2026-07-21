import { describe, it, expect } from 'vitest'
import { vaultState } from '../../src/lib/vaultState'

describe('vaultState (U180)', () => {
  it('warns clearly when profiles are NOT encrypted', () => {
    // The state the owner hit after a reset: the badge used to read "BENIGN".
    const s = vaultState(false, false)
    expect(s.kind).toBe('warn')
    expect(s.label).toBe('Not encrypted')
    expect(s.title).toMatch(/unencrypted/i)
    expect(s.title).toMatch(/face recognition/i)   // explains the missing button
    expect(s.label.toLowerCase()).not.toContain('benign')
  })

  it('confirms encryption once a passphrase is set', () => {
    const s = vaultState(false, true)
    expect(s.kind).toBe('ok')
    expect(s.label).toBe('Encrypted')
  })

  it('locked wins over everything else', () => {
    const s = vaultState(true, true)
    expect(s.kind).toBe('locked')
    expect(s.label).toBe('Locked')
    expect(s.title).toMatch(/passphrase/i)
  })

  it('never leaks internal tier names to the owner', () => {
    for (const s of [vaultState(false, false), vaultState(false, true), vaultState(true, true)]) {
      expect(`${s.label} ${s.title}`.toLowerCase()).not.toMatch(/benign|sensitive|omk|tier/)
    }
  })
})
