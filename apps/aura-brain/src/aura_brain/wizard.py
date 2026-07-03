"""AURA setup wizard (U30) — guided first-run configuration for device day.

Run with:  uv run python -m aura_brain.wizard   (from the repo root)

Walks the owner through every choice needed to bring AURA up on real hardware:
robot connection, LLM provider + key, voice pipeline, offline resilience,
security (knowledge passphrase, step-up webhook, dev agent), persona,
connectors — then seeds the household's people directly into the encrypted
knowledge store so the brain knows everyone on first boot.

Output: an env file (default ``infra/dev/.env``, used by docker compose) and,
when a knowledge passphrase is set, the encrypted ``knowledge.enc.json``.

Security notes (ADR-008):
  - Secrets are read without echo (getpass) and are never printed back.
  - People are stored encrypted (AES-256-GCM under the OMK) — the wizard
    refuses to seed people without a passphrase rather than write plaintext.
  - A random KNOWLEDGE_SALT is generated per install.
"""

from __future__ import annotations

import asyncio
import getpass
import secrets
from collections.abc import Callable
from pathlib import Path

from shared_schemas.knowledge import EncryptedKnowledgeStore, crypto
from shared_schemas.knowledge.models import Person, PersonRole, ProfileFact

_LLM_PROVIDERS: dict[str, tuple[str, str, str]] = {
    # provider -> (key env var ("" = none), default model, note)
    "openai": ("OPENAI_API_KEY", "gpt-4o-mini", "requires an OpenAI API key"),
    "openrouter": ("OPENROUTER_API_KEY", "openai/gpt-oss-120b:free", "free-tier models available"),
    "gemini": ("GEMINI_API_KEY", "gemini-2.5-flash", "requires a Google AI Studio key"),
    "echo": ("", "", "no key — mirrors input back (offline dev/testing)"),
}

_ROLES = [r.value for r in PersonRole]


