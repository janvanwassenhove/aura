"""U399: the volume slider is his volume — whatever he plays.

Reported, in Stand with emotion sounds (translated): *"I have the impression
the volume slider has no effect"*.

It had none that could be heard. The slider was a digital gain on the speech
the robot runtime itself plays, and the runtime set the speaker's hardware
mixer to 100 % on every connect (U82). Two things went past it entirely:

* his emotions — Pollen's recordings, played by the daemon (ADR-016), at the
  hardware level, so always at full volume;
* his words, which that evening went through the laptop (U364).

The slider now sets the robot's own mixer, the one the daemon plays through
as well — so speech, emotions and chimes follow it alike — at the same
decibels the digital gain gave, so 18 % sounds as 18 % did. The digital gain
steps aside while the mixer has it, and takes over again when it cannot be
set (no robot connected, no `amixer`), so a test run never touches anyone's
speaker. The laptop's half is in the console's tests.
"""

from __future__ import annotations

import sys
import types

import pytest


class FakeMini:
    def __init__(self, **kwargs) -> None:
        self.client = types.SimpleNamespace(disconnect=lambda: None)

    def goto_target(self, **kw) -> None: ...

    def start_head_tracking(self, weight: float = 1.0) -> None: ...

    def stop_head_tracking(self) -> None: ...

    def get_tracked_face(self, wait: bool = True, timeout: float = 5.0):
        return types.SimpleNamespace(detected=False, ts=1.0)

    def set_automatic_body_yaw(self, enabled: bool) -> None: ...

    def set_target_body_yaw(self, yaw: float) -> None: ...

    def wake_up(self) -> None: ...

    def release_media(self) -> None: ...

    def acquire_media(self) -> None: ...


@pytest.fixture()
def adapter(monkeypatch):
    fake_module = types.ModuleType("reachy_mini")
    fake_module.ReachyMini = lambda **kw: FakeMini(**kw)
    monkeypatch.setitem(sys.modules, "reachy_mini", fake_module)
    monkeypatch.setenv("HEAD_TRACKING", "false")
    from robot_runtime.adapters.reachy import ReachyRobotAdapter

    a = ReachyRobotAdapter(host="stub-host", connection_mode="network", media_backend="no_media")
    a.mixer_calls = []                                   # type: ignore[attr-defined]

    def mixer(args: list[str]) -> bool:
        a.mixer_calls.append(args)                      # type: ignore[attr-defined]
        return a.mixer_ok                                # type: ignore[attr-defined]
    a.mixer_ok = True                                    # type: ignore[attr-defined]
    a._amixer = mixer                                    # type: ignore[method-assign]
    return a


async def test_the_slider_sets_the_speakers_own_volume(adapter) -> None:
    await adapter.connect()
    adapter.mixer_calls.clear()
    assert adapter.set_volume(0.18) == pytest.approx(0.18)
    assert adapter.mixer_calls == [["sset", "PCM,0", "--", "-14.9dB", "unmute"]]


async def test_the_same_decibels_the_digital_gain_gave(adapter) -> None:
    """20·log10(level): 50 % is -6 dB, as it was — not the mixer's own
    percentage, where 50 % is -30 dB and the robot all but disappears."""
    await adapter.connect()
    adapter.mixer_calls.clear()
    adapter.set_volume(0.5)
    adapter.set_volume(1.0)
    assert [c[3] for c in adapter.mixer_calls] == ["-6.0dB", "0.0dB"]


async def test_zero_is_silence(adapter) -> None:
    await adapter.connect()
    adapter.mixer_calls.clear()
    adapter.set_volume(0.0)
    assert adapter.mixer_calls[-1][-1] == "mute"


async def test_the_digital_gain_steps_aside_while_the_mixer_has_it(adapter) -> None:
    """Otherwise 50 % would be -6 dB twice over."""
    await adapter.connect()
    adapter.set_volume(0.5)
    assert adapter._digital_gain() == pytest.approx(1.0)


async def test_without_the_mixer_the_digital_gain_does_it(adapter) -> None:
    await adapter.connect()
    adapter.mixer_ok = False
    adapter.set_volume(0.25)
    assert adapter._digital_gain() == pytest.approx(0.25)


async def test_not_connected_it_touches_no_mixer(adapter) -> None:
    """A test run, or a laptop running the runtime, must never turn anyone's
    speaker up or down."""
    adapter.set_volume(0.4)
    assert adapter.mixer_calls == []
    assert adapter._digital_gain() == pytest.approx(0.4)


async def test_connecting_applies_his_level_not_full_volume(adapter, monkeypatch) -> None:
    """U82 set the mixer to 100 % on every connect, which is what made the
    daemon's sounds ignore the slider."""
    adapter.set_volume(0.3)
    await adapter.connect()
    assert ["sset", "PCM,0", "--", "-10.5dB", "unmute"] in adapter.mixer_calls
    assert not any("100%" in c for c in adapter.mixer_calls)
    assert adapter._digital_gain() == pytest.approx(1.0)
