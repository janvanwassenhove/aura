"""U402: face recognition must not lose OpenCV to the gesture extra.

Reported with a screenshot of the People screen: *"Face recognition isn't
installed on this machine"* — on a machine started with start-aura.bat, which
installs the recognition extra.

It was installed. `insightface` was there and imported nothing, because
`cv2` was gone — while `opencv_python-5.0.0.93.dist-info` still said OpenCV
was installed. Two distributions write the same `cv2/` directory: the
recognition extra pulls `opencv-python` through insightface, and the gestures
extra pulls `opencv-contrib-python` through mediapipe. With both installed
once, a later sync without gestures (start-aura.bat does not ask for it)
removes the contrib package — and its files, which are the shared `cv2/`.
uv then sees opencv-python's record, reports "no changes", and never puts it
back. Reproduced on a scratch environment exactly like that.

So only one OpenCV is ever installed: the contrib build, which the gestures
extra needs anyway and which contains everything insightface uses.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
NEVER = "sys_platform == 'never'"


def _installable_requirements() -> set[str]:
    """Every package a locked package can actually pull in — a requirement
    whose marker can never be true (the override's) installs nothing."""
    lock = (REPO / "uv.lock").read_text(encoding="utf-8")
    names = set()
    for m in re.finditer(r'\{ name = "([^"]+)"([^}]*)\}', lock):
        if NEVER not in m.group(2):
            names.add(m.group(1))
    return names


def test_only_one_opencv_is_ever_installed() -> None:
    names = {n for n in _installable_requirements() if n.startswith("opencv")}
    assert names == {"opencv-contrib-python"}, (
        f"two OpenCV builds share cv2/ and delete it from each other: {sorted(names)}")


def test_recognition_asks_for_opencv_itself() -> None:
    """Not left to whichever package happens to bring it."""
    project = tomllib.loads((REPO / "apps/aura-brain/pyproject.toml").read_text(encoding="utf-8"))
    recognition = project["project"]["optional-dependencies"]["recognition"]
    assert any(d.startswith("opencv-contrib-python") for d in recognition)
