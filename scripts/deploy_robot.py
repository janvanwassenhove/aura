#!/usr/bin/env python
"""Deploy robot-runtime to the Pi — U240.

    python scripts/deploy_robot.py            # deploy + verify
    python scripts/deploy_robot.py --check    # only say whether it is in step
    python scripts/deploy_robot.py --rollback # back to the recorded point

Why this exists: the Pi drifted 74 commits behind the laptop because deploying
was a sequence somebody had to remember. Every step below was learned by
getting it wrong once.

The two that will bite you if you improvise:

  * `uv sync --package robot-runtime` PRUNES the environment and removes the
    reachy-mini SDK. Restart at that moment and the robot goes offline. The
    extra is not optional on real hardware — hence --extra reachy, always.

  * The Pi's git history was rewritten (privacy filter-repo) and shares no
    ancestry with this repo, so a plain `git pull` cannot work. Fetch a bundle
    into a ref and hard-reset onto it.

Nothing here is clever; it is just written down, which is the whole point.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPO = Path(__file__).resolve().parents[1]
HOST = "pollen@reachy-mini.local"
KEY = Path.home() / ".ssh" / "reachy"
REMOTE_REPO = "~/aura"
SERVICE = "aura-robot-runtime"
ROBOT_URL = "http://reachy-mini.local:8001"
ROLLBACK_FILE = "~/aura-rollback.sha"


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def ssh(command: str, timeout: int = 900) -> subprocess.CompletedProcess:
    return run(["ssh", "-i", str(KEY), "-o", "ConnectTimeout=10", HOST, command], timeout=timeout)


def say(step: str, detail: str = "") -> None:
    print(f"  {step:<28} {detail}")


def robot_build() -> dict:
    """Ask the robot what it is running. Needs the shared secret if one is set."""
    secret = ""
    env_file = Path.home() / "AppData" / "Roaming" / "aura-desktop" / ".env"
    if not env_file.exists():
        env_file = REPO / "infra" / "dev" / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("ROBOT_SHARED_SECRET="):
                secret = line.split("=", 1)[1].strip()
    req = Request(f"{ROBOT_URL}/health")
    if secret:
        req.add_header("X-AURA-Secret", secret)
    try:
        with urlopen(req, timeout=10) as resp:      # noqa: S310 — fixed local URL
            return json.loads(resp.read()).get("build") or {}
    except (HTTPError, URLError, OSError, ValueError):
        return {}


def local_commit() -> str:
    return run(["git", "rev-parse", "HEAD"], cwd=REPO).stdout.strip()


def check() -> int:
    here = local_commit()
    there = robot_build()
    if not there:
        print("robot: cannot say (no build in /health — runtime older than U240, or unreachable)")
        print(f"here : {here[:7]}")
        return 2
    if there.get("commit") == here:
        print(f"in step — both on {here[:7]}")
        return 0
    print(f"robot: {there.get('commit_short')}  ({there.get('committed_at')})")
    print(f"here : {here[:7]}")
    print("\nBEHIND — run: python scripts/deploy_robot.py")
    return 1


def deploy() -> int:
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=REPO).stdout.strip()
    dirty = run(["git", "status", "--porcelain"], cwd=REPO).stdout.strip()
    if dirty:
        print("refusing: the working tree has uncommitted changes.")
        print("Deploy what is committed, or the robot runs code that exists nowhere else.")
        return 1

    print(f"deploying {branch} @ {local_commit()[:7]} to {HOST}")

    probe = ssh("echo ok")
    if probe.returncode != 0:
        print(f"cannot reach the robot over ssh: {probe.stderr.strip()}")
        return 1
    say("ssh", "ok")

    # A rollback point BEFORE anything changes.
    ssh(f"cd {REMOTE_REPO} && git rev-parse HEAD > {ROLLBACK_FILE}")
    previous = ssh(f"cat {ROLLBACK_FILE}").stdout.strip()
    say("rollback point", previous[:7])

    with tempfile.TemporaryDirectory() as tmp:
        bundle = Path(tmp) / "aura-deploy.bundle"
        made = run(["git", "bundle", "create", str(bundle), branch], cwd=REPO)
        if made.returncode != 0:
            print(f"bundle failed: {made.stderr.strip()}")
            return 1
        size_mb = bundle.stat().st_size / 1e6
        say("bundle", f"{size_mb:.1f} MB")
        sent = run(["scp", "-i", str(KEY), str(bundle), f"{HOST}:~/aura-deploy.bundle"], timeout=1800)
        if sent.returncode != 0:
            print(f"transfer failed: {sent.stderr.strip()}")
            return 1
        say("transferred")

    steps = [
        ("fetch", f"cd {REMOTE_REPO} && git fetch ~/aura-deploy.bundle {branch}:deployed"),
        ("checkout", f"cd {REMOTE_REPO} && git reset --hard deployed"),
        # --extra reachy is load-bearing: without it uv REMOVES the SDK and the
        # next restart takes the robot offline.
        ("dependencies", f"cd {REMOTE_REPO} && ~/.local/bin/uv sync --package robot-runtime --extra reachy"),
    ]
    for name, cmd in steps:
        result = ssh(cmd, timeout=1800)
        if result.returncode != 0:
            print(f"\n{name} failed:\n{result.stderr.strip()[:800]}")
            print(f"\nnothing has been restarted; the robot is still running {previous[:7]}")
            return 1
        say(name, "ok")

    # Prove the SDK survived BEFORE restarting — this is the one that hurts.
    sdk = ssh(f"cd {REMOTE_REPO} && ~/.local/bin/uv run --package robot-runtime "
              f"python -c 'import reachy_mini; print(\"ok\")'")
    if "ok" not in sdk.stdout:
        print("\nthe reachy SDK is NOT importable after the sync — refusing to restart.")
        print("The robot is still running its old process. Re-run with --extra reachy,")
        print(f"or roll back: python {Path(__file__).name} --rollback")
        return 1
    say("reachy sdk", "importable")

    restarted = ssh(f"sudo systemctl restart {SERVICE} && sleep 8 && systemctl is-active {SERVICE}")
    if "active" not in restarted.stdout:
        print(f"\nservice did not come back: {restarted.stdout.strip()} {restarted.stderr.strip()}")
        return 1
    say("service", "active")

    build = robot_build()
    if build.get("commit") == local_commit():
        say("verified", f"robot now on {build.get('commit_short')}")
    else:
        print(f"\ndeployed, but the robot reports {build.get('commit_short') or 'nothing'} "
              f"rather than {local_commit()[:7]}")
        return 1

    ssh("rm -f ~/aura-deploy.bundle")
    print(f"\ndone. rollback point kept at {ROLLBACK_FILE} ({previous[:7]})")
    return 0


def enable_auto_update(enable: bool) -> int:
    """U241: install (or remove) the timer that lets the robot follow releases.

    Opt-in on purpose. Something that restarts a moving machine in someone's
    house without being asked should be a decision, not a default.
    """
    if not enable:
        ssh("sudo systemctl disable --now aura-robot-update.timer 2>/dev/null; "
            "sudo rm -f /etc/systemd/system/aura-robot-update.{service,timer}; "
            "sudo systemctl daemon-reload")
        print("auto-update disabled and removed")
        return 0

    for unit in ("aura-robot-update.service", "aura-robot-update.timer"):
        src = REPO / "infra" / "systemd" / unit
        sent = run(["scp", "-i", str(KEY), str(src), f"{HOST}:/tmp/{unit}"], timeout=300)
        if sent.returncode != 0:
            print(f"could not copy {unit}: {sent.stderr.strip()}")
            return 1
        moved = ssh(f"sudo mv /tmp/{unit} /etc/systemd/system/{unit}")
        if moved.returncode != 0:
            print(f"could not install {unit}: {moved.stderr.strip()}")
            return 1
        say(unit, "installed")

    # The updater lives OUTSIDE the checkout it updates: `git reset --hard`
    # replaces files while bash is still reading the running script, and a robot
    # older than the script would not have it at all. Copy it to a stable path.
    src = REPO / "scripts" / "robot_selfupdate.sh"
    # LF, whatever this machine checked out. A shell script with CRLF fails
    # on the Pi as "env: 'bash\r': No such file or directory" — a message that
    # names the wrong thing entirely. .gitattributes pins it too; this is the
    # belt to that pair of braces, because scp copies bytes, not intentions.
    with tempfile.TemporaryDirectory() as tmp:
        staged = Path(tmp) / "aura-robot-selfupdate"
        text = src.read_text(encoding="utf-8")
        staged.write_bytes(text.replace("\r\n", "\n").encode("utf-8"))
        sent = run(["scp", "-i", str(KEY), str(staged),
                    f"{HOST}:/tmp/aura-robot-selfupdate"], timeout=300)
    if sent.returncode != 0:
        print(f"could not copy the updater: {sent.stderr.strip()}")
        return 1
    installed = ssh("sudo install -m 0755 /tmp/aura-robot-selfupdate "
                    "/usr/local/bin/aura-robot-selfupdate && rm -f /tmp/aura-robot-selfupdate")
    if installed.returncode != 0:
        print(f"could not install the updater: {installed.stderr.strip()}")
        return 1
    say("updater", "/usr/local/bin/aura-robot-selfupdate")

    result = ssh("sudo systemctl daemon-reload && "
                 "sudo systemctl enable --now aura-robot-update.timer && "
                 "systemctl is-active aura-robot-update.timer")
    if "active" not in result.stdout:
        print(f"timer did not start: {result.stdout.strip()} {result.stderr.strip()}")
        return 1
    say("timer", "active")
    nxt = ssh("systemctl list-timers aura-robot-update.timer --no-pager | sed -n 2p")
    print()
    print(nxt.stdout.strip())
    print()
    print("the robot now follows release tags. journalctl -u aura-robot-update to watch it.")
    return 0


def rollback() -> int:
    sha = ssh(f"cat {ROLLBACK_FILE}").stdout.strip()
    if not sha:
        print(f"no rollback point on the robot ({ROLLBACK_FILE} is empty or missing)")
        return 1
    print(f"rolling back to {sha[:7]}")
    for name, cmd in [
        ("checkout", f"cd {REMOTE_REPO} && git reset --hard {sha}"),
        ("dependencies", f"cd {REMOTE_REPO} && ~/.local/bin/uv sync --package robot-runtime --extra reachy"),
        ("restart", f"sudo systemctl restart {SERVICE} && sleep 8 && systemctl is-active {SERVICE}"),
    ]:
        result = ssh(cmd, timeout=1800)
        if result.returncode != 0:
            print(f"{name} failed: {result.stderr.strip()[:400]}")
            return 1
        say(name, "ok")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="report the skew and exit")
    ap.add_argument("--rollback", action="store_true", help="restore the recorded commit")
    ap.add_argument("--enable-auto-update", action="store_true",
                    help="install the timer that follows release tags")
    ap.add_argument("--disable-auto-update", action="store_true",
                    help="remove that timer")
    args = ap.parse_args()
    if args.check:
        return check()
    if args.rollback:
        return rollback()
    if args.enable_auto_update:
        return enable_auto_update(True)
    if args.disable_auto_update:
        return enable_auto_update(False)
    return deploy()


if __name__ == "__main__":
    sys.exit(main())
