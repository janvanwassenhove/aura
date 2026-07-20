"""U168b: environment guard for the whole orchestrator suite.

orchestrator.config builds its singleton AT IMPORT TIME from LLM_PROVIDER
(default "openai"). Individual test modules doing os.environ.setdefault at
their top are a race against import order — won locally, lost on Linux CI,
where test_latency then tried to build a real OpenAI client without a key.
conftest.py imports before any test module, so this is the earliest hook.
"""

import os

os.environ.setdefault("LLM_PROVIDER", "echo")
