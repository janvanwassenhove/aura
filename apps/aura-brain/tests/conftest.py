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

# U226: GESTURES_ENABLED defaults to true, so every create_app() in this suite
# built a real mediapipe hand landmarker — an 8 MB model and native threads,
# hundreds of times over. Besides being slow, the objects were only released by
# the garbage collector, whose finaliser blocks on a mediapipe worker future;
# firing mid-test it hung the whole run (reproduced: stalled at test 22 of 343).
# Gesture behaviour has its own tests that construct a detector explicitly.
os.environ.setdefault("GESTURES_ENABLED", "false")


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


@pytest.fixture(autouse=True)
def _own_mode_policy(monkeypatch, tmp_path):
    """U401: every test gets its own mode policy, never the owner's.

    A source checkout keeps the running AURA's policy in ./data — Quiet, each
    mode's behaviour, the boundaries. A test that named no path read it (twenty
    went red the morning the owner switched Quiet on) and could have written it.
    Work is active and nothing is quiet, as on a fresh install.
    """
    monkeypatch.setenv("MODE_POLICY_PATH", str(tmp_path / "mode-policy.json"))
    try:
        from orchestrator import mode_policy
    except Exception:  # noqa: BLE001 — a suite without the orchestrator has no policy
        yield
        return
    mode_policy.reset_cache_for_tests()
    mode_policy.set_active("work")
    yield
    mode_policy.reset_cache_for_tests()
    mode_policy.set_active("work")


@pytest.fixture(autouse=True)
def _own_recordings(monkeypatch, tmp_path):
    """U409: a talk's lines are recorded to disk and kept between runs. Without
    this a test would write takes into ./scenarios/recordings, and find the
    previous test's take of the same words instead of its own."""
    monkeypatch.setenv("RECORDINGS_DIR", str(tmp_path / "recordings"))
    from aura_brain import recordings

    recordings.reset()
    yield
    recordings.reset()
