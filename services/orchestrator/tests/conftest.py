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
