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

U340 gives every other secret the same treatment, because only the passphrase
had moved. The OpenAI, OpenRouter and Gemini keys, the calendar sharing link
and the robot's pairing key stayed in plain text in exactly the file the
paragraph above calls a bad place for a secret — and on a managed laptop that
file lives under Roaming, which is synchronised. Same rules: the environment
wins, the credential store is next, the file is the fallback that must keep
docker and CI working, and wherever the file still holds something it is
locked to its owner instead of inheriting whatever the profile hands out.

The limit, stated plainly: none of this stops something running as the owner.
The credential store will hand a secret to any process of that user. What it
removes is the copy — a synced profile, a second account, a backup, a zip
attached to a bug report.
"""

from __future__ import annotations

import logging
import os

SERVICE = "AURA"
ACCOUNT = "knowledge-passphrase"

#: The env vars that are secrets rather than settings. Each is stored under its
#: own name in the credential store.
#:
#: ``GITHUB_TOKEN`` is deliberately NOT here: the Electron updater reads it from
#: the env file itself (updater.cjs), so moving it would break update checks
#: while looking like a security improvement.
MANAGED: tuple[str, ...] = (
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "GEMINI_API_KEY",
    "CALENDAR_ICS_URL",
    "ROBOT_SHARED_SECRET",
)

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


# ── U340: every other secret, under the same roof ──────────────────────────


def get(name: str) -> str | None:
    """The stored value for one secret, or None."""
    kr = _keyring()
    if kr is None:
        return None
    try:
        return kr.get_password(SERVICE, name)
    except Exception as exc:  # noqa: BLE001 — never break boot over a keyring
        _log.warning("keyring read failed for %s (%s)", name, type(exc).__name__)
        return None


def put(name: str, value: str) -> bool:
    """Store one secret and READ IT BACK. False if either half fails.

    The read-back is not ceremony: the caller is usually about to delete the
    only other copy, and a store that accepts writes it cannot serve would
    turn that into a lost account.
    """
    kr = _keyring()
    if kr is None:
        return False
    try:
        kr.set_password(SERVICE, name, value)
        return kr.get_password(SERVICE, name) == value
    except Exception as exc:  # noqa: BLE001
        _log.warning("keyring write failed for %s (%s)", name, type(exc).__name__)
        return False


def forget(name: str) -> bool:
    kr = _keyring()
    if kr is None:
        return False
    try:
        kr.delete_password(SERVICE, name)
        return True
    except Exception:  # noqa: BLE001 — absent is the desired end state anyway
        return False


def load_into_env() -> list[str]:
    """Put the stored secrets into the environment. Returns the names loaded.

    The environment wins: a value already set came from docker-compose, CI or
    the owner's own shell, and a stale credential-store entry must never
    shadow it.
    """
    loaded: list[str] = []
    for name in MANAGED:
        if os.environ.get(name, "").strip():
            continue
        value = get(name)
        if value:
            os.environ[name] = value
            loaded.append(name)
    if loaded:
        _log.info("loaded %d secret(s) from the credential store: %s",
                  len(loaded), ", ".join(loaded))
    return loaded


def harden(path) -> bool:
    """Lock an env file to its owner. True when the file now stands alone.

    On Windows the file inherits whatever the profile directory grants — on
    the machine this was reported from, that includes read access for a local
    sandbox group. Inheritance is dropped and the grants rewritten to the
    owner, SYSTEM and Administrators. Elsewhere: mode 0600.
    """
    from pathlib import Path

    file = Path(path)
    if not file.exists():
        return False
    try:
        if os.name != "nt":
            file.chmod(0o600)
            return True
        import getpass
        import subprocess

        who = os.environ.get("USERNAME") or getpass.getuser()
        result = subprocess.run(
            ["icacls", str(file), "/inheritance:r",
             "/grant:r", f"{who}:F", "/grant:r", "*S-1-5-18:F",
             "/grant:r", "*S-1-5-32-544:F"],
            capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            _log.warning("could not lock down %s: %s", file.name,
                         result.stderr.strip()[:200])
            return False
        return True
    except Exception as exc:  # noqa: BLE001 — a file we cannot lock is not fatal
        _log.warning("could not lock down %s (%s)", file.name, type(exc).__name__)
        return False


def migrate_env_file(path) -> list[str]:
    """Move plain-text secrets out of an env file into the credential store.

    Returns the names actually moved. A line is removed ONLY after the store
    has served the value back; anything else risks deleting the last copy of a
    key over a write that merely looked like it worked.
    """
    from pathlib import Path

    file = Path(path)
    if not file.exists() or _keyring() is None:
        return []
    try:
        lines = file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    moved: list[str] = []
    kept: list[str] = []
    for line in lines:
        name, _, value = line.partition("=")
        name, value = name.strip(), value.strip()
        if name in MANAGED and value and put(name, value):
            os.environ.setdefault(name, value)
            moved.append(name)
            continue          # the line goes away with the plain text
        kept.append(line)

    if moved:
        try:
            file.write_text("\n".join(kept) + "\n", encoding="utf-8")
        except OSError as exc:
            _log.warning("could not rewrite %s: %s", file.name, exc)
            return []
        _log.info("moved %d secret(s) out of %s into the credential store: %s",
                  len(moved), file.name, ", ".join(moved))
    harden(file)
    return moved
