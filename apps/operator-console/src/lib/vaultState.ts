/**
 * U180: the brain header badge, in owner language.
 *
 * It used to print the raw internal tier name ("BENIGN"), which says nothing
 * about the only two questions an owner actually has: is my personal data
 * encrypted on this device, and can I read it right now?
 *
 * Extracted from BrainPanel so every state is unit-testable — the badge is a
 * privacy signal, and a privacy signal that silently says the wrong thing is
 * worse than none.
 */

export type VaultKind = 'ok' | 'warn' | 'locked'

export interface VaultState {
  kind: VaultKind
  label: string
  title: string
}

export function vaultState(locked: boolean, omkLoaded: boolean): VaultState {
  if (locked) {
    return {
      kind: 'locked',
      label: 'Locked',
      title: 'Profiles are encrypted and currently locked — enter your passphrase to read them.',
    }
  }
  if (!omkLoaded) {
    return {
      kind: 'warn',
      label: 'Not encrypted',
      title: 'Profiles are stored unencrypted on this device, and face recognition stays off. '
        + 'Set a passphrase under "Secure profiles" to encrypt them.',
    }
  }
  return {
    kind: 'ok',
    label: 'Encrypted',
    title: 'Profiles are encrypted at rest with your passphrase and unlocked for this session.',
  }
}
