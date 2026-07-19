"""U16: ReachyRobotAdapter — contract tests against a stubbed SDK.

No hardware needed: a fake ``reachy_mini`` module is injected into sys.modules.
The live smoke test lives in test_reachy_live.py (REACHY_LIVE=1).
"""

from __future__ import annotations

import sys
import types

import numpy as np
import pytest

from shared_schemas.robot.models import (
    BehaviorState,
    MotionCommand,
    MotionCue,
    MotionTimeline,
    RobotMode,
)


class FakeMini:
    """Records every SDK call the adapter makes."""

    def __init__(self, **kwargs) -> None:
        self.init_kwargs = kwargs
        self.calls: list[tuple[str, dict]] = []
        self.media_released = False
        self.client = types.SimpleNamespace(disconnect=lambda: self.calls.append(("disconnect", {})))

    def goto_target(self, head=None, antennas=None, duration=0.5, body_yaw=0.0) -> None:
        self.calls.append(("goto_target", {"head": head, "antennas": antennas, "duration": duration}))

    def look_at_world(self, x, y, z, duration=1.0):
        self.calls.append(("look_at_world", {"x": x, "y": y, "z": z}))
        return np.eye(4)

    def wake_up(self) -> None:
        self.calls.append(("wake_up", {}))

    def goto_sleep(self) -> None:
        self.calls.append(("goto_sleep", {}))

    def stop_head_tracking(self) -> None:
        self.calls.append(("stop_head_tracking", {}))

    def start_head_tracking(self) -> None:
        self.calls.append(("start_head_tracking", {}))

    def set_automatic_body_yaw(self, enabled: bool) -> None:
        self.calls.append(("set_automatic_body_yaw", {"enabled": enabled}))

    def set_target_body_yaw(self, yaw: float) -> None:
        self.calls.append(("set_target_body_yaw", {"yaw": yaw}))

    def release_media(self) -> None:
        self.media_released = True


@pytest.fixture()
def adapter(monkeypatch):
    """A connected ReachyRobotAdapter backed by FakeMini."""
    created: list[FakeMini] = []

    fake_module = types.ModuleType("reachy_mini")

    def _ctor(**kwargs):
        mini = FakeMini(**kwargs)
        created.append(mini)
        return mini

    fake_module.ReachyMini = _ctor
    monkeypatch.setitem(sys.modules, "reachy_mini", fake_module)

    from robot_runtime.adapters.reachy import ReachyRobotAdapter

    a = ReachyRobotAdapter(host="stub-host", connection_mode="network", media_backend="no_media")
    a._created = created  # type: ignore[attr-defined]
    return a


def _moves(mini: FakeMini) -> list[str]:
    return [name for name, _ in mini.calls if name != "disconnect"]


async def test_connect_reports_online_status(adapter) -> None:
    await adapter.connect()
    state = await adapter.get_status()
    assert state.connected is True
    assert state.mode == RobotMode.ONLINE
    assert state.adapter_name == "reachy"
    mini = adapter._created[0]
    assert mini.init_kwargs["host"] == "stub-host"
    assert mini.init_kwargs["connection_mode"] == "network"


async def test_disconnect_reports_offline(adapter) -> None:
    await adapter.connect()
    await adapter.disconnect()
    state = await adapter.get_status()
    assert state.connected is False
    assert state.mode == RobotMode.OFFLINE


async def test_set_state_round_trips(adapter) -> None:
    await adapter.connect()
    await adapter.set_state(RobotMode.DEGRADED, BehaviorState.SPEAKING)
    state = await adapter.get_status()
    assert state.mode == RobotMode.DEGRADED
    assert state.behavior_state == BehaviorState.SPEAKING


async def test_nod_pitches_head_and_returns_to_neutral(adapter) -> None:
    await adapter.connect()
    await adapter.execute_motion(MotionCommand(motion_id="nod", amplitude=0.5, direction=None))
    mini = adapter._created[0]
    gotos = [kw for name, kw in mini.calls if name == "goto_target"]
    assert len(gotos) == 2
    # first leg pitches (rotation about x → element [1][2] non-zero)
    assert abs(gotos[0]["head"][1][2]) > 0
    # last leg returns to neutral
    assert np.allclose(gotos[-1]["head"], np.eye(4))


async def test_wave_wiggles_antennas_and_recenters(adapter) -> None:
    await adapter.connect()
    await adapter.execute_motion(MotionCommand(motion_id="wave", amplitude=1.0, direction=None))
    mini = adapter._created[0]
    antenna_moves = [kw["antennas"] for name, kw in mini.calls if name == "goto_target"]
    assert len(antenna_moves) == 3
    assert antenna_moves[-1] == [0.0, 0.0]


