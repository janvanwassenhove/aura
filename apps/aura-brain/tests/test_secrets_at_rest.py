r"""U340: the keys were in a file that anything with read on Roaming could open.

Asked, after pairing a second machine: *"moeten we deze file niet beveiligen
ook?"* — about `%APPDATA%\aura-desktop\.env`.

U225 moved the knowledge passphrase into the OS credential store, and its own
docstring names the reason: that file sits beside the ciphertext with the same
ACL, so "encrypted at rest" protected nothing it was likely to face. Only the
passphrase moved. The OpenAI key, the OpenRouter and Gemini keys, the calendar
sharing link and — since U339 — the robot's pairing key all stayed in plain
text in exactly the file that argument was about.

On the owner's own machine that file inherits a **read** grant for a local
sandbox group from `%APPDATA%\Roaming`. And Roaming is precisely what a managed
work laptop synchronises to a corporate share.

So: the same treatment as the passphrase. The credential store when there is
one, the file when there is not (docker, CI, headless — breaking those to fix a
desktop problem would be a poor trade), the environment always winning, and the
file itself locked down to its owner wherever it must still exist.

What this does NOT defend against, and must not be described as if it did:
anything running as the owner. The credential store hands a secret to any
process of that user. What it removes is the *copy* — a synced profile, a
second account, a support zip, a backup, a screenshare.
"""

from __future__ import annotations

import logging
import os

os.environ.setdefault("LLM_PROVIDER", "echo")

import pytest
from aura_brain import secret_store, setup_api
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Deliberately not shaped like a real key: the privacy scan refuses those,
# and a test fixture is exactly where a real one would hide.
PLACEHOLDER = "placeholder-value-0000"


