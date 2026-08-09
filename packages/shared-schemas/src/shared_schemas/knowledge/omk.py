"""U225 (audit S9): self-describing KDF parameters + in-place OMK rotation.

Until now the Owner Master Key was derived with scrypt n=2**14 from a salt that
defaulted to the hardcoded string "aura-knowledge" — so an install that never
ran the wizard shared its salt with every other such install, and the work
factor sat well under current OWASP guidance (n=2**17). Neither could be fixed
by editing the constants: the OMK wraps the per-person DEKs, so a different OMK
makes an existing store unreadable.

This module makes the parameters part of the stored state (``key-params.json``,
next to the ciphertext) and rotates the OMK in place. Only the wrapped DEKs and
the embedding blobs are rewritten — the knowledge bundles themselves are left
untouched, exactly as ``wrap_dek`` was designed to allow.

Crash safety, because this runs against real data:

* the params file records the OLD parameters under ``migrating_from`` BEFORE a
  single byte is rewritten, so both keys stay derivable;
* every store is probed individually, so a crash between two stores is
  recoverable — the next boot finishes the ones still on the old key;
* a store is only rewritten after the old key has been PROVEN to decrypt its
  current contents. If neither key opens it, the migration aborts and touches
  nothing.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from shared_schemas.knowledge import crypto

PARAMS_FILENAME = "key-params.json"

#: Minimum owner passphrase length. Raised from 8 — at 8 characters the scrypt
#: work factor is the only thing standing between an offline copy of the store
#: and the plaintext, and that is not a trade worth making.
MIN_PASSPHRASE_LEN = 12

#: What ``KNOWLEDGE_SALT`` unset used to produce. Refused for new installs.
LEGACY_DEFAULT_SALT = b"aura-knowledge00"

_SALT_BYTES = 16


class OmkError(RuntimeError):
    """Raised when the stored data cannot be opened with any known parameters."""


def legacy_salt(env_value: str | None) -> bytes:
    """Reproduce the pre-U225 salt derivation byte for byte, so existing data
    stays readable. Do not change: this is a compatibility shim, not a policy."""
    return (env_value or "aura-knowledge").encode().ljust(16, b"0")[:_SALT_BYTES]


@dataclass(frozen=True)
class KdfParams:
    salt: bytes
    n: int = crypto.SCRYPT_N
    r: int = crypto.SCRYPT_R
    p: int = crypto.SCRYPT_P

    def derive(self, passphrase: str) -> bytes:
        return crypto.derive_omk(passphrase, self.salt, n=self.n, r=self.r, p=self.p)

    def to_dict(self) -> dict:
        return {"salt_b64": base64.b64encode(self.salt).decode(),
                "n": self.n, "r": self.r, "p": self.p}

    @classmethod
    def from_dict(cls, d: dict) -> KdfParams:
        return cls(salt=base64.b64decode(d["salt_b64"]),
                   n=int(d["n"]), r=int(d["r"]), p=int(d["p"]))

    @classmethod
    def fresh(cls) -> KdfParams:
        # Read the constants at call time, not at class-definition time, so the
        # work factor stays one editable place (and tests can turn it down).
        return cls(salt=secrets.token_bytes(_SALT_BYTES),
                   n=crypto.SCRYPT_N, r=crypto.SCRYPT_R, p=crypto.SCRYPT_P)


# ----------------------------------------------------------------------------
# The params document on disk
# ----------------------------------------------------------------------------

def _write_doc(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def save_current(params_path: str | Path, params: KdfParams) -> None:
    """Record the parameters for a store being created from scratch.

    No ``migrating_from``: there is nothing older to fall back to, and claiming
    otherwise would send a future boot looking for data that never existed.
    """
    _write_doc(Path(params_path), {"version": 1, "current": params.to_dict()})


def load_or_init(params_path: Path, *, env_salt: str | None,
                 legacy_data_exists: bool) -> dict:
    """Return the params document, creating it on first run.

    On an install that predates this module the existing ciphertext is, by
    definition, under the legacy parameters — that is recorded as
    ``migrating_from`` so :func:`open_omk` can finish the rotation.
    """
    params_path = Path(params_path)
    if params_path.exists():
        return json.loads(params_path.read_text(encoding="utf-8"))

    doc: dict = {"version": 1, "current": KdfParams.fresh().to_dict()}
    if legacy_data_exists:
        doc["migrating_from"] = KdfParams(
            salt=legacy_salt(env_salt), n=crypto.LEGACY_SCRYPT_N,
        ).to_dict()
    _write_doc(params_path, doc)
    return doc


# ----------------------------------------------------------------------------
# Per-store probe + rewrap. Probes return None when there is nothing to judge.
# ----------------------------------------------------------------------------

def _probe_knowledge(path: Path, omk: bytes) -> bool | None:
    if not path.exists():
        return None
    people = json.loads(path.read_text(encoding="utf-8")).get("people", {})
    seen = False
    for entry in people.values():
        seen = True
        try:
            crypto.unwrap_dek(base64.b64decode(entry["wrapped_dek"]), omk)
            return True
        except Exception:  # noqa: BLE001 — a wrong key is the expected failure
            continue  # keep looking: ONE dead entry must not condemn the file
    return False if seen else None  # None = present but empty


def _rewrap_knowledge(path: Path, old: bytes, new: bytes) -> int:
    """Re-wrap every per-person DEK under the new OMK. The bundles themselves
    are not re-encrypted (their DEK does not change) — see wrap_dek.

    An entry the old key cannot open is carried across untouched rather than
    dropped or fatal: it is already unreadable, and one corrupt record must not
    make the upgrade impossible forever.
    """
    doc = json.loads(path.read_text(encoding="utf-8"))
    rewrapped = 0
    for entry in doc.get("people", {}).values():
        try:
            dek = crypto.unwrap_dek(base64.b64decode(entry["wrapped_dek"]), old)
        except Exception:  # noqa: BLE001
            continue
        entry["wrapped_dek"] = base64.b64encode(crypto.wrap_dek(dek, new)).decode()
        rewrapped += 1
    _write_doc(path, doc)
    return rewrapped


def _probe_recognition(path: Path, omk: bytes) -> bool | None:
    if not path.exists():
        return None
    embeddings = json.loads(path.read_text(encoding="utf-8")).get("embeddings", {})
    seen = False
    for pid, val in embeddings.items():
        for blob in (val if isinstance(val, list) else [val]):
            seen = True
            try:
                crypto.decrypt(omk, base64.b64decode(blob), aad=pid.encode())
                return True
            except Exception:  # noqa: BLE001
                continue
    return False if seen else None


def _rewrap_recognition(path: Path, old: bytes, new: bytes) -> int:
    """Embeddings are encrypted under the OMK directly (AAD-bound to the person),
    so these DO have to be decrypted and re-encrypted. As with the knowledge
    store, a sample that will not open is kept as-is rather than dropped."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    embeddings = doc.get("embeddings", {})
    moved = 0
    for pid, val in embeddings.items():
        out = []
        for blob in (val if isinstance(val, list) else [val]):
            try:
                plain = crypto.decrypt(old, base64.b64decode(blob), aad=pid.encode())
            except Exception:  # noqa: BLE001
                out.append(blob)
                continue
            out.append(base64.b64encode(
                crypto.encrypt(new, plain, aad=pid.encode())).decode())
            moved += 1
        embeddings[pid] = out
    doc["embeddings"] = embeddings
    _write_doc(path, doc)
    return moved


