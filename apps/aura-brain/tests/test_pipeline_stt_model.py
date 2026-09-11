"""U321: the pipeline never sends a realtime-only transcriber to its endpoint.

`gpt-live-transcribe` exists only on realtime transcription sessions. Measured:
POST /v1/audio/transcriptions answers 404 "Invalid URL" for it. STT_MODEL is
read by BOTH the pipeline and the realtime session, and `voice.transcribe`
swallows failures by design — so setting STT_MODEL to the new model, the
obvious thing to try, would have made Richie deaf on the pipeline path with
nothing on screen to say why.
"""

from __future__ import annotations

import logging

import pytest
from aura_brain import voice


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.delenv("STT_MODEL", raising=False)
    voice._warned_stt.clear()


def test_a_realtime_only_transcriber_never_reaches_the_pipeline(monkeypatch, caplog) -> None:
    monkeypatch.setenv("STT_MODEL", "gpt-live-transcribe")
    with caplog.at_level(logging.WARNING, logger="aura_brain.voice"):
        assert voice._pipeline_stt_model() == "gpt-4o-mini-transcribe"
    assert "only works inside realtime sessions" in caplog.text, "and it says so"


def test_it_says_so_once_not_on_every_clip(monkeypatch, caplog) -> None:
    monkeypatch.setenv("STT_MODEL", "gpt-live-transcribe")
    with caplog.at_level(logging.WARNING, logger="aura_brain.voice"):
        for _ in range(5):
            voice._pipeline_stt_model()
    assert caplog.text.count("only works inside realtime sessions") == 1


def test_an_ordinary_transcriber_is_used_as_configured(monkeypatch) -> None:
    monkeypatch.setenv("STT_MODEL", "gpt-4o-transcribe")
    assert voice._pipeline_stt_model() == "gpt-4o-transcribe"


def test_unset_means_the_default() -> None:
    assert voice._pipeline_stt_model() == "gpt-4o-mini-transcribe"