@pytest.fixture()
def env_file(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    monkeypatch.setenv("AURA_ENV_FILE", str(path))
    for name in secret_store.MANAGED:
        monkeypatch.delenv(name, raising=False)
    return path


@pytest.fixture()
def client(env_file):
    app = FastAPI()
    app.include_router(setup_api.router)
    return TestClient(app), env_file


def test_a_new_key_goes_to_the_credential_store_not_the_file(client) -> None:
    c, path = client
    assert c.post("/setup/config", json={"openai_api_key": PLACEHOLDER}).status_code == 200

    assert secret_store.get("OPENAI_API_KEY") == PLACEHOLDER
    assert PLACEHOLDER not in (path.read_text(encoding="utf-8") if path.exists() else "")
    # and it still works right now, without a restart
    assert os.environ["OPENAI_API_KEY"] == PLACEHOLDER


def test_without_a_credential_store_the_file_still_works(client, monkeypatch) -> None:
    """Docker, CI and headless installs have no keyring. Breaking them to fix a
    desktop problem would be a poor trade (U225 made the same call)."""
    c, path = client
    monkeypatch.setattr(secret_store, "_keyring", lambda: None)

    assert c.post("/setup/config", json={"openai_api_key": PLACEHOLDER}).status_code == 200
    assert f"OPENAI_API_KEY={PLACEHOLDER}" in path.read_text(encoding="utf-8")


def test_keys_already_in_the_file_are_moved_out_of_it(env_file) -> None:
    """The owner has had these in plain text for months. Storing new ones
    safely while the old ones sit there changes nothing at all."""
    env_file.write_text(
        f"LLM_PROVIDER=openai\nOPENAI_API_KEY={PLACEHOLDER}\nROBOT_SHARED_SECRET=pair-42\n",
        encoding="utf-8")

    moved = secret_store.migrate_env_file(env_file)

    assert set(moved) == {"OPENAI_API_KEY", "ROBOT_SHARED_SECRET"}
    text = env_file.read_text(encoding="utf-8")
    assert PLACEHOLDER not in text and "pair-42" not in text
    assert "LLM_PROVIDER=openai" in text, "it took a setting that was not a secret"
    assert secret_store.get("ROBOT_SHARED_SECRET") == "pair-42"


def test_nothing_is_deleted_when_the_store_will_not_take_it(env_file, monkeypatch) -> None:
    """Deleting the only copy of a key because a write *seemed* to succeed is
    how someone loses access to their own account."""
    env_file.write_text(f"OPENAI_API_KEY={PLACEHOLDER}\n", encoding="utf-8")

    class _Amnesiac:
        def get_password(self, service, account):
            return None                      # accepts writes, serves nothing
        def set_password(self, service, account, value):
            return None
        def delete_password(self, service, account):
            return None

    monkeypatch.setattr(secret_store, "_keyring", lambda: _Amnesiac())

    assert secret_store.migrate_env_file(env_file) == []
    assert f"OPENAI_API_KEY={PLACEHOLDER}" in env_file.read_text(encoding="utf-8")


def test_the_environment_still_wins(env_file, monkeypatch) -> None:
    """docker-compose, CI and a shell that exports a key must keep control —
    and a stale credential-store entry must never shadow them."""
    secret_store.put("OPENAI_API_KEY", "from-the-keyring")
    monkeypatch.setenv("OPENAI_API_KEY", "from-the-environment")

    secret_store.load_into_env()

    assert os.environ["OPENAI_API_KEY"] == "from-the-environment"


def test_a_stored_key_is_loaded_at_boot(env_file) -> None:
    secret_store.put("ROBOT_SHARED_SECRET", "pair-42")
    secret_store.load_into_env()
    assert os.environ["ROBOT_SHARED_SECRET"] == "pair-42"


def test_no_secret_is_ever_written_to_the_log(env_file, caplog) -> None:
    env_file.write_text(f"OPENAI_API_KEY={PLACEHOLDER}\n", encoding="utf-8")
    with caplog.at_level(logging.DEBUG):
        secret_store.migrate_env_file(env_file)
        secret_store.load_into_env()
    assert PLACEHOLDER not in caplog.text
    assert "OPENAI_API_KEY" in caplog.text, "say WHICH key moved, never its value"


def test_the_file_is_locked_to_its_owner(env_file, monkeypatch) -> None:
    """Wherever a file must still hold something, it stops inheriting whatever
    the profile directory hands out. On this owner's machine that inheritance
    is a read grant for a local sandbox group."""
    monkeypatch.setattr(secret_store, "_keyring", lambda: None)
    env_file.write_text("OPENAI_API_KEY=x\n", encoding="utf-8")

    assert secret_store.harden(env_file) is True

    if os.name != "nt":
        assert (env_file.stat().st_mode & 0o077) == 0
    else:
        import subprocess
        out = subprocess.run(["icacls", str(env_file)], capture_output=True,
                             text=True, check=False).stdout
        assert "(I)" not in out, f"still inheriting the profile's grants:\n{out}"


def test_writing_the_file_hardens_it(client, monkeypatch) -> None:
    """A harden() nobody calls is a comment. It runs on every write, because a
    rewrite can restore inheritance."""
    seen: list[str] = []
    monkeypatch.setattr(secret_store, "harden", lambda p: seen.append(str(p)) or True)
    c, path = client

    c.post("/setup/config", json={"llm_provider": "openai"})

    assert seen and seen[0] == str(path)


def test_starting_the_brain_moves_what_is_already_there(env_file, monkeypatch) -> None:
    """The whole point of the unit: the owner's key has been sitting in that
    file since the wizard wrote it. It has to leave on its own, on the next
    start, without anybody knowing this happened."""
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    env_file.write_text(f"OPENAI_API_KEY={PLACEHOLDER}\nVOICE_MODE=off\n", encoding="utf-8")

    from aura_brain.main import create_app

    with TestClient(create_app()):
        pass

    text = env_file.read_text(encoding="utf-8")
    assert PLACEHOLDER not in text, "it is still lying in the file"
    assert "VOICE_MODE=off" in text
    assert secret_store.get("OPENAI_API_KEY") == PLACEHOLDER
