"""U329: streamed speech came out of the speaker far quieter than spoken speech.

Reported as "wanneer hij spreekt, is zijn audio heel stil". Measured rather
than guessed, on the owner's robot and on a real recording:

* the hardware mixer was at 100 % (0.00 dB) and the app's digital volume at its
  0.8 default, so neither of those explained it;
* every single playback that day went through `POST /robot/speak/segment` —
  twelve of them, none through the whole-utterance route — because the
  conversation engine is `realtime`, which always streams;
* the whole-utterance path peak-normalises quiet TTS to 0.95 and then applies
  the volume, leaving the speaker at ~0.76. The streamed path deliberately does
  not normalise (U153: per-segment normalisation pumps the volume between
  segments), so it delivered whatever the model sent, times 0.8;
* and the model does not send full-scale audio. A captured reply peaks at
  **0.35**, so the speaker got 0.28 — about **9 dB** below the other path. The
  code's comment claiming "Realtime PCM is already near full-scale" was simply
  wrong.

The fix keeps U153's reason intact: ONE gain for a whole utterance, decided on
its first segment and never raised afterwards, so nothing pumps. A later, louder
segment may pull it DOWN, which is what keeps the sum from clipping.
"""

from __future__ import annotations

import sys
import types

import numpy as np
import pytest


class FakeMini:
    def __init__(self, **kwargs) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.client = types.SimpleNamespace(disconnect=lambda: None)

    def goto_target(self, **kw) -> None:
        self.calls.append(("goto_target", kw))

    def start_head_tracking(self, weight: float = 1.0) -> None: ...

    def stop_head_tracking(self) -> None: ...

    def get_tracked_face(self, wait: bool = True, timeout: float = 5.0):
        return types.SimpleNamespace(detected=False, ts=1.0)

    def set_automatic_body_yaw(self, enabled: bool) -> None: ...

    def set_target_body_yaw(self, yaw: float) -> None: ...

    def wake_up(self) -> None: ...

    def release_media(self) -> None: ...

    def acquire_media(self) -> None: ...


class FakeMedia:
    """The SDK's appsrc media backend, recording what reaches the speaker."""

    def __init__(self, rate: int = 24_000) -> None:
        self.rate = rate
        self.pushed: list[np.ndarray] = []
        self.started = 0

    def get_output_audio_samplerate(self) -> int:
        return self.rate

    def start_playing(self) -> None:
        self.started += 1

    def push_audio_sample(self, pcm) -> None:
        self.pushed.append(np.asarray(pcm, dtype=np.float32).copy())

    def clear_player(self) -> None: ...


@pytest.fixture()
def adapter(monkeypatch):
    monkeypatch.setenv("HEAD_TRACKING", "false")
    monkeypatch.setenv("IDLE_SCAN_S", "0")
    monkeypatch.setenv("TRACKING_WATCHDOG_S", "0")
    monkeypatch.setenv("TALK_ANTENNAS", "false")   # no antenna task in a test
    for var in ("ROBOT_TTS_NORMALIZE", "ROBOT_TTS_TARGET_PEAK", "ROBOT_TTS_MAX_GAIN",
                "ROBOT_VOLUME"):
        monkeypatch.delenv(var, raising=False)
    module = types.ModuleType("reachy_mini")
    module.ReachyMini = lambda **kw: FakeMini(**kw)
    monkeypatch.setitem(sys.modules, "reachy_mini", module)
    from robot_runtime.adapters.reachy import ReachyRobotAdapter

    return ReachyRobotAdapter(host="stub", connection_mode="network",
                              media_backend="no_media")


def _pcm(peak: float, n: int = 2400) -> np.ndarray:
    """A tone at a given peak, as the float mono the adapter works in."""
    t = np.linspace(0.0, 1.0, num=n, endpoint=False, dtype=np.float32)
    return (np.sin(2 * np.pi * 12 * t) * peak).astype(np.float32)


def _bytes(peak: float, n: int = 2400) -> bytes:
    return (_pcm(peak, n) * 32767.0).astype(np.int16).tobytes()


# ── the gain decision ──────────────────────────────────────────────────────

def test_a_quiet_reply_is_lifted_to_the_same_loudness_as_the_other_path(adapter) -> None:
    """0.35 is what the model actually sends; 0.95 is what the whole-utterance
    path delivers before the volume."""
    gain = adapter._segment_gain(_pcm(0.35), new_utterance=True)
    assert gain == pytest.approx(0.95 / 0.35, rel=0.05)


def test_audio_that_is_already_loud_is_left_alone(adapter) -> None:
    assert adapter._segment_gain(_pcm(0.97), new_utterance=True) == pytest.approx(1.0)


def test_the_gain_is_held_for_the_whole_utterance(adapter) -> None:
    """U153's reason: a gain recomputed per segment pumps the volume up and
    down inside one sentence."""
    first = adapter._segment_gain(_pcm(0.35), new_utterance=True)
    quieter = adapter._segment_gain(_pcm(0.05), new_utterance=False)
    assert quieter == pytest.approx(first), "a soft syllable must not be shouted"


def test_a_louder_segment_later_pulls_the_gain_down_rather_than_clipping(adapter) -> None:
    first = adapter._segment_gain(_pcm(0.20), new_utterance=True)
    louder = adapter._segment_gain(_pcm(0.80), new_utterance=False)
    assert louder < first
    assert 0.80 * louder <= 1.0


def test_the_next_utterance_starts_over(adapter) -> None:
    adapter._segment_gain(_pcm(0.10), new_utterance=True)
    assert adapter._segment_gain(_pcm(0.90), new_utterance=True) == pytest.approx(
        0.95 / 0.90, rel=0.05)


def test_silence_is_not_amplified(adapter) -> None:
    """Amplifying a gap would raise the noise floor and, on this robot, feed the
    echo path with hiss."""
    assert adapter._segment_gain(np.zeros(2400, dtype=np.float32),
                                 new_utterance=True) == pytest.approx(1.0)


def test_the_lift_is_capped(adapter, monkeypatch) -> None:
    """A nearly-silent segment must not be multiplied by fifty."""
    monkeypatch.setenv("ROBOT_TTS_MAX_GAIN", "4")
    assert adapter._segment_gain(_pcm(0.001), new_utterance=True) <= 4.0


def test_it_can_be_switched_off(adapter, monkeypatch) -> None:
    monkeypatch.setenv("ROBOT_TTS_NORMALIZE", "false")
    assert adapter._segment_gain(_pcm(0.2), new_utterance=True) == pytest.approx(1.0)


# ── through the real playback path ─────────────────────────────────────────

async def test_a_streamed_segment_reaches_the_speaker_at_a_usable_level(adapter) -> None:
    media = FakeMedia()
    adapter._media = lambda: media  # type: ignore[method-assign]
    await adapter.play_stream_segment(_bytes(0.35), sample_rate=24_000)
    assert media.pushed, "nothing reached the speaker"
    out = float(np.max(np.abs(media.pushed[-1])))
    # 0.95 target, times the 0.8 app volume — what the other path delivers.
    assert out == pytest.approx(0.95 * 0.8, rel=0.1)
    assert out > 0.35 * 0.8, "it must be louder than what came in"


async def test_the_app_volume_still_rules_over_it(adapter) -> None:
    media = FakeMedia()
    adapter._media = lambda: media  # type: ignore[method-assign]
    adapter.set_volume(0.25)
    await adapter.play_stream_segment(_bytes(0.35), sample_rate=24_000)
    out = float(np.max(np.abs(media.pushed[-1])))
    assert out == pytest.approx(0.95 * 0.25, rel=0.1)
