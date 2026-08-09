"""Envelope encryption primitives for the knowledge layer (ADR-008 §4).

    OS keyring → Owner Master Key (OMK) ── wraps ──► per-person Data Encryption
    Keys (DEKs) ── each encrypts that person's bundle with AES-256-GCM.

No hand-rolled crypto: AES-256-GCM (AEAD, per-record nonce, AAD binding) and
scrypt KDF, both from the vetted `cryptography` library. The OMK is supplied by
the caller (from the OS keyring or a passphrase) — this module never persists it.
"""

from __future__ import annotations

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

_NONCE_BYTES = 12
_KEY_BYTES = 32  # AES-256

# U225 (audit S9): scrypt work factor. n=2**17/r=8/p=1 is the current OWASP
# recommendation (~128 MB, a few hundred ms); the original n=2**14 is three
# doublings below that. Callers must not hardcode these — the parameters that
# a given store was written with live in its key-params.json (see omk.py), so
# raising them here stays a one-line change instead of an unreadable store.
SCRYPT_N = 2**17
SCRYPT_R = 8
SCRYPT_P = 1
LEGACY_SCRYPT_N = 2**14  # pre-U225 installs; only ever used to migrate off


def generate_key() -> bytes:
    """A fresh random 256-bit key (used for per-person DEKs)."""
    return AESGCM.generate_key(bit_length=256)


def derive_omk(passphrase: str, salt: bytes, *, n: int = SCRYPT_N,
               r: int = SCRYPT_R, p: int = SCRYPT_P) -> bytes:
    """Derive the Owner Master Key from a passphrase via scrypt (memory-hard).

    ADR-008 allows Argon2id or scrypt; scrypt avoids an extra dependency. Use the
    OS keyring directly when possible; this is the headless/passphrase fallback.

    The work factor is a parameter (U225) because existing ciphertext can only be
    opened with the parameters it was written under — pass the ones recorded in
    key-params.json rather than trusting the defaults.
    """
    kdf = Scrypt(salt=salt, length=_KEY_BYTES, n=n, r=r, p=p)
    return kdf.derive(passphrase.encode())


def encrypt(key: bytes, plaintext: bytes, aad: bytes = b"") -> bytes:
    """AES-256-GCM encrypt. Returns nonce || ciphertext+tag. `aad` is bound
    (authenticated) so ciphertext can't be moved between contexts."""
    nonce = os.urandom(_NONCE_BYTES)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, aad)


def decrypt(key: bytes, blob: bytes, aad: bytes = b"") -> bytes:
    """Inverse of encrypt. Raises cryptography.exceptions.InvalidTag on a wrong
    key, tampered ciphertext, or mismatched AAD."""
    nonce, ct = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
    return AESGCM(key).decrypt(nonce, ct, aad)


def wrap_dek(dek: bytes, omk: bytes, aad: bytes = b"dek") -> bytes:
    """Wrap (encrypt) a per-person DEK under the OMK. Rotating the OMK re-wraps
    DEKs without re-encrypting any bundle."""
    return encrypt(omk, dek, aad)


def unwrap_dek(wrapped: bytes, omk: bytes, aad: bytes = b"dek") -> bytes:
    return decrypt(omk, wrapped, aad)
