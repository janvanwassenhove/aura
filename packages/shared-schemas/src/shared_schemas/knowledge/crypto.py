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


def generate_key() -> bytes:
    """A fresh random 256-bit key (used for per-person DEKs)."""
    return AESGCM.generate_key(bit_length=256)


def derive_omk(passphrase: str, salt: bytes) -> bytes:
    """Derive the Owner Master Key from a passphrase via scrypt (memory-hard).

    ADR-008 allows Argon2id or scrypt; scrypt avoids an extra dependency. Use the
    OS keyring directly when possible; this is the headless/passphrase fallback.
    """
    kdf = Scrypt(salt=salt, length=_KEY_BYTES, n=2**14, r=8, p=1)
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