async def test_point_uses_look_at_world(adapter) -> None:
    await adapter.connect()
    await adapter.execute_motion(MotionCommand(motion_id="point", direction=None))
    assert "look_at_world" in _moves(adapter._created[0])


async def test_wake_up_and_sleep_map_to_sdk_emotes(adapter) -> None:
    await adapter.connect()
    await adapter.execute_motion(MotionCommand(motion_id="wake_up", direction=None))
    await adapter.execute_motion(MotionCommand(motion_id="sleep", direction=None))
    moves = _moves(adapter._created[0])
    # U102: back to the SDK emotes — wake_up() and goto_sleep().
    assert "wake_up" in moves and "goto_sleep" in moves
    # sleep must hard-stop head-tracking + body-yaw BEFORE goto_sleep, so the
    # tracking loop can't pull the head back out of the pose.
    assert moves.index("stop_head_tracking") < moves.index("goto_sleep")
    assert moves.index("set_automatic_body_yaw") < moves.index("goto_sleep")


async def test_status_reports_tracking(adapter, monkeypatch) -> None:
    """U126: follow-me state is visible in the status."""
    monkeypatch.setenv("HEAD_TRACKING", "false")  # don't auto-enable on connect
    await adapter.connect()
    assert (await adapter.get_status()).tracking is False
    await adapter.set_tracking(True)
    assert (await adapter.get_status()).tracking is True


async def test_tracking_watchdog_reasserts(adapter, monkeypatch) -> None:
    """U126: the watchdog re-calls start_head_tracking while follow-me is on,
    so a silently-dropped tracker self-heals."""
    monkeypatch.setenv("HEAD_TRACKING", "false")
    monkeypatch.setenv("TRACKING_WATCHDOG_S", "0.02")
    await adapter.connect()
    await adapter.set_tracking(True)
    mini = adapter._created[0]
    before = [n for n, _ in mini.calls].count("start_head_tracking")
    import asyncio
    await asyncio.sleep(0.07)  # let the watchdog fire a couple of times
    after = [n for n, _ in mini.calls].count("start_head_tracking")
    assert after > before
    # When follow-me is OFF the watchdog must NOT re-assert it.
    await adapter.set_tracking(False)
    idle = [n for n, _ in mini.calls].count("start_head_tracking")
    await asyncio.sleep(0.07)
    assert [n for n, _ in mini.calls].count("start_head_tracking") == idle


async def test_wake_up_resumes_tracking_after_sleep(adapter) -> None:
    """U116: sleep stops head tracking; the wake_up MOTION must restart it —
    otherwise the Sleep→Wake quick actions leave follow-me dead."""
    await adapter.connect()
    await adapter.set_tracking(True)
    await adapter.execute_motion(MotionCommand(motion_id="sleep", direction=None))
    assert adapter._tracking_on is False
    mini = adapter._created[0]
    before = len(mini.calls)
    await adapter.execute_motion(MotionCommand(motion_id="wake_up", direction=None))
    moves = [n for n, _ in mini.calls[before:]]
    assert "start_head_tracking" in moves
    assert adapter._tracking_on is True


async def test_mood_gestures_do_not_pause_tracking(adapter) -> None:
    """U116: mood poses are follow-gestures — the robot keeps its eyes on you
    while expressing, instead of pausing/resuming tracking every reply."""
    await adapter.connect()
    await adapter.set_tracking(True)
    mini = adapter._created[0]
    before = len(mini.calls)
    await adapter.execute_motion(MotionCommand(motion_id="mood_happy", direction=None))
    moves = [n for n, _ in mini.calls[before:]]
    assert "stop_head_tracking" not in moves


async def test_mood_motions_move_head_and_antennas(adapter) -> None:
    """U111: each mood pose is a real goto_target move (not a crash/fallback)."""
    await adapter.connect()
    for mood in ("mood_happy", "mood_excited", "mood_apologetic", "mood_curious", "mood_attentive"):
        mini = adapter._created[0]
        before = len(mini.calls)
        await adapter.execute_motion(MotionCommand(motion_id=mood, direction=None))
        moves = [n for n, _ in mini.calls[before:]]
        assert "goto_target" in moves, f"{mood} did not move"


