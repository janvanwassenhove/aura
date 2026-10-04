"""U401: the tests never read or write the owner's own settings.

Found while verifying U400 on the owner's machine: twenty brain tests failed
with "quiet switched on". A source checkout keeps the running AURA's mode
policy in `./data/mode-policy.json` — the owner had switched Quiet on that
morning — and every test that did not name its own `MODE_POLICY_PATH` read
that file. CI has no such file, so the suite was green there and red on the
one machine where it matters. Reading was the visible half; a test that
switched Quiet or a mode's behaviour without its own path would have changed
the owner's live settings.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def test_every_test_has_its_own_mode_policy() -> None:
    path = os.environ.get("MODE_POLICY_PATH", "")
    assert path, "no test may fall back to ./data/mode-policy.json"
    assert Path(path).resolve() != (REPO / "data" / "mode-policy.json").resolve()


def test_quiet_starts_off_whatever_the_owner_has() -> None:
    from orchestrator import mode_policy

    assert mode_policy.quiet() is False
    assert mode_policy.active() == "work"
