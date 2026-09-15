"""U363: the brain's log recorded no beats.

Found while diagnosing a beat that did not speak during Devoxx prep. The
question was simply "did that beat fire?" — the runner logs exactly that, at
INFO:

    logger.info("beat %r fired (mode=%s trigger=%s)", ...)

and `brain.log` contained 20 MB of uvicorn access lines and **not one of them**.
Nothing configured logging: `uvicorn.run()` sets up its own loggers and leaves
the root at WARNING, so every `logger.info` in the app was discarded on the way
out. During a talk that file is the only record there is.
"""

from __future__ import annotations

import logging

import pytest
from aura_brain.main import configure_logging


@pytest.fixture(autouse=True)
def _restore_logging():
    """Put the root logger back — this test configures it for real.

    Our own handler is dropped before AND after: before, so each test gets one
    bound to the capture stream that is live right now; after, so nothing here
    leaks into the rest of the suite. Other handlers are left strictly alone —
    closing pytest's was how the first version of this broke six unrelated
    tests.
    """
    root = logging.getLogger()
    level_before = root.level
    noisy_before = {n: logging.getLogger(n).level for n in ("httpx", "httpcore",
                                                            "urllib3", "openai",
                                                            "PIL", "asyncio")}

    def _drop_ours() -> None:
        for h in [h for h in root.handlers if getattr(h, "_aura", False)]:
            root.removeHandler(h)

    _drop_ours()
    yield
    _drop_ours()
    root.setLevel(level_before)
    for name, lvl in noisy_before.items():
        logging.getLogger(name).setLevel(lvl)


def test_the_apps_own_loggers_are_heard() -> None:
    configure_logging()
    for name in ("aura_brain", "orchestrator", "orchestrator.scenario_runner"):
        assert logging.getLogger(name).isEnabledFor(logging.INFO), \
            f"{name} INFO is discarded — its lines never reach brain.log"


def test_the_beat_line_actually_comes_out(capsys) -> None:
    """The specific line that was missing when it was needed.

    Read off the stream rather than through `caplog`: `configure_logging` uses
    `basicConfig(force=True)`, which replaces every root handler — pytest's
    included — so caplog sees nothing while the line is printed perfectly. The
    stream is also what `brain.log` actually is, which makes it the honest
    thing to assert on.
    """
    configure_logging()
    logging.getLogger("orchestrator.scenario_runner").info(
        "beat %r fired (mode=%s trigger=%s)", "the-disclaimer", "speak", "slide:8")
    assert "the-disclaimer" in capsys.readouterr().err


def test_the_noisy_libraries_stay_quiet() -> None:
    """INFO on httpx is a line per HTTP call — and the brain polls the robot's
    camera several times a second. Turning the app up must not bury it."""
    configure_logging()
    for noisy in ("httpx", "httpcore", "urllib3", "openai"):
        assert not logging.getLogger(noisy).isEnabledFor(logging.INFO), \
            f"{noisy} at INFO would drown the log it is meant to make readable"


def test_the_level_can_be_turned_down(monkeypatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    configure_logging()
    assert not logging.getLogger("aura_brain").isEnabledFor(logging.INFO)


def test_a_nonsense_level_is_not_fatal(monkeypatch) -> None:
    """A typo in an env var must never stop the brain from starting — it is the
    one process the whole app waits on."""
    monkeypatch.setenv("LOG_LEVEL", "LOUD")
    configure_logging()
    assert logging.getLogger("aura_brain").isEnabledFor(logging.INFO)


def test_configuring_twice_does_not_double_every_line() -> None:
    """Called again (a reload, a test) it must not add a second handler and
    print everything twice."""
    configure_logging()
    first = len(logging.getLogger().handlers)
    configure_logging()
    assert len(logging.getLogger().handlers) == first
