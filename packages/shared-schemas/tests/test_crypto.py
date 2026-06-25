"""U19b: envelope-crypto primitives (ADR-008 §4)."""

from __future__ import annotations

import pytest
from cryptography.exceptions import InvalidTag

from shared_schemas.knowledge import crypto


def test_encrypt_decrypt_roundtrip() -> None:
    key = crypto.generate_key()
    blob = crypto.encrypt(key, b"secret profile", aad=b"jan")
    assert blob != b"secret profile"  # ciphertext, not plaintext
    assert crypto.decrypt(key, blob, aad=b"jan") == b"secret profile"


def test_wrong_key_fails() -> None:
    blob = crypto.encrypt(crypto.generate_key(), b"x")
    with pytest.raises(InvalidTag):
        crypto.decrypt(crypto.generate_key(), blob)


def test_aad_binding_prevents_context_swap() -> None:
    key = crypto.generate_key()
    blob = crypto.encrypt(key, b"x", aad=b"person-a")
    with pytest.raises(InvalidTag):
        crypto.decrypt(key, blob, aad=b"person-b")  # can't reuse another person's ct


def test_dek_wrap_unwrap() -> None:
    omk = crypto.generate_key()
    dek = crypto.generate_key()
    wrapped = crypto.wrap_dek(dek, omk)
    assert wrapped != dek
    assert crypto.unwrap_dek(wrapped, omk) == dek
    with pytest.raises(InvalidTag):
        crypto.unwrap_dek(wrapped, crypto.generate_key())  # wrong OMK


def test_omk_derivation_is_deterministic_per_salt() -> None:
    salt = b"s" * 16
    a = crypto.derive_omk("hunter2", salt)
    b = crypto.derive_omk("hunter2", salt)
    c = crypto.derive_omk("hunter2", b"t" * 16)
    assert a == b and a != c and len(a) == 32
