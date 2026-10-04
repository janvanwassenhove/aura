"""U168b/c: environment + singleton guards for the whole orchestrator suite.

Two classes of leak bit us on Linux CI (invisible on the dev machine, where a
real OPENAI_API_KEY exists and quietly turned test_latency into a REAL API
call):

1. orchestrator.config builds its singleton AT IMPORT TIME from LLM_PROVIDER
   (default "openai"); per-test-module setdefault lines were a race against
   import order. conftest imports before any test module — earliest hook.

2. Tests that call update_config() mutate the module-global singleton;
   monkeypatch restores env vars but not module globals, so provider=openai
   leaked into every later test. The autouse fixture below restores it.
"""

import os

import pytest

os.environ.setdefault("LLM_PROVIDER", "echo")


@pytest.fixture(autouse=True)
def _restore_llm_config():
    from orchestrator import config as _cfg

    before = (_cfg._config.provider, _cfg._config.model)
    yield
    _cfg._config.provider, _cfg._config.model = before


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
