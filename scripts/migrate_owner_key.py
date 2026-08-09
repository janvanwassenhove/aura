"""U225 (audit S9+S10): one-time owner-key migration for an existing install.

Two things move here, and the ORDER matters:

  S9  rotate the Owner Master Key onto a random per-install salt at scrypt
      n=2**17, rewrapping the per-person DEKs and the face embeddings. This
      writes ``key-params.json`` next to the ciphertext.

  S10 move KNOWLEDGE_PASSPHRASE from the .env file into the OS keyring, then
      delete it — and KNOWLEDGE_SALT — from .env.

KNOWLEDGE_SALT may only be removed AFTER key-params.json exists, because until
then it is the only record of how the existing data was encrypted. Deleting it
first would leave the store unopenable. The script enforces that; it does not
rely on the operator remembering.

Nothing is deleted until the replacement has been read back and the data has
been verified to still decrypt. Run with --dry-run first.

    python scripts/migrate_owner_key.py --dry-run
    python scripts/migrate_owner_key.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import socket
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for pkg in ("packages/shared-schemas/src", "apps/aura-brain/src"):
    sys.path.insert(0, str(REPO / pkg))

from aura_brain import secret_store  # noqa: E402
from shared_schemas.knowledge import EncryptedKnowledgeStore  # noqa: E402
from shared_schemas.knowledge import omk as omk_mod  # noqa: E402


def _desktop_dir() -> Path | None:
    appdata = os.environ.get("APPDATA")
    return Path(appdata) / "aura-desktop" if appdata else None


def _default_env_file() -> Path:
    desktop = _desktop_dir()
    if desktop and (desktop / ".env").exists():
        return desktop / ".env"
    return REPO / "infra" / "dev" / ".env"


def _default_data_dir(env_file: Path, env: dict[str, str]) -> Path:
    """Where the ciphertext actually lives.

    KNOWLEDGE_DB_PATH is usually absent from .env: the desktop app injects it
    at spawn time (main.cjs) so an update cannot wipe the data. Defaulting to
    the repo's ./data here would point the migration at stale dev files and
    leave the real store untouched — while reporting success.
    """
    if env.get("KNOWLEDGE_DB_PATH"):
        return Path(env["KNOWLEDGE_DB_PATH"]).parent
    desktop = _desktop_dir()
    if desktop and env_file.parent == desktop:
        return desktop / "data"
    return REPO / "data"


def _read_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _drop_keys(path: Path, keys: set[str]) -> int:
    """Remove whole lines for `keys`, preserving everything else verbatim."""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    kept = [ln for ln in lines
            if not (("=" in ln) and ln.split("=", 1)[0].strip() in keys)]
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("".join(kept), encoding="utf-8")
    os.replace(tmp, path)
    return len(lines) - len(kept)


def _brain_is_running(port: int = 8020) -> bool:
    with socket.socket() as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _count(knowledge_path: Path, recognition_path: Path, key: bytes) -> tuple[int, int]:
    people = 0
    if knowledge_path.exists():
        store = EncryptedKnowledgeStore(key, path=knowledge_path)
        people = len(asyncio.run(store.list_people()))
    # Count embeddings that actually DECRYPT, not merely blobs that exist:
    # sample_count() would report a full gallery of unreadable ciphertext as a
    # success, and face matching would then fail silently later.
    samples = 0
    if recognition_path.exists():
        import base64
        import json as _json

        from shared_schemas.knowledge import crypto

        stored = _json.loads(recognition_path.read_text(encoding="utf-8"))
        for pid, blobs in stored.get("embeddings", {}).items():
            for blob in (blobs if isinstance(blobs, list) else [blobs]):
                try:
                    crypto.decrypt(key, base64.b64decode(blob), aad=pid.encode())
                    samples += 1
                except Exception:  # noqa: BLE001 — counted as not-readable
                    pass
    return people, samples


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--env-file", type=Path, default=None)
    ap.add_argument("--data-dir", type=Path, default=None)
    args = ap.parse_args()

    env_file = args.env_file or _default_env_file()
    if not env_file.exists():
        print(f"!!  no env file at {env_file}")
        return 1
    env = _read_env(env_file)
    data_dir = args.data_dir or _default_data_dir(env_file, env)
    kpath = data_dir / "knowledge.enc.json"
    rpath = data_dir / "recognition.enc.json"
    params_path = data_dir / omk_mod.PARAMS_FILENAME

    print(f"env file : {env_file}")
    print(f"data dir : {data_dir}")

    if _brain_is_running():
        print("\n!!  the brain is listening on 8020. Close AURA (or stop the brain)")
        print("  first -- migrating a store that is being written to can corrupt it.")
        return 1

    passphrase, source = secret_store.get_passphrase(env.get("KNOWLEDGE_PASSPHRASE"))
    if not passphrase:
        print("!!  no passphrase in the env file or the keyring -- nothing to migrate.")
        return 1
    print(f"passphrase source: {source}")

    # --- backup -------------------------------------------------------------
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = data_dir.parent / f"key-migration-backup-{stamp}"
    if args.dry_run:
        print(f"\n[dry-run] would back up to {backup}")
    else:
        backup.mkdir(parents=True, exist_ok=True)
        for src in (kpath, rpath, env_file):
            if src.exists():
                shutil.copy2(src, backup / src.name)
        print(f"\nOK  backed up to {backup}")

    # --- S9 -----------------------------------------------------------------
    already = params_path.exists()
    print(f"\nS9  key parameters: {'present' if already else 'not yet written'}")
    if args.dry_run:
        doc = json.loads(params_path.read_text()) if already else None
        if doc and doc["current"]["n"] >= 2**17:
            print(f"    nothing to do -- already at scrypt n={doc['current']['n']}")
        else:
            print("    would rotate to scrypt n=2**17 with a fresh random salt")
        key = None
    else:
        key, report = omk_mod.open_omk(
            passphrase=passphrase, params_path=params_path,
            knowledge_paths=[kpath], recognition_paths=[rpath],
            env_salt=env.get("KNOWLEDGE_SALT"))
        print(f"    scrypt n={report['kdf_n']}")
        for path, n in report["migrated"].items():
            print(f"    rotated {Path(path).name}: {n} entries")
        for path in report["already_current"]:
            print(f"    {Path(path).name}: already current")
        for path in report["unreadable"]:
            print(f"    !   {Path(path).name}: does not open -- left untouched")

        people, samples = _count(kpath, rpath, key)
        print(f"    verified after rotation: {people} people, {samples} face samples")
        if kpath.exists() and people == 0:
            print("!!  the knowledge store decrypts to zero people -- stopping here.")
            print(f"  Restore from {backup} before doing anything else.")
            return 1

    # --- S10 ----------------------------------------------------------------
    print("\nS10 passphrase location")
    if not secret_store.available():
        print("    !!  no usable OS keyring on this machine -- leaving .env as is.")
        return 1
    if args.dry_run:
        print("    would store the passphrase in the OS keyring, verify it reads")
        print(f"    back, then drop KNOWLEDGE_PASSPHRASE + KNOWLEDGE_SALT from"
              f" {env_file.name}")
        return 0

    if not secret_store.put_passphrase(passphrase):
        print("    !!  keyring write/read-back failed -- .env left untouched.")
        return 1
    print("    OK  stored in the OS keyring and read back")

    # Only now is it safe: the keyring holds the passphrase, and key-params.json
    # holds the salt, so neither is needed in .env any more.
    if not params_path.exists():
        print("    !!  key-params.json missing -- refusing to drop KNOWLEDGE_SALT.")
        return 1
    dropped = _drop_keys(env_file, {"KNOWLEDGE_PASSPHRASE", "KNOWLEDGE_SALT"})
    print(f"    OK  removed {dropped} line(s) from {env_file.name}")

    # --- final check, from the keyring alone --------------------------------
    env_after = _read_env(env_file)
    assert "KNOWLEDGE_PASSPHRASE" not in env_after
    recovered, src2 = secret_store.get_passphrase(env_after.get("KNOWLEDGE_PASSPHRASE"))
    if src2 != "keyring" or not recovered:
        print("!!  the passphrase is no longer retrievable -- RESTORE THE BACKUP NOW.")
        return 1
    key2, _ = omk_mod.open_omk(passphrase=recovered, params_path=params_path,
                               knowledge_paths=[kpath], recognition_paths=[rpath])
    people, samples = _count(kpath, rpath, key2)
    print(f"\nOK  end-to-end: passphrase from keyring -> {people} people, "
          f"{samples} face samples decrypt")
    print(f"  backup kept at {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
