"""U167: the privacy scanner is itself guarded by tests — a guard nobody
trusts gets bypassed, and a guard that rots blocks nothing."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from privacy_scan import ALLOWED_PATHS, check_content, check_path  # noqa: E402

SCRIPT = Path(__file__).parent / "privacy_scan.py"


# --- path classes -----------------------------------------------------------

def test_blocks_the_classes_that_actually_burned_us() -> None:
    # skills/.metrics/*.jsonl held the owner's literal spoken requests (U166).
    assert check_path("skills/.metrics/music.jsonl")
    assert check_path("data/aura-memory.db")
    assert check_path("data/knowledge.enc.json")
    assert check_path("recording.wav")
    assert check_path("brain.log")
    assert check_path(".env")
    assert check_path("infra/prod/.env.local")
    assert check_path("backup/id_rsa")
    assert check_path("aura-brain-export-2026-07-20.json")
    assert check_path("docs/snapshots/jan.jpg")


def test_allows_normal_source_and_the_reviewed_templates() -> None:
    assert not check_path("apps/aura-brain/src/aura_brain/main.py")
    assert not check_path("docs/implementation-backlog.md")
    assert not check_path("package.json")
    for allowed in ALLOWED_PATHS:  # curated templates stay committable
        assert not check_path(allowed), allowed


def test_windows_path_separators_do_not_bypass() -> None:
    assert check_path("skills\\.metrics\\music.jsonl")
    assert check_path("data\\dev.db")


# --- content classes --------------------------------------------------------

def test_flags_real_looking_secrets() -> None:
    assert check_content("x.py", b"OPENAI_API_KEY = 'sk-" + b"a" * 40 + b"'")
    assert check_content("x.md", b"token ghp_" + b"A" * 36)
    assert check_content("x.txt", b"-----BEGIN RSA PRIVATE KEY-----")  # privacy-ok
    assert check_content("x.yml", b'password: "hunter2hunter2hunter2"')  # privacy-ok


def test_flags_personal_email_addresses() -> None:
    assert check_content("x.md", b"contact: someone.real@gmail.com")  # privacy-ok


def test_ignores_placeholders_markers_and_binaries() -> None:
    assert not check_content("x.py", b"monkeypatch.setenv('OPENAI_API_KEY', 'sk-test')")
    assert not check_content("x.env", b"OPENAI_API_KEY=")          # empty value
    fixture = b"PASSPHRASE = 'correct-horse-battery'  # privacy-ok"
    assert not check_content("x.py", fixture)                       # reviewed
    assert not check_content("x.bin", b"\x00\x01sk-" + b"a" * 40)   # binary
    assert not check_content("x.py", b"noreply@anthropic.com")      # not a personal provider


# --- the hook path: staged files are read from the INDEX --------------------

def test_staged_scan_blocks_inside_a_real_repo(tmp_path) -> None:
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True,
                       capture_output=True)

    git("init", "-q")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "test")
    (tmp_path / "notes.md").write_text("api_key = 'sk-" + "a" * 40 + "'")
    git("add", "notes.md")

    r = subprocess.run([sys.executable, str(SCRIPT), "--staged"],
                       cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 1
    assert "OpenAI-style API key" in r.stdout

    # Clean content sails through.
    (tmp_path / "notes.md").write_text("just release notes\n")
    git("add", "notes.md")
    r2 = subprocess.run([sys.executable, str(SCRIPT), "--staged"],
                        cwd=tmp_path, capture_output=True, text=True)
    assert r2.returncode == 0


def test_personal_skill_files_are_blocked() -> None:
    """U183: a skill is the owner's routine (playlists, habits, names). These
    were public in the repo until a history rewrite removed them."""
    assert check_path("skills/music.md")
    assert check_path("skills/vrtmax.md")
    assert not check_path("skills/README.md")   # the explainer stays


# --- the hook itself: a finding must REFUSE the commit ----------------------

def test_the_hook_refuses_the_commit_rather_than_only_printing(tmp_path) -> None:
    """U323: everything above tests the scanner; nothing ran the hook.

    U299 appended a spec warning to `.githooks/pre-commit` after the scan line,
    and a shell script exits with the status of its LAST command — that final
    `if`, which is 0. From then on the hook printed "PRIVACY SCAN FAILED" and
    committed anyway. The scanner's own tests stayed green the whole time,
    because the scanner was fine. So this test commits for real, through a copy
    of the real hook, and asks git whether a commit exists.
    """
    def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=tmp_path, check=check,
                              capture_output=True, text=True)

    root = Path(__file__).resolve().parent.parent
    (tmp_path / "scripts").mkdir()
    shutil.copy(SCRIPT, tmp_path / "scripts" / "privacy_scan.py")
    (tmp_path / ".githooks").mkdir()
    hook = tmp_path / ".githooks" / "pre-commit"
    shutil.copy(root / ".githooks" / "pre-commit", hook)
    os.chmod(hook, 0o755)

    git("init", "-q")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "test")
    git("config", "core.hooksPath", ".githooks")
    (tmp_path / "notes.md").write_text("api_key = 'sk-" + "a" * 40 + "'\n")
    git("add", "notes.md")

    refused = git("commit", "-q", "-m", "leak", check=False)
    assert "PRIVACY SCAN FAILED" in refused.stdout + refused.stderr, "the hook ran"
    assert refused.returncode != 0, "a finding must refuse the commit"
    assert git("rev-parse", "--verify", "HEAD", check=False).returncode != 0, \
        "and no commit may exist afterwards"

    # A clean commit still goes through — a gate that refuses everything gets
    # bypassed with --no-verify, which is worse than no gate.
    (tmp_path / "notes.md").write_text("just release notes\n")
    git("add", "notes.md")
    assert git("commit", "-q", "-m", "clean", check=False).returncode == 0
