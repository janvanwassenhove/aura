#!/usr/bin/env python3
"""U167: privacy scan — no personal data ever rides along with a commit.

Two layers use this single source of truth:

  * ``--staged``  — the pre-commit hook (.githooks/pre-commit): blocks the
    commit locally before anything personal enters history.
  * ``--all``     — CI (ci.yml + the release test gate): the enforced
    backstop, because hooks can be skipped with --no-verify or a fresh clone.

What counts as personal/sensitive here (deny by CLASS, not by guesswork):

  paths    — databases, audio recordings, logs, skill-usage logs (they contain
             the owner's literal spoken requests — found committed once, U166),
             encrypted stores/exports, key material, .env files.
  content  — API keys/tokens (OpenAI, GitHub, Slack, AWS, Google), private key
             blocks, credential assignments WITH a real-looking value, and
             personal e-mail addresses.

Escape hatches, both explicit and reviewable:
  * ALLOWED_PATHS — files that look like a denied class but are curated
    templates (e.g. .env.example with empty values). Content is still scanned.
  * a ``privacy-ok`` marker on the same line silences a content finding
    (e.g. a documented fake key in a test).

Stdlib only — runs anywhere Python 3.10+ exists, no sync needed.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# --- path rules (case-insensitive, matched against the repo-relative path) ---

DENY_PATHS: tuple[tuple[str, str], ...] = (
    (r"(^|/)data/", "runtime data directory (databases, encrypted stores)"),
    (r"(^|/)skills/\.metrics(/|$)", "skill usage logs — contain literal spoken requests"),
    # U183: a skill file is a personal routine (playlists, habits, names).
    (r"(^|/)skills/(?!README\.md$)[^/]+\.md$", "personal skill (owner routine)"),
    (r"\.(db|sqlite3?|sqlite)$", "database file"),
    (r"\.enc\.json$", "encrypted personal-data store"),
    (r"\.(wav|pcm|mp3|ogg|flac|m4a)$", "audio recording"),
    (r"\.log$", "log file"),
    (r"\.jsonl$", "line-log file (observations/transcripts)"),
    (r"(^|/)\.env($|\.)", "environment file (credentials)"),
    (r"\.(pem|p12|pfx)$", "key/certificate material"),
    (r"(^|/)id_(rsa|ed25519|ecdsa)(\.|$)", "SSH private key"),
    (r"aura-brain-export.*\.json$", "brain export (full personal profile dump)"),
    (r"(^|/)(snapshots?|sightings?)/.*\.(png|jpe?g|webp)$", "camera snapshot"),
)

# Files that MATCH a deny rule but are deliberate, reviewed templates.
# Content rules still apply to them.
ALLOWED_PATHS: frozenset[str] = frozenset({
    "infra/dev/.env.example",
    "apps/operator-console/.env.production",  # localhost URLs only, by design
})

# --- content rules (scanned in text files; a `privacy-ok` marker skips a line) ---

DENY_CONTENT: tuple[tuple[str, str], ...] = (
    (r"sk-[A-Za-z0-9_-]{20,}", "OpenAI-style API key"),
    (r"ghp_[A-Za-z0-9]{36}", "GitHub personal access token"),
    (r"github_pat_[A-Za-z0-9_]{22,}", "GitHub fine-grained token"),
    (r"xox[baprs]-[A-Za-z0-9-]{10,}", "Slack token"),
    (r"AKIA[0-9A-Z]{16}", "AWS access key"),
    (r"AIza[0-9A-Za-z_-]{35}", "Google API key"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "private key block"),
    (r"(?i)(api_key|apikey|secret|token|passphrase|password|wachtwoord)"
     r"\s*[=:]\s*['\"][A-Za-z0-9+/_-]{12,}['\"]", "credential assignment with a value"),
    (r"(?i)\b[\w.+-]+@(gmail|googlemail|hotmail|outlook|live|icloud|telenet|proximus|skynet)\.[a-z.]{2,6}\b",
     "personal e-mail address"),
)

_MARKER = "privacy-ok"
_MAX_CONTENT_BYTES = 2_000_000  # don't churn through huge blobs


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True,
                          check=True).stdout


def staged_files() -> list[str]:
    out = _git("diff", "--cached", "--name-only", "--diff-filter=ACMR")
    return [line.strip() for line in out.splitlines() if line.strip()]


def tracked_files() -> list[str]:
    return [line.strip() for line in _git("ls-files").splitlines() if line.strip()]


def read_staged(path: str) -> bytes:
    """The INDEX version — what would actually be committed — not the worktree."""
    return subprocess.run(["git", "show", f":{path}"], capture_output=True,
                          check=True).stdout


def read_tracked(path: str) -> bytes:
    p = Path(path)
    return p.read_bytes() if p.exists() else b""


def check_path(path: str) -> list[str]:
    norm = path.replace("\\", "/")
    if norm in ALLOWED_PATHS:
        return []
    return [f"{path}: blocked path — {why}"
            for pattern, why in DENY_PATHS if re.search(pattern, norm, re.IGNORECASE)]


def check_content(path: str, blob: bytes) -> list[str]:
    if not blob or len(blob) > _MAX_CONTENT_BYTES or b"\x00" in blob[:8192]:
        return []  # empty, huge, or binary — path rules cover those classes
    text = blob.decode("utf-8", errors="replace")
    findings: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if _MARKER in line:
            continue
        for pattern, why in DENY_CONTENT:
            if re.search(pattern, line):
                findings.append(f"{path}:{lineno}: {why}")
                break  # one finding per line is enough
    return findings


def scan(paths: list[str], reader) -> list[str]:
    findings: list[str] = []
    for path in paths:
        hits = check_path(path)
        findings.extend(hits)
        if not hits:  # only content-scan files whose path class is fine
            try:
                findings.extend(check_content(path, reader(path)))
            except subprocess.CalledProcessError:
                pass  # deleted/renamed race — nothing to commit from it
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--staged", action="store_true",
                      help="scan files staged for commit (pre-commit hook)")
    mode.add_argument("--all", action="store_true",
                      help="scan every tracked file (CI backstop)")
    args = ap.parse_args()

    if args.staged:
        findings = scan(staged_files(), read_staged)
        context = "staged for commit"
    # (note: output stays pure ASCII — a cp1252 Windows console must never be
    # the reason the guard itself crashes; learned that the hard way in U160)
    else:
        findings = scan(tracked_files(), read_tracked)
        context = "tracked in the repository"

    if findings:
        # ASCII only: this prints on cp1252 Windows consoles and CI alike.
        print(f"PRIVACY SCAN FAILED - personal/sensitive data {context}:\n")
        for f in findings:
            print(f"  [x] {f}")
        print(f"\n{len(findings)} finding(s)."
              "\nFix: unstage the file, or for a reviewed false positive add a"
              f" '{_MARKER}' marker on that line / an ALLOWED_PATHS entry in"
              " scripts/privacy_scan.py (both are visible in review).")
        return 1
    print(f"privacy scan clean ({context}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
