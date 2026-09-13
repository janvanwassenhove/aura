#!/usr/bin/env python3
"""U330: refresh the README screenshots with ONE command.

    python scripts/refresh_screenshots.py            # all of them
    python scripts/refresh_screenshots.py --keep     # leave the stack running

Why this exists: the pictures come from a demo stack (fake robot, echo LLM, one
fictional persona), and that stack had to be assembled by hand — build the
console against the right port, boot two services with eight isolated paths,
serve the console, install a browser, capture, convert. Six steps nobody
repeats, so the shots sat still for weeks while the app moved underneath them:
by the time the owner said "ik merk daar nog oude layouts", Settings was two
units behind and did not show the calendar connection at all. U297 automated
capture inside the release; this automates it here, which is the only place
the committed files can actually change.

Two safety rules are code here rather than comments:

* **Nothing may point at `./data`.** Those defaults are a real knowledge store
  on a developer's machine; a screenshot stack that reads them publishes
  someone's family. Every owner-state path is redirected into a throwaway
  directory, and the run refuses to start if one of them still resolves inside
  the repository.
* **Nothing may touch the running app.** Ports are picked free rather than
  assumed, so a demo brain can never bind (or worse, be captured) next to the
  one the owner is using on 8020.
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CONSOLE = REPO / "apps" / "operator-console"
CAPTURE = REPO / ".github" / "scripts" / "release-screenshots.mjs"

#: Every environment variable that otherwise stores owner state under ./data.
#: Keep this in step with `test_owner_state_is_persisted.py`, which scans for
#: exactly these defaults — a new one there is a new one here.
OWNER_STATE = (
    "KNOWLEDGE_DB_PATH", "RECOGNITION_DB_PATH", "MODE_POLICY_PATH",
    "CONNECTOR_PREFS_PATH", "MCP_SERVERS_PATH", "TURN_TRACE_PATH",
    "GESTURE_MODEL_PATH", "DATABASE_URL", "SKILLS_DIR", "SCENARIOS_DIR",
)

#: Fictional, and the only profile the stack will ever hold (U160).
DEMO_PASSPHRASE = "demo-stack-passphrase"   # privacy-ok: fictional demo data only


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def demo_env(tmp: Path, brain_port: int, robot_port: int) -> dict[str, str]:
    """The environment of a stack that cannot reach anything real."""
    data, skills, scenarios = tmp / "data", tmp / "skills", tmp / "scenarios"
    for d in (data, skills, scenarios):
        d.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update({
        # No keys: the echo provider answers deterministically, which is also
        # what makes the captured conversation reproducible.
        "OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": "", "LLM_PROVIDER": "echo",
        "PORT": str(brain_port),
        "ROBOT_RUNTIME_URL": f"http://localhost:{robot_port}",
        "CORS_ORIGINS": "*",
        "DEMO_PERSONA": "true",          # the one fictional profile
        "VOICE_MODE": "off",             # no microphone, no wake word
        "RECOGNITION_ENABLED": "false",  # no camera, no embeddings
        "GESTURES_ENABLED": "false",
        "PROACTIVE_ENABLED": "false",    # nothing speaks on its own mid-capture
        # ON, and deliberately: the offline picture needs the BRAIN to
        # notice the robot is gone, and the heartbeat is what notices.
        # With it off, the console kept drawing a robot that was dead,
        # and the capture refused (correctly) to photograph that.
        "HEARTBEAT_ENABLED": "true",
        "KNOWLEDGE_PASSPHRASE": DEMO_PASSPHRASE,
        "SKILLS_DIR": str(skills),
        "SCENARIOS_DIR": str(scenarios),
        "DATABASE_URL": f"sqlite+aiosqlite:///{data.as_posix()}/memory.db",
        "KNOWLEDGE_DB_PATH": str(data / "knowledge.enc.json"),
        "RECOGNITION_DB_PATH": str(data / "recognition.enc.json"),
        "MODE_POLICY_PATH": str(data / "mode-policy.json"),
        "CONNECTOR_PREFS_PATH": str(data / "connector-prefs.json"),
        "MCP_SERVERS_PATH": str(data / "mcp-servers.json"),
        "TURN_TRACE_PATH": str(data / "turn_traces.jsonl"),
        "GESTURE_MODEL_PATH": str(data / "models" / "hand_landmarker.task"),
    })
    return env


def check_isolated(env: dict[str, str]) -> list[str]:
    """Every owner-state path must live outside the repository. Returns the
    offenders, so the caller can refuse rather than publish someone's data."""
    bad: list[str] = []
    for key in OWNER_STATE:
        raw = env.get(key, "")
        if not raw:
            bad.append(f"{key} is unset (it would default into ./data)")
            continue
        path = Path(raw.split("///")[-1] if "///" in raw else raw)
        try:
            path.resolve().relative_to(REPO)
        except ValueError:
            continue          # outside the repo: good
        bad.append(f"{key} resolves inside the repository ({path})")
    return bad