_KINDS = {
    "knowledge": (_probe_knowledge, _rewrap_knowledge),
    "recognition": (_probe_recognition, _rewrap_recognition),
}


# ----------------------------------------------------------------------------
# The entry point
# ----------------------------------------------------------------------------

def open_omk(*, passphrase: str, params_path: str | Path,
             knowledge_paths: list[str | Path] | None = None,
             recognition_paths: list[str | Path] | None = None,
             env_salt: str | None = None) -> tuple[bytes, dict]:
    """Return ``(omk, report)``, migrating any store still on old parameters.

    ``report`` carries what actually happened, so the caller can log something
    truthful instead of assuming success::

        {"migrated": {path: entries}, "already_current": [path],
         "unreadable": [path], "kdf_n": int}

    ``unreadable`` is not an error: it is a store neither key opens, which in
    practice means a file left behind by an earlier install. It is left exactly
    as found. Raises :class:`OmkError` — before writing anything — only when the
    KNOWLEDGE store itself will not open, since that is the case where carrying
    on would look like data loss to the owner.
    """
    params_path = Path(params_path)
    stores = [(Path(p), "knowledge") for p in (knowledge_paths or [])]
    stores += [(Path(p), "recognition") for p in (recognition_paths or [])]
    legacy_data_exists = any(p.exists() for p, _ in stores)

    doc = load_or_init(params_path, env_salt=env_salt,
                       legacy_data_exists=legacy_data_exists)
    current = KdfParams.from_dict(doc["current"])
    omk = current.derive(passphrase)
    report: dict = {"migrated": {}, "already_current": [], "unreadable": [],
                    "kdf_n": current.n}

    if "migrating_from" not in doc:
        return omk, report

    # Pass 1: decide for every store WITHOUT writing, so an abort leaves the
    # data exactly as it was rather than half-rotated. The old key is derived
    # only if some store actually still needs it — on a normal boot after the
    # migration this loop finds nothing and we never pay for a second scrypt.
    stale: list[tuple[Path, str]] = []
    for path, kind in stores:
        probe, _ = _KINDS[kind]
        state = probe(path, omk)
        if state is True:
            report["already_current"].append(str(path))
        elif state is False:
            stale.append((path, kind))
        # None → absent or empty; nothing to carry over

    if stale:
        old_omk = KdfParams.from_dict(doc["migrating_from"]).derive(passphrase)
        movable: list[tuple[Path, str]] = []
        for path, kind in stale:
            probe, _ = _KINDS[kind]
            if probe(path, old_omk) is True:
                movable.append((path, kind))
            else:
                report["unreadable"].append(str(path))

        # A store that opens under NEITHER key is either foreign (left over
        # from another install) or the passphrase is wrong — indistinguishable
        # from here. Only the KNOWLEDGE store is worth failing the boot over:
        # if it is there and will not open, carrying on would show the owner an
        # empty profile list and invite them to start typing over data that is
        # still perfectly intact. Face embeddings are rebuildable; a stale
        # recognition file must never be the reason nothing starts.
        blocked = [p for p, kind in stale
                   if kind == "knowledge" and str(p) in report["unreadable"]]
        if blocked:
            raise OmkError(
                f"{', '.join(p.name for p in blocked)} cannot be opened with "
                "either the current or the previous key parameters. The "
                "passphrase is most likely wrong; nothing was modified."
            )

        # Pass 2: rewrite. Each store is atomic on its own.
        for path, kind in movable:
            _, rewrap = _KINDS[kind]
            report["migrated"][str(path)] = rewrap(path, old_omk, omk)

    # `migrating_from` is deliberately NOT removed. These are public KDF
    # parameters, not a key, and keeping them means a store that was missed
    # here — one behind a feature flag, one restored from an old backup — can
    # still be recovered on a later boot. Dropping them would make that
    # permanent data loss to save nine bytes.
    return omk, report
