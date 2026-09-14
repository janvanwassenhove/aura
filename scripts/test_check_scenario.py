"""U361: the pre-flight check for a scenario.

The Present panel already refuses a bad file with one readable sentence — but
that is on a stage, on the wrong machine, at the worst moment. This is the same
validation at a desk, and it has to be trustworthy in both directions: a file
that would load must pass, and one that would not must fail with the reason.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "check_scenario.py"
GOOD = REPO / "docs" / "demo" / "robot-junior-dev.scenario.yaml"


def _run(path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), str(path)],
                          capture_output=True, text=True, check=False)


def test_the_shipped_scenario_passes() -> None:
    result = _run(GOOD)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout


def test_it_reports_what_the_talk_will_actually_do() -> None:
    """A checker that only says "valid" leaves you no wiser than before."""
    out = _run(GOOD).stdout
    for line in ("beats", "he speaks", "armed keywords", "slide cues", "overlay starts"):
        assert line in out, out


def test_a_misspelt_field_is_refused_by_name(tmp_path) -> None:
    """The whole reason this exists: `voise: onyx` used to be dropped in
    silence, and the gag it was written for came out in one voice (U360)."""
    bad = tmp_path / "bad.yaml"
    bad.write_text('title: T\nbeats:\n  - id: oops\n    mode: speak\n'
                   '    text: "x"\n    voise: onyx\n', encoding="utf-8")
    result = _run(bad)
    assert result.returncode == 1
    assert "voise" in result.stdout


def test_a_broken_beat_names_the_beat(tmp_path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text('title: T\nbeats:\n  - id: quiet\n    mode: speak\n', encoding="utf-8")
    result = _run(bad)
    assert result.returncode == 1
    assert "quiet" in result.stdout


def test_a_file_that_is_not_yaml_says_so(tmp_path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("title: [unclosed\n", encoding="utf-8")
    result = _run(bad)
    assert result.returncode == 1
    assert "YAML" in result.stdout


def test_a_missing_file_is_not_a_traceback(tmp_path) -> None:
    result = _run(tmp_path / "nope.yaml")
    assert result.returncode == 1
    assert "no such file" in result.stdout
    assert "Traceback" not in result.stderr


def test_it_flags_the_things_worth_a_second_look(tmp_path) -> None:
    """Legal, and still worth reading twice before a talk."""
    sc = tmp_path / "s.yaml"
    sc.write_text(
        'title: T\nbeats:\n'
        '  - id: fanfare\n    mode: speak\n    text: "Ta."\n    voice: onyx\n    speed: 0.85\n'
        '  - id: setup\n    mode: speak\n    text: "Oh."\n    pause: 7.0\n',
        encoding="utf-8")
    out = _run(sc).stdout
    assert "voice onyx" in out and "0.85" in out
    assert "waits 7.0s" in out