def wait_for(url: str, timeout_s: float = 120.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:  # noqa: S310
                if r.status == 200:
                    return True
        except (urllib.error.URLError, OSError, TimeoutError):
            time.sleep(1.0)
    return False


def wait_until_offline(brain_port: int, timeout_s: float = 60.0) -> bool:
    """Wait for the BRAIN to agree the robot is gone, not just for the process
    to die. The console draws what the brain reports."""
    import json

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(  # noqa: S310
                    f"http://localhost:{brain_port}/robot/status", timeout=12) as r:
                if not json.loads(r.read() or b"{}").get("connected", False):
                    return True
        except (urllib.error.HTTPError, urllib.error.URLError, OSError,
                TimeoutError, ValueError):
            return True          # unreachable status is itself "not connected"
        time.sleep(2.0)
    return False


def stop(proc: subprocess.Popen) -> None:
    """Stop a server AND the process it wrapped.

    `uv run` is a launcher: terminating it leaves the server underneath alive,
    still bound to the port and still answering. Measured the hard way — a
    "stopped" fake robot went on reporting itself healthy for a full minute,
    which looked exactly like the brain lying about a connection it did not
    have.
    """
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           check=False, capture_output=True)
        else:
            proc.terminate()
        proc.wait(timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        try:
            proc.kill()
        except OSError:
            pass


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    print(f"  $ {' '.join(cmd[:6])}{' …' if len(cmd) > 6 else ''}")
    return subprocess.run(cmd, check=True, **kw)


def npx() -> str:
    return shutil.which("npx") or ("npx.cmd" if os.name == "nt" else "npx")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--keep", action="store_true",
                    help="leave the demo stack running afterwards")
    ap.add_argument("--shots", default="",
                    help="comma-separated shot names (default: all)")
    args = ap.parse_args()

    brain_port, robot_port, console_port = free_port(), free_port(), free_port()
    tmp = Path(tempfile.mkdtemp(prefix="aura-shots-"))
    out = tmp / "shots"
    out.mkdir()
    env = demo_env(tmp, brain_port, robot_port)

    offenders = check_isolated(env)
    if offenders:
        print("refusing to run — the stack is not isolated:")
        for line in offenders:
            print(f"  [x] {line}")
        return 1

    print(f"demo stack: brain :{brain_port}  robot :{robot_port}  console :{console_port}")
    print(f"throwaway state: {tmp}")
    procs: list[subprocess.Popen] = []
    try:
        print("building the console against the demo brain…")
        run(["npm", "run", "build"], cwd=CONSOLE, shell=(os.name == "nt"), env={
            **env,
            "VITE_BRAIN_URL": f"http://localhost:{brain_port}",
            "VITE_CONVERSATION_URL": f"http://localhost:{brain_port}",
            "VITE_ROBOT_RUNTIME_WS": f"ws://localhost:{brain_port}/ws/events",
        })

        print("booting the fake robot and the demo brain…")
        procs.append(subprocess.Popen(
            ["uv", "run", "--package", "robot-runtime", "robot-runtime"],
            cwd=REPO, env={**env, "ROBOT_ADAPTER": "fake", "PORT": str(robot_port)},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        procs.append(subprocess.Popen(
            ["uv", "run", "--package", "aura-brain", "aura-brain"],
            cwd=REPO, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        for name, url in (("robot", f"http://localhost:{robot_port}/health"),
                          ("brain", f"http://localhost:{brain_port}/health")):
            if not wait_for(url):
                print(f"the demo {name} never came up")
                return 1

        print("serving the console…")
        procs.append(subprocess.Popen(
            [npx(), "vite", "preview", "--port", str(console_port)],
            cwd=CONSOLE, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        if not wait_for(f"http://localhost:{console_port}/"):
            print("the console never came up")
            return 1

        print("capturing…")
        run([npx(), "playwright", "install", "chromium"], cwd=REPO, env=env)
        shot_env = {**env, "CONSOLE_URL": f"http://localhost:{console_port}",
                    "OUT_DIR": str(out)}
        if args.shots:
            shot_env["SHOTS"] = args.shots
        if args.shots.strip() != "06-robot-offline":
            run(["node", str(CAPTURE)], cwd=REPO, env=shot_env)

        if not args.shots or "06-robot-offline" in args.shots:
            # `06-robot-offline` is the one picture that needs the robot GONE,
            # which is why the capture script marks it manual.
            #
            # Killing the robot mid-run is NOT enough: measured, the brain went
            # on reporting `connected: true` for over a minute afterwards, so
            # the console kept drawing a healthy robot and the picture would
            # have contradicted its own caption. A brain that never reached a
            # robot at all is unambiguous, so the offline shot gets its own
            # brain, pointed at a port where nothing listens.
            print("restarting the brain with no robot to reach…")
            for p in (procs[1], procs[0]):       # brain first, then the robot
                stop(p)
            procs.clear()
            dead_port = free_port()
            lonely = {**env, "ROBOT_RUNTIME_URL": f"http://localhost:{dead_port}"}
            procs.append(subprocess.Popen(
                ["uv", "run", "--package", "aura-brain", "aura-brain"],
                cwd=REPO, env=lonely,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            if not wait_for(f"http://localhost:{brain_port}/health"):
                print("the brain did not come back up for the offline shot")
                return 1
            if not wait_until_offline(brain_port):
                print("the brain reports a robot it cannot possibly reach — "
                      "not capturing a picture that would contradict itself")
                return 1
            run(["node", str(CAPTURE)], cwd=REPO,
                env={**shot_env, "SHOTS": "06-robot-offline"})

        print("converting to the .webp files the README points at…")
        run([sys.executable, str(REPO / "scripts" / "readme_shots.py"),
             "--shots", str(out)], cwd=REPO, env=env)
        print("done — `git status docs/screenshots` shows what moved.")
        return 0
    finally:
        # No `return` in here: it would swallow a failure above and report
        # success, which is the one thing a refresh script must never do.
        if args.keep:
            print(f"leaving the stack running; state in {tmp}")
        else:
            for p in procs:
                stop(p)
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