class SetupWizard:
    """Interactive setup. IO is injectable so every step is unit-testable."""

    def __init__(
        self,
        input_fn: Callable[[str], str] = input,
        print_fn: Callable[[str], None] = print,
        secret_fn: Callable[[str], str] | None = None,
    ) -> None:
        self._input = input_fn
        self._print = print_fn
        self._secret = secret_fn or getpass.getpass
        self.env: dict[str, str] = {}
        self.people: list[tuple[Person, list[ProfileFact]]] = []
        self._passphrase: str | None = None

    # ------------------------------------------------------------------
    # Prompt helpers
    # ------------------------------------------------------------------

    def ask(self, prompt: str, default: str = "") -> str:
        suffix = f" [{default}]" if default else ""
        answer = self._input(f"{prompt}{suffix}: ").strip()
        return answer or default

    def ask_choice(self, prompt: str, choices: list[str], default: str) -> str:
        while True:
            answer = self.ask(f"{prompt} ({'/'.join(choices)})", default).lower()
            if answer in choices:
                return answer
            self._print(f"  Please pick one of: {', '.join(choices)}")

    def ask_yes_no(self, prompt: str, default: bool = False) -> bool:
        answer = self.ask(f"{prompt} (y/n)", "y" if default else "n").lower()
        return answer.startswith("y")

    # ------------------------------------------------------------------
    # Steps
    # ------------------------------------------------------------------

    def step_robot(self) -> None:
        self._print("\n== 1. Robot connection ==")
        self._print("Where does robot-runtime run? On the real device that is the")
        self._print("Reachy Mini's Pi (see docs: two-host bring-up); for a dry run, localhost.")
        url = self.ask("Robot runtime URL", "http://reachy.local:8001")
        self.env["ROBOT_RUNTIME_URL"] = url
        adapter = self.ask_choice("Robot adapter — fake needs no hardware", ["reachy", "fake"], "reachy")
        self.env["ROBOT_ADAPTER"] = adapter
        if self.ask_yes_no("Check the robot link now?", default=False):
            self._check_robot(url)

    def _check_robot(self, url: str) -> None:
        try:
            import httpx

            resp = httpx.get(f"{url.rstrip('/')}/health", timeout=3.0)
            if resp.status_code == 200:
                self._print("  ✓ robot-runtime is reachable.")
            else:
                self._print(f"  ✗ robot answered HTTP {resp.status_code} — check the Pi.")
        except Exception as exc:  # noqa: BLE001 — wizard must not crash on a dead link
            self._print(f"  ✗ could not reach {url} ({type(exc).__name__}). You can fix this later.")

    def step_llm(self) -> None:
        self._print("\n== 2. LLM provider ==")
        for name, (_, _, note) in _LLM_PROVIDERS.items():
            self._print(f"  {name:<11}— {note}")
        provider = self.ask_choice("Provider", list(_LLM_PROVIDERS), "openai")
        self.env["LLM_PROVIDER"] = provider
        key_var, default_model, _ = _LLM_PROVIDERS[provider]
        if key_var:
            key = self._secret(f"{key_var} (input hidden, Enter to keep host env var): ").strip()
            if key:
                self.env[key_var] = key
            model_var = key_var.replace("_API_KEY", "_MODEL")
            self.env[model_var] = self.ask("Model", default_model)

    def step_voice(self) -> None:
        self._print("\n== 3. Voice pipeline ==")
        self.env["STT_PROVIDER"] = self.ask_choice(
            "Speech-to-text (null = text-only console)",
            ["null", "local_whisper", "openai_realtime"], "local_whisper",
        )
        self.env["TTS_PROVIDER"] = self.ask_choice(
            "Text-to-speech (kokoro/piper run offline)",
            ["null", "kokoro", "piper", "openai"], "kokoro",
        )

    def step_offline(self) -> None:
        self._print("\n== 4. Offline resilience ==")
        self.env["HEARTBEAT_ENABLED"] = "true" if self.ask_yes_no(
            "Enable heartbeat monitoring (robot link + internet)?", default=True
        ) else "false"
        if self.ask_yes_no("Use a local model when the internet is down (ollama/llama.cpp)?"):
            self.env["OFFLINE_LLM_BASE_URL"] = self.ask(
                "Local OpenAI-compatible URL", "http://localhost:11434/v1"
            )
            self.env["OFFLINE_LLM_MODEL"] = self.ask("Local model", "llama3.1")

    def step_security(self) -> None:
        self._print("\n== 5. Security (ADR-008) ==")
        self._print("The knowledge passphrase encrypts everything AURA learns about")
        self._print("people (AES-256-GCM). Without it, profiles are memory-only and lost")
        self._print("on restart. It is asked ONCE per brain start — never spoken aloud.")
        while True:
            p1 = self._secret("Knowledge passphrase (input hidden, Enter to skip): ")
            if not p1:
                self._print("  ⚠ skipping encryption — people will NOT persist across restarts.")
                break
            p2 = self._secret("Confirm passphrase: ")
            if p1 == p2:
                self._passphrase = p1
                self.env["KNOWLEDGE_SALT"] = secrets.token_hex(8)  # 16 hex chars
                if self.ask_yes_no(
                    "Store the passphrase in .env for auto-unlock at boot? "
                    "(convenient; anyone with laptop access can read it)"
                ):
                    self.env["KNOWLEDGE_PASSPHRASE"] = p1
                else:
                    self._print("  → set KNOWLEDGE_PASSPHRASE in the environment at each start.")
                break
            self._print("  Passphrases do not match — try again.")
        webhook = self.ask("Step-up approval webhook URL (phone notification; Enter to skip)")
        if webhook:
            self.env["STEP_UP_WEBHOOK_URL"] = webhook
        else:
            self._print("  ⚠ no step-up webhook: destructive knowledge ops will be auto-denied.")
        self.env["DEV_AGENT_ENABLED"] = "true" if self.ask_yes_no(
            "Enable the outbound dev agent (repo writes need approval)?"
        ) else "false"

    def step_persona(self) -> None:
        self._print("\n== 6. Mode & connectors ==")
        self.env["ACTIVE_PERSONA"] = self.ask_choice(
            "Startup mode", ["work", "home", "presentation", "silent_desk", "demo"], "work",
        )
        self.env["M365_CONNECTOR"] = self.ask_choice(
            "Microsoft 365 connector (mock = fake data, no account)",
            ["mock", "workiq"], "mock",
        )
        self.env["ENABLED_CONNECTORS"] = self.ask(
            "Enabled connectors (comma-separated: m365,google,github,slack)", "m365",
        )

    def step_people(self) -> None:
        self._print("\n== 7. People ==")
        if self._passphrase is None:
            self._print("  Skipped: people can only be seeded into the ENCRYPTED store")
            self._print("  (set a knowledge passphrase in step 5, or add people later")
            self._print("  via the console's 🧠 Knowledge panel).")
            return
        self._print("Who should AURA know? Add the owner first. Facts are optional")
        self._print("key=value lines (e.g. likes=espresso). Minors get explicit facts")
        self._print("only — AURA never learns passively about them.")
        while True:
            name = self.ask("\nPerson's display name (Enter to finish)")
            if not name:
                break
            default_id = name.lower().split()[0]
            pid = self.ask("Short id", default_id)
            default_role = "owner" if not self.people else "family"
            role = self.ask_choice("Role", _ROLES, default_role)
            person = Person(person_id=pid, display_name=name, role=PersonRole(role))
            facts: list[ProfileFact] = []
            while True:
                line = self.ask("  Fact key=value (Enter to stop)")
                if not line or "=" not in line:
                    break
                key, value = line.split("=", 1)
                facts.append(ProfileFact(person_id=pid, key=key.strip(), value=value.strip()))
            self.people.append((person, facts))
            self._print(f"  ✓ {name} ({role}), {len(facts)} fact(s)")

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def render_env(self) -> str:
        lines = [
            "# AURA — generated by the setup wizard (python -m aura_brain.wizard)",
            "# Secrets live here: keep this file out of version control.",
            "",
        ]
        lines += [f"{key}={value}" for key, value in self.env.items()]
        return "\n".join(lines) + "\n"

    def write_env(self, path: Path) -> None:
        if path.exists():
            backup = path.with_suffix(path.suffix + ".bak")
            backup.write_bytes(path.read_bytes())
            self._print(f"  (existing {path.name} backed up to {backup.name})")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.render_env(), encoding="utf-8")
        self._print(f"  ✓ wrote {path}")

    def seed_people(self, data_dir: Path) -> Path | None:
        if self._passphrase is None or not self.people:
            return None
        # Same derivation as aura_brain.main: the salt STRING's bytes, padded to 16.
        salt = self.env["KNOWLEDGE_SALT"].encode().ljust(16, b"0")[:16]
        db_path = data_dir / "knowledge.enc.json"
        store = EncryptedKnowledgeStore(crypto.derive_omk(self._passphrase, salt), path=db_path)

        async def _seed() -> None:
            for person, facts in self.people:
                await store.upsert_person(person)
                for fact in facts:
                    await store.add_fact(fact)

        asyncio.run(_seed())
        self._print(f"  ✓ seeded {len(self.people)} people into {db_path} (encrypted)")
        return db_path

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def run(self, env_path: Path, data_dir: Path) -> None:
        self._print("AURA setup wizard — answer a few questions; Enter accepts the default.")
        self.step_robot()
        self.step_llm()
        self.step_voice()
        self.step_offline()
        self.step_security()
        self.step_persona()
        self.step_people()
        self._print("\n== 8. Writing configuration ==")
        self.write_env(env_path)
        self.seed_people(data_dir)
        self._print("\nDone. Next steps:")
        self._print("  1. Start the stack:  docker compose -f infra/dev/docker-compose.yml up --build")
        self._print("     (or bare-metal: see docs/setup-guide.md)")
        self._print("  2. Open the console: http://localhost:5173  (🧠 = knowledge, ⚙ = settings)")
        self._print("  3. Full guide:       docs/setup-guide.md")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    SetupWizard().run(
        env_path=repo_root / "infra" / "dev" / ".env",
        data_dir=repo_root / "data",
    )


if __name__ == "__main__":
    main()