async def test_unknown_motion_falls_back_to_gentle_nod(adapter) -> None:
    await adapter.connect()
    await adapter.execute_motion(MotionCommand(motion_id="does-not-exist", direction=None))
    mini = adapter._created[0]
    assert _moves(mini)  # did SOMETHING (graceful) rather than raising


async def test_timeline_executes_cues_in_order(adapter) -> None:
    await adapter.connect()
    timeline = MotionTimeline(cues=[
        MotionCue(offset_ms=0, motion_id="wake_up"),
        MotionCue(offset_ms=10, motion_id="sleep"),
    ])
    await adapter.execute_timeline(timeline)
    moves = _moves(adapter._created[0])
    assert moves.index("wake_up") < moves.index("goto_sleep")


async def test_motion_before_connect_raises(adapter) -> None:
    with pytest.raises(RuntimeError):
        await adapter.execute_motion(MotionCommand(motion_id="nod", direction=None))


async def test_no_media_degrades_gracefully(adapter) -> None:
    await adapter.connect()
    # speak without audio payload: logs, no crash
    await adapter.speak("hello")
    # play_audio: skipped with a warning
    await adapter.play_audio(b"\x00\x00" * 100)
    # capture: silence of the right length (16kHz 16-bit mono)
    pcm = await adapter.capture_audio(duration_s=0.5)
    assert len(pcm) == int(0.5 * 16_000) * 2
    # camera: explicit error (recognition must know there is no frame)
    with pytest.raises(RuntimeError):
        await adapter.get_camera_frame()


async def test_speed_scales_motion_duration(adapter) -> None:
    await adapter.connect()
    await adapter.execute_motion(MotionCommand(motion_id="nod", speed=2.0, direction=None))
    await adapter.execute_motion(MotionCommand(motion_id="nod", speed=0.5, direction=None))
    mini = adapter._created[0]
    durations = [kw["duration"] for name, kw in mini.calls if name == "goto_target"]
    assert durations[0] < durations[2]  # fast nod's legs are shorter than slow nod's


# ------------------------------------------------------------------
# U137: manual quick actions pause follow-me; dance moves exist
# ------------------------------------------------------------------

async def test_manual_motion_pauses_tracking(adapter) -> None:
    """A manual quick action must pause head tracking even for a gesture that
    normally keeps it (otherwise the daemon pulls the head back mid-move)."""
    await adapter.connect()
    await adapter.set_tracking(True)
    mini = adapter._created[0]

    before = len(mini.calls)
    await adapter.execute_motion(MotionCommand(motion_id="nod", direction=None))
    auto_moves = [n for n, _ in mini.calls[before:]]
    assert "stop_head_tracking" not in auto_moves      # reply gesture keeps eye contact

    before = len(mini.calls)
    await adapter.execute_motion(MotionCommand(motion_id="nod", direction=None, manual=True))
    manual_moves = [n for n, _ in mini.calls[before:]]
    assert "stop_head_tracking" in manual_moves        # manual → fully visible
    assert "start_head_tracking" in manual_moves       # and resumed after


async def test_dance_moves_animate(adapter) -> None:
    await adapter.connect()
    for motion in ("dance", "bop", "sway"):
        mini = adapter._created[0]
        before = len(mini.calls)
        await adapter.execute_motion(MotionCommand(motion_id=motion, direction=None, manual=True))
        moves = [n for n, _ in mini.calls[before:]]
        # A dance is a repeating routine, not a single pose.
        assert moves.count("goto_target") >= 4, f"{motion} barely moved: {moves}"


async def test_spin_uses_body_yaw_and_restores(adapter) -> None:
    await adapter.connect()
    mini = adapter._created[0]
    before = len(mini.calls)
    await adapter.execute_motion(MotionCommand(motion_id="spin", direction=None, manual=True))
    moves = [n for n, _ in mini.calls[before:]]
    assert "set_target_body_yaw" in moves          # the real body twirl
    assert moves.count("set_target_body_yaw") >= 3  # out, back, recentre


# ------------------------------------------------------------------
# U138: dance music — a synthesized groove under the moves
# ------------------------------------------------------------------

async def test_groove_synth_is_audible_and_bounded(adapter) -> None:
    await adapter.connect()
    audio = adapter._synth_groove(beats=4, bpm=120.0, rate=8000)
    beat_s = 60.0 / 120.0
    assert len(audio) >= int(4 * beat_s * 8000)     # covers the requested bars
    assert float(abs(audio).max()) <= 1.0            # never clips the DAC
    assert float(abs(audio).max()) > 0.1             # and is actually audible


