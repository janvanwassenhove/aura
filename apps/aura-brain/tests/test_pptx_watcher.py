"""U205: the PowerPoint watcher degrades gracefully off-Windows."""

from __future__ import annotations

from aura_brain import pptx_watcher


def test_reports_unavailable_without_powerpoint() -> None:
    """No pywin32 / no slideshow → 'not available', never an exception. The
    manual and keyword triggers still work; you just advance slides by hand."""
    assert pptx_watcher.powerpoint_available() is False
    assert pptx_watcher._read_slide_index() is None
