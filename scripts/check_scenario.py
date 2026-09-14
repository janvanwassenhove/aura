#!/usr/bin/env python3
"""U361: validate a presentation scenario before you are standing in front of
a room.

    python scripts/check_scenario.py my-talk.scenario.yaml

The Present panel refuses a bad scenario with one readable sentence (FR-282),
but that is the wrong moment to find out and the wrong machine to fix it on.
This is the same validation, at a desk, with the file open - plus the things
validation cannot know: how many times he speaks, which keywords are armed,
and which slides he appears on.

Exit code 0 when the file would load, 1 when it would not.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for pkg in ("packages/shared-schemas/src",):
    sys.path.insert(0, str(REPO / pkg))

import yaml  # noqa: E402

from shared_schemas.presentation import Scenario  # noqa: E402


def _readable(exc: Exception) -> str:
    """One line a person can act on, rather than a Pydantic dump."""
    from pydantic import ValidationError

    if not isinstance(exc, ValidationError):
        return str(exc)
    out = []
    for err in exc.errors():
        where = ".".join(str(p) for p in err.get("loc", ()) if p != "beats")
        msg = err.get("msg", "").removeprefix("Value error, ")
        out.append(f"{where}: {msg}" if where else msg)
    return "\n  ".join(out)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    path = Path(argv[1])
    if not path.exists():
        print(f"no such file: {path}")
        return 1

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        print(f"that file is not valid YAML:\n  {exc}")
        return 1

    try:
        scenario = Scenario.model_validate(raw)
    except Exception as exc:  # noqa: BLE001 — every failure is worth printing
        print(f"REFUSED - the Present panel would say the same:\n  {_readable(exc)}")
        return 1

    speaks = [b for b in scenario.beats if b.mode in ("speak", "improvise", "chime_in")]
    keywords = [b.trigger_value for b in scenario.beats if b.trigger_kind == "keyword"]
    slides = sorted({b.slide_number for b in scenario.beats
                     if b.slide_number is not None})
    manual = [b.id for b in scenario.beats if b.trigger_kind == "manual"]

    print(f"OK - {scenario.title or '(untitled)'}")
    print(f"  deck            {scenario.pptx or '(none named)'}")
    print(f"  beats           {len(scenario.beats)}")
    print(f"  he speaks       {len(speaks)} time(s)")
    print(f"  you press       {len(manual)} time(s): {', '.join(manual) or '-'}")
    print(f"  armed keywords  {', '.join(keywords) or '-'}")
    print(f"  slide cues      {', '.join(str(n) for n in slides) or '-'}")
    print(f"  overlay starts  {'shown' if scenario.overlay_starts_visible else 'hidden'}")

    # The things that are legal and still worth a second look.
    for beat in scenario.beats:
        if beat.voice:
            print(f"  ! {beat.id}: voice {beat.voice}"
                  f"{f' at {beat.speed}x' if beat.speed else ''}")
        if beat.pause:
            print(f"  ! {beat.id}: waits {beat.pause}s before speaking")
        if beat.mode == "speak" and len(beat.speech_segments()) > 1:
            voices = " then ".join(s.persona or "(the talk's own)"
                                for s in beat.speech_segments())
            print(f"  ! {beat.id}: changes voice mid-line: {voices}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
