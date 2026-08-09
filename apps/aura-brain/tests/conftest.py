"""U168b: environment guard for the whole orchestrator suite.

orchestrator.config builds its singleton AT IMPORT TIME from LLM_PROVIDER
(default "openai"). Individual test modules doing os.environ.setdefault at
their top are a race against import order — won locally, lost on Linux CI,
where test_latency then tried to build a real OpenAI client without a key.
conftest.py imports before any test module, so this is the earliest hook.
"""

import os

import pytest

os.environ.setdefault("LLM_PROVIDER", "echo")


@pytest.fixture(autouse=True)
def fake_keyring(monkeypatch):
    """U225: never let the suite touch the developer's real OS keyring.

    The wizard and /setup/secure now store the owner passphrase in the OS
    credential store. Without this, running the tests would overwrite the
    live AURA entry on the developer's own machine with a test passphrase —
    silently locking them out of their own knowledge base.
    """
    from aura_brain import secret_store

    class _InMemoryKeyring:
        def __init__(self) -> None:
            self._values: dict[tuple[str, str], str] = {}

        def get_password(self, service, account):
            return self._values.get((service, account))

        def set_password(self, service, account, value):
            self._values[(service, account)] = value

        def delete_password(self, service, account):
            self._values.pop((service, account), None)

    fake = _InMemoryKeyring()
    monkeypatch.setattr(secret_store, "_keyring", lambda: fake)
    return fake
