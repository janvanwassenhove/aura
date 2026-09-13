"""U353: Windows gets an MSI as well as the .exe, because a managed laptop
refuses the .exe outright.

Reported with a screenshot: *"Windows cannot access the specified device, path,
or file. You may not have the appropriate permissions to access the item."* —
and, beside it, the observation that settles the diagnosis: the Reachy Mini
Control **MSI** reaches its wizard on the same machine, with the same unsigned
warning.

Both files are genuinely unsigned (measured with `Get-AuthenticodeSignature`),
so the signature is not what separates them. The difference is that an MSI is
not an executable: it is data handed to `msiexec.exe`, a Microsoft-signed
binary the policy already trusts, and it lands in `Program Files` — while the
NSIS `.exe` has to be executed itself, from a user-writable directory, which is
the case those policies exist to stop.

Signing (U337/U338) is still worth having and is untouched here; U337's own
entry said it would not necessarily defeat a policy block. This is the other
half.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
DESKTOP = REPO / "apps" / "desktop"
RELEASE = REPO / ".github" / "workflows" / "release.yml"


def _build() -> dict:
    return json.loads((DESKTOP / "package.json").read_text(encoding="utf-8"))["build"]


def _windows_matrix_args() -> str:
    workflow = yaml.safe_load(RELEASE.read_text(encoding="utf-8"))
    for entry in workflow["jobs"]["build"]["strategy"]["matrix"]["include"]:
        if "windows" in entry["os"]:
            return entry["args"]
    raise AssertionError("no windows entry in the build matrix")


# --------------------------------------------------------------------------- #
# what is built
# --------------------------------------------------------------------------- #

def test_windows_builds_both_an_exe_and_an_msi() -> None:
    targets = _build()["win"]["target"]
    assert "nsis" in targets, "the .exe stays — it is the auto-update path"
    assert "msi" in targets, "the MSI is the one a managed laptop will run"


def test_the_msi_installs_for_the_whole_machine() -> None:
    """The entire point. electron-builder defaults BOTH installers to per-user,
    which puts the app in %LOCALAPPDATA% — the user-writable location that the
    default AppLocker rule set exists to deny. The MSI that works on the same
    laptop (Reachy Mini Control) sits in Program Files with a machine-wide
    uninstall entry; this one has to as well, or it changes nothing.
    """
    assert _build()["msi"]["perMachine"] is True


def test_the_msi_asks_before_it_installs() -> None:
    """A per-machine install needs elevation, and a silent one-click MSI that
    triggers a UAC prompt with no explanation is worse than a wizard."""
    assert _build()["msi"]["oneClick"] is False


def test_the_two_installers_do_not_share_a_file_name() -> None:
    """They are published side by side in one release, and the updater picks
    between them by name."""
    nsis = _build()["nsis"]["artifactName"]
    msi = _build()["msi"]["artifactName"]
    assert nsis != msi
    assert msi.endswith(".${ext}") and nsis.endswith(".${ext}")


def test_the_nsis_installer_is_untouched() -> None:
    """Auto-update downloads and runs the .exe, and every existing install is
    an .exe install. Changing it here would break both."""
    nsis = _build()["nsis"]
    assert nsis["artifactName"] == "AURA-${version}-windows-setup.${ext}"
    assert nsis["oneClick"] is False


# --------------------------------------------------------------------------- #
# what is released
# --------------------------------------------------------------------------- #

def test_the_release_actually_builds_the_msi() -> None:
    """`win.target` is ignored when the workflow names its targets on the
    command line — which it does."""
    args = _windows_matrix_args()
    assert "nsis" in args and "msi" in args, args


def test_the_msi_is_published_alongside_the_exe() -> None:
    yml = RELEASE.read_text(encoding="utf-8")
    assert "apps/desktop/dist/*.msi" in yml, "the MSI never leaves the runner"


def test_the_msi_is_offered_for_signing_too() -> None:
    """Whenever the signing route is configured, it must cover both files —
    signing only the .exe would leave the one a work laptop actually runs
    unsigned, which is the exact machine the signing was for."""
    workflow = yaml.safe_load(RELEASE.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["build"]["steps"]
    upload = next(s for s in steps
                  if "unsigned" in str(s.get("name", "")).lower())
    assert ".msi" in str(upload["with"]["path"])


def test_the_build_says_whether_the_msi_is_signed() -> None:
    """U337's rule: "unknown publisher" is otherwise discovered at install
    time, on somebody else's machine, at the worst possible moment."""
    yml = RELEASE.read_text(encoding="utf-8")
    report = yml.split("Say whether the Windows installer")[1]
    assert "*.msi" in report, "the summary reports only the .exe"
