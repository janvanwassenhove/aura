"""U30: setup wizard — scripted-IO tests, no real terminal or network."""

from __future__ import annotations

from aura_brain.wizard import SetupWizard
from shared_schemas.knowledge import EncryptedKnowledgeStore, crypto

PASSPHRASE = "correct-horse-battery"  # test fixture, privacy-ok


class ScriptedIO:
    def __init__(self, answers: list[str], secrets: list[str] | None = None) -> None:
        self._answers = iter(answers)
        self._secrets = iter(secrets or [])
        self.output: list[str] = []

    def input(self, prompt: str) -> str:
        self.output.append(prompt)
        return next(self._answers)

    def print(self, msg: str) -> None:
        self.output.append(msg)

    def secret(self, prompt: str) -> str:
        self.output.append(prompt)
        return next(self._secrets)


FULL_RUN_ANSWERS = [
    "",                 # robot URL -> default
    "",                 # adapter -> default reachy
    "n",                # check robot link now? no
    "echo",             # LLM provider (no key path)
    "null",             # STT
    "null",             # TTS
    "y",                # heartbeat
    "n",                # local offline model
    "y",                # store passphrase in .env
    "",                 # step-up webhook -> skip
    "n",                # dev agent
    "",                 # mode -> work
    "",                 # m365 -> mock
    "",                 # connectors -> m365
    "Alice",            # person 1 name
    "",                 # id -> alice
    "",                 # role -> owner (first person default)
    "likes=espresso",   # fact
    "",                 # stop facts
    "",                 # finish people
]


def _run_full(tmp_path) -> tuple[SetupWizard, ScriptedIO]:
    io = ScriptedIO(FULL_RUN_ANSWERS, secrets=[PASSPHRASE, PASSPHRASE])
    wizard = SetupWizard(input_fn=io.input, print_fn=io.print, secret_fn=io.secret)
    wizard.run(env_path=tmp_path / ".env", data_dir=tmp_path / "data")
    return wizard, io


def test_full_run_writes_env(tmp_path) -> None:
    _run_full(tmp_path)
    env = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "LLM_PROVIDER=echo" in env
    assert "ROBOT_RUNTIME_URL=http://reachy.local:8001" in env
    assert "ROBOT_ADAPTER=reachy" in env
    assert "HEARTBEAT_ENABLED=true" in env
    assert "DEV_AGENT_ENABLED=false" in env
    assert "ACTIVE_PERSONA=work" in env
    # U225 (S10): the passphrase goes to the OS keyring, never to .env — which
    # lives beside the ciphertext with the same permissions. Same for the salt,
    # which now lives in key-params.json next to the data it describes.
    assert "KNOWLEDGE_PASSPHRASE" not in env
    assert "KNOWLEDGE_SALT" not in env


def test_full_run_stores_the_passphrase_in_the_keyring(tmp_path, fake_keyring) -> None:
    _run_full(tmp_path)
    from aura_brain import secret_store

    assert fake_keyring.get_password(secret_store.SERVICE,
                                     secret_store.ACCOUNT) == PASSPHRASE


def test_full_run_seeds_encrypted_people(tmp_path) -> None:
    wizard, _ = _run_full(tmp_path)
    db = tmp_path / "data" / "knowledge.enc.json"
    assert db.exists()

    # U225: the parameters the wizard used are recorded beside the ciphertext,
    # which is exactly how the brain will find them at boot.
    import json

    from shared_schemas.knowledge import omk as omk_mod

    doc = json.loads((tmp_path / "data" / omk_mod.PARAMS_FILENAME).read_text())
    assert doc["current"]["n"] == crypto.SCRYPT_N
    params = omk_mod.KdfParams.from_dict(doc["current"])
    store = EncryptedKnowledgeStore(params.derive(PASSPHRASE), path=db)
    import asyncio

    async def _check():
        person = await store.get_person("alice")
        assert person is not None and person.role == "owner"
        facts = await store.get_facts("alice")
        assert [(f.key, f.value) for f in facts] == [("likes", "espresso")]

    asyncio.run(_check())
    # Plaintext never on disk.
    raw = db.read_text(encoding="utf-8")
    assert "Alice" not in raw and "espresso" not in raw


def test_passphrase_never_echoed(tmp_path) -> None:
    _, io = _run_full(tmp_path)
    for line in io.output:
        assert PASSPHRASE not in line


def test_skipping_passphrase_skips_people(tmp_path) -> None:
    answers = [
        "", "", "n",        # robot
        "echo",             # llm
        "null", "null",     # voice
        "y", "n",           # offline
        "",                 # webhook skip
        "n",                # dev agent
        "", "", "",         # persona/connectors
        # people step must NOT prompt — no more answers on purpose
    ]
    io = ScriptedIO(answers, secrets=[""])  # empty passphrase -> skip encryption
    wizard = SetupWizard(input_fn=io.input, print_fn=io.print, secret_fn=io.secret)
    wizard.run(env_path=tmp_path / ".env", data_dir=tmp_path / "data")
    assert "KNOWLEDGE_PASSPHRASE" not in wizard.env
    assert not (tmp_path / "data" / "knowledge.enc.json").exists()


def test_existing_env_backed_up(tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("OLD=1\n", encoding="utf-8")
    io = ScriptedIO([], [])
    wizard = SetupWizard(input_fn=io.input, print_fn=io.print, secret_fn=io.secret)
    wizard.env = {"NEW": "2"}
    wizard.write_env(env_path)
    assert (tmp_path / ".env.bak").read_text(encoding="utf-8") == "OLD=1\n"
    assert "NEW=2" in env_path.read_text(encoding="utf-8")


def test_ask_choice_reprompts_on_invalid(tmp_path) -> None:
    io = ScriptedIO(["bogus", "fake"])
    wizard = SetupWizard(input_fn=io.input, print_fn=io.print, secret_fn=io.secret)
    assert wizard.ask_choice("Adapter", ["reachy", "fake"], "reachy") == "fake"


def test_minor_role_accepted_for_children(tmp_path) -> None:
    answers = [
        "Bram",     # name
        "",         # id -> bram
        "minor",    # role
        "",         # no facts
        "",         # finish
    ]
    io = ScriptedIO(answers)
    wizard = SetupWizard(input_fn=io.input, print_fn=io.print, secret_fn=io.secret)
    wizard._passphrase = PASSPHRASE
    wizard.env["KNOWLEDGE_SALT"] = "00" * 8
    wizard.step_people()
    assert wizard.people[0][0].role == "minor"
