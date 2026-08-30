"""U266: "I cannot look" must never render as "I am waiting".

Reported with a slideshow running full-screen behind the message: the overlay
said "waiting for your slideshow (F5 / Play)" and kept saying it. He was not
waiting. The packaged app's bootstrap never asked `uv sync` for the
`presentation` extra, so pywin32 — the only way he reads which slide
PowerPoint is on — was pruned out of every installed build. It worked
perfectly in the dev tree, which is where it was tested.

Two different states had one appearance, and the visible one told the
presenter to do the thing they had already done.
"""

from __future__ import annotations

import builtins
import platform

import pytest
from aura_brain import slides_watcher


@pytest.fixture(autouse=True)
def _fresh_probe():
    slides_watcher.read_blocker.cache_clear()
    yield
    slides_watcher.read_blocker.cache_clear()


def test_a_missing_pywin32_is_named_not_hidden(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    real_import = builtins.__import__

    def no_win32(name, *args, **kwargs):
        if name.startswith("win32com"):
            raise ModuleNotFoundError("No module named 'win32com'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_win32)

    blocker = slides_watcher.read_blocker()
    assert blocker, "a build that cannot read PowerPoint must say so"
    assert "pywin32" in blocker
    # It must also say what to DO — the old message's whole failing was that
    # it sent the presenter back to a key they had already pressed.
    assert "Restart" in blocker
    # And it must not scare anyone off the beats that DO still work.
    assert "keyword" in blocker.lower()


def test_a_working_install_reports_no_blocker(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    pytest.importorskip("win32com.client")
    assert slides_watcher.read_blocker() == ""


def test_linux_is_not_broken_it_simply_has_no_slideshow(monkeypatch):
    """No PowerPoint and no Keynote is a fact of the platform, not a fault."""
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    assert slides_watcher.read_blocker() == ""
