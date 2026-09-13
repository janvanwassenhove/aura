"""U337: the Windows installer is signed when there is a certificate, and says
so when there is not.

Reported as: "code signing moet toegevoegd te worden zodat ik ook kan
installeren op werk pc en niet langer exceptie krijg". The build had no signing
configuration at all, so every installer arrived as *unknown publisher* —
SmartScreen warns a private user and a managed work PC refuses outright.

Signing itself cannot be tested here: it needs a certificate, which is bought
and identity-checked, not committed. What CAN be checked is the wiring, which
is the part that rots silently — a `sign` hook that stops being referenced
produces a perfectly successful build that is quietly unsigned again, and
nobody finds out until someone tries to install it somewhere strict.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DESKTOP = REPO / "apps" / "desktop"
RELEASE = REPO / ".github" / "workflows" / "release.yml"


def _build_config() -> dict:
    return json.loads((DESKTOP / "package.json").read_text(encoding="utf-8"))["build"]


def test_the_windows_build_runs_the_signing_hook() -> None:
    win = _build_config()["win"]
    assert win.get("sign") == "./sign.cjs", win
    assert (DESKTOP / "sign.cjs").exists()


def test_an_unsigned_build_still_succeeds() -> None:
    """A fork, a pull request and a local `npm run dist` have no secrets. They
    must still produce a working installer — the hook returns instead of
    raising — or the whole release stops the first time a secret is missing."""
    hook = (DESKTOP / "sign.cjs").read_text(encoding="utf-8")
    assert "UNSIGNED" in hook, "an unsigned build must say so"
    assert "no signing credentials configured" in hook


def test_the_private_key_never_outlives_the_signature() -> None:
    """A PFX written to a runner's disk and left there is a leaked key: build
    workspaces are cached and restored."""
    hook = (DESKTOP / "sign.cjs").read_text(encoding="utf-8")
    assert "finally" in hook and "rmSync(pfxFile" in hook


def test_the_release_hands_the_credentials_to_the_build() -> None:
    yml = RELEASE.read_text(encoding="utf-8")
    for secret in ("AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_TENANT_ID",
                   "TRUSTED_SIGNING_ENDPOINT", "WINDOWS_PFX_BASE64"):
        assert secret in yml, f"{secret} never reaches the build"


def test_the_release_reports_whether_it_signed_anything() -> None:
    """"Unknown publisher" is otherwise discovered at install time, on somebody
    else's machine, at the worst possible moment."""
    yml = RELEASE.read_text(encoding="utf-8")
    assert "Get-AuthenticodeSignature" in yml
    assert "GITHUB_STEP_SUMMARY" in yml
