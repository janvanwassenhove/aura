"""U140 (voice-brief Phase 0): per-turn latency traces."""

from __future__ import annotations

import os

os.environ.setdefault("LLM_PROVIDER", "echo")

from aura_brain.turn_trace import TraceLog, TurnTrace


def test_mouth_to_ear_and_breakdown() -> None:
    t = TurnTrace(session_id="s", turn_id=1)
    # Fabricate a clean timeline (monotonic seconds).
    base = 100.0
    for stage, offset in [
        ("capture_start", 0.0), ("capture_end", 1.0), ("endpoint_fired", 1.0),
        ("stt_final", 1.3), ("llm_request_sent", 1.3), ("llm_final", 1.7),
        ("tts_request_sent", 1.7), ("tts_first_audio", 1.9),
        ("playback_first_sample", 1.95), ("playback_complete", 3.0),
    ]:
        t.mark(stage, base + offset)
    # endpoint_fired (1.0) → playback_first_sample (1.95) = 950 ms.
    assert t.mouth_to_ear_ms() == 950.0
    bd = t.breakdown_ms()
    assert bd["stt"] == 300.0 and bd["llm"] == 400.0 and bd["tts"] == 200.0
    assert t.to_dict()["mouth_to_ear_ms"] == 950.0


def test_mark_is_write_once() -> None:
    t = TurnTrace(session_id="s", turn_id=1)
    t.mark("stt_final", 5.0)
    t.mark("stt_final", 9.0)  # ignored
    assert t.marks["stt_final"] == 5.0
    t.mark("not_a_stage", 1.0)  # unknown stages are dropped
    assert "not_a_stage" not in t.marks


def test_log_ring_report_and_percentiles(tmp_path) -> None:
    log = TraceLog(keep=10, path=str(tmp_path / "traces.jsonl"))
    for i, m2e in enumerate([200, 400, 600, 800, 1000]):
        t = log.start("s")
        t.mark("endpoint_fired", 0.0)
        t.mark("playback_first_sample", m2e / 1000.0)
        log.finish("s")
    rep = log.report(n=10)
    assert rep["count"] == 5
    assert rep["mouth_to_ear_p50_ms"] == 600.0
    assert rep["mouth_to_ear_p95_ms"] == 1000.0
    # Slowest first.
    assert rep["turns"][0]["mouth_to_ear_ms"] == 1000.0
    # One JSON line per finished turn on disk.
    assert (tmp_path / "traces.jsonl").read_text().count("\n") == 5


def test_dangling_turn_is_finalised_by_next_start() -> None:
    log = TraceLog(keep=10, path="")  # no disk
    log.start("s")  # never finished
    log.start("s")  # finalises the previous one
    log.finish("s")
    assert log.report()["count"] == 2  # both survived, the first with a note


def test_discard_drops_in_flight_trace() -> None:
    log = TraceLog(keep=10, path="")
    log.start("s")
    log.discard("s")
    log.start("s")
    log.finish("s")
    assert log.report()["count"] == 1  # the discarded one is gone