async def test_dance_plays_a_groove(adapter, monkeypatch) -> None:
    """The dance moves start music; DANCE_SOUND=false keeps the disco silent."""
    played: list[int] = []
    monkeypatch.setattr(type(adapter), "_play_groove",
                        lambda self, beats, bpm: played.append(beats))
    await adapter.connect()
    for motion in ("dance", "bop", "sway", "spin"):
        await adapter.execute_motion(MotionCommand(motion_id=motion, direction=None, manual=True))
    assert len(played) == 4                          # every dance move grooves


async def test_dance_sound_can_be_disabled(adapter, monkeypatch) -> None:
    monkeypatch.setenv("DANCE_SOUND", "false")
    await adapter.connect()
    # _play_groove returns before touching the media backend.
    adapter._play_groove(beats=4, bpm=120.0)
    assert adapter._groove_files == []


async def test_dance_uses_torso_and_recentres(adapter) -> None:
    """U139: the full dance swings the TORSO too, and always lands square."""
    await adapter.connect()
    mini = adapter._created[0]
    before = len(mini.calls)
    await adapter.execute_motion(MotionCommand(motion_id="dance", direction=None, manual=True))
    calls = mini.calls[before:]
    yaws = [kw["yaw"] for name, kw in calls if name == "set_target_body_yaw"]
    assert len(yaws) >= 6                      # torso swings throughout, not once
    assert max(yaws) > 0 and min(yaws) < 0      # both directions
    assert yaws[-1] == 0.0                      # lands facing forward
    # And it still moves head/antennas — a whole-body routine.
    assert sum(1 for n, _ in calls if n == "goto_target") >= 10


async def test_dance_restores_body_follow(adapter) -> None:
    """Body-follow was on before the dance → it must be on again after."""
    await adapter.connect()
    await adapter.set_body_follow(True)
    mini = adapter._created[0]
    before = len(mini.calls)
    await adapter.execute_motion(MotionCommand(motion_id="dance", direction=None, manual=True))
    yaw_toggles = [kw["enabled"] for n, kw in mini.calls[before:]
                   if n == "set_automatic_body_yaw"]
    assert yaw_toggles and yaw_toggles[0] is False   # paused during the routine
    assert yaw_toggles[-1] is True                   # restored afterwards


async def test_listening_and_thinking_cues(adapter) -> None:
    """U147: attentive-listening cues animate and keep tracking (follow gesture)."""
    await adapter.connect()
    await adapter.set_tracking(True)
    mini = adapter._created[0]
    for motion in ("listening", "thinking"):
        before = len(mini.calls)
        await adapter.execute_motion(MotionCommand(motion_id=motion, direction=None))
        moves = [n for n, _ in mini.calls[before:]]
        assert "goto_target" in moves               # it actually moves
        assert "stop_head_tracking" not in moves     # keeps eyes on the speaker


async def test_capture_endpoints_on_trailing_silence(adapter, monkeypatch) -> None:
    """U148: capture stops shortly after speech ends instead of recording the
    whole window. Fake media yields ~0.5 s of 'speech' then silence."""
    monkeypatch.setenv("VOICE_ENDPOINTING", "true")
    monkeypatch.setenv("ENDPOINT_MIN_SPEECH_S", "0.3")
    monkeypatch.setenv("ENDPOINT_SILENCE_S", "0.4")
    monkeypatch.setenv("ENDPOINT_VAD_GATE", "0.02")
    await adapter.connect()

    rate = 16_000
    frame = rate // 20  # 50 ms frames
    speech = (np.ones(frame, dtype=np.float32) * 0.2)     # above the gate
    silence = (np.zeros(frame, dtype=np.float32))         # below the gate
    plan = [speech] * 12 + [silence] * 40                 # 0.6 s speech, then quiet

    class _FakeMedia:
        def __init__(self):
            self.i = 0
            self.recording = False
        def start_recording(self): self.recording = True
        def stop_recording(self): self.recording = False
        def get_input_audio_samplerate(self): return rate
        def get_audio_sample(self):
            if self.i < len(plan):
                s = plan[self.i]; self.i += 1; return s
            return silence

    fake = _FakeMedia()
    monkeypatch.setattr(adapter, "_media", lambda: fake)
    pcm = await adapter.capture_audio(duration_s=5.0)
    got_s = len(pcm) / 2 / 16_000
    # Speech (0.6 s) + hang (0.4 s) ≈ ~1 s, well under the 5 s max window.
    assert got_s < 2.0, f"endpointing did not cut early: {got_s:.2f}s"
    assert got_s > 0.5
