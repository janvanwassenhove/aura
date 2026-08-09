"""U225 (audit S10): keep the owner passphrase in the OS keyring, not in .env.

The knowledge store is encrypted at rest so that a copy of the data file — a
stolen laptop, a synced backup folder, a stray zip — is worthless without the
owner's passphrase. That promise was hollow: the passphrase sat in
``%APPDATA%/aura-desktop/.env``, a sibling directory of the ciphertext with the
same ACL. Anything that could read one could read the other, so the encryption
protected the data against nothing it was actually likely to face.

The passphrase now lives in the OS credential store (Windows Credential Manager
via DPAPI, Keychain on macOS, Secret Service on Linux), where it is bound to the
logged-in user account and cannot be read by simply copying files.

``KNOWLEDGE_PASSPHRASE`` still wins when it is set: docker-compose, CI and
headless installs have no keyring, and breaking them to fix a desktop problem
would be a poor trade.
"""

from __future__ import annotations

import logging

SERVICE = "AURA"
ACCOUNT = "knowledge-passphrase"

_log = logging.getLogger(__name__)


def _keyring():
    """The keyring module, or None when it (or a usable backend) is absent."""
    try:
        import keyring
        from keyring.backends.fail import Keyring as FailKeyring

        if isinstance(keyring.get_keyring(), FailKeyring):
            return None
        return keyring
    except Exception:  # noqa: BLE001 — an unusable keyring must never break boot
        return None


def available() -> bool:
    return _keyring() is not None


def get_passphrase(env_value: str | None) -> tuple[str | None, str]:
    """Return ``(passphrase, source)`` where source is ``env``/``keyring``/``none``."""
    if env_value:
        return env_value, "env"
    kr = _keyring()
    if kr is None:
        return None, "none"
    try:
        value = kr.get_password(SERVICE, ACCOUNT)
    except Exception as exc:  # noqa: BLE001
        _log.warning("keyring read failed (%s); knowledge stays locked",
                     type(exc).__name__)
        return None, "none"
    return (value, "keyring") if value else (None, "none")


def put_passphrase(passphrase: str) -> bool:
    """Store the passphrase and READ IT BACK. Returns False if either fails.

    The read-back is the point: the caller is about to delete the only other
    copy, and a keyring that silently accepts writes it cannot serve would turn
    that into an unopenable store.
    """
    kr = _keyring()
    if kr is None:
        return False
    try:
        kr.set_password(SERVICE, ACCOUNT, passphrase)
        return kr.get_password(SERVICE, ACCOUNT) == passphrase
    except Exception as exc:  # noqa: BLE001
        _log.warning("keyring write failed: %s", type(exc).__name__)
        return False


def clear_passphrase() -> bool:
    kr = _keyring()
    if kr is None:
        return False
    try:
        kr.delete_password(SERVICE, ACCOUNT)
        return True
    except Exception:  # noqa: BLE001 — absent is the desired end state anyway
        return False
