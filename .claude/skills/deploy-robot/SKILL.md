---
name: deploy-robot
description: Deploy robot-runtime to the Reachy Mini Pi, or check whether it has drifted behind the laptop. Use when robot code changed, when a brain→runtime route returns 404, when the robot behaves like an older version, or when asked to update/redeploy the robot or check the deployment skew.
---

# Deploying to the robot

The laptop updates itself several times a day. The Pi is deployed by hand and
stays on whatever it was last given — it once sat **74 commits behind** for a
month, and the first sign was a new endpoint returning 404 while a button
silently did nothing.

## Check first, always

```bash
python scripts/deploy_robot.py --check
```

- `in step` — nothing to do.
- `BEHIND` — deploy.
- `cannot say` — the runtime predates the build endpoint (U240). That is itself
  an answer: it is old. Deploy.

The brain also reports this on every maintenance tick (`robot_build` in the
report), so drift surfaces on its own rather than waiting to be looked for.

## Deploy

```bash
python scripts/deploy_robot.py
```

It refuses on a dirty working tree — deploy what is committed, or the robot ends
up running code that exists nowhere else. Then: rollback point, bundle,
transfer, fetch, reset, dependencies, **SDK check**, restart, verify.

## The two traps, both learned the hard way

**`uv sync --package robot-runtime` removes the Reachy SDK.** It prunes the
environment to that package's base dependencies, and `reachy-mini` lives in the
`reachy` extra. Restart at that moment and the robot goes offline. Always
`--extra reachy`. The script verifies the SDK imports *before* restarting, which
is the only point where the mistake is still free.

**`git pull` cannot work on the Pi.** Its history was rewritten (privacy
filter-repo) and shares no ancestry with this repo. Fetch a bundle into a ref
and hard-reset onto it — which is what the script does.

## After deploying

Verify what you can from here, and say plainly what you cannot:

- `--check` should now say `in step`.
- `systemctl is-active aura-robot-runtime` → `active`, `NRestarts=0`.
- Behaviour that was the reason for the deploy — test it through the API.
- **Camera, audio and speech need the owner's eyes and ears.** A deploy can
  cross many commits that touch the media path; do not claim those work.

## Rolling back

```bash
python scripts/deploy_robot.py --rollback
```

Restores the commit recorded on the Pi before the last deploy
(`~/aura-rollback.sha`), re-syncs with the extra, restarts.

## Connection details

| | |
|---|---|
| Host | `pollen@reachy-mini.local` |
| Key | `~/.ssh/reachy` |
| Repo | `~/aura` |
| Service | `aura-robot-runtime` (systemd, boot-enabled, port 8001) |
| uv | `~/.local/bin/uv` |

The robot needs `X-AURA-Secret` on every `/robot/*` call (U220); the script reads
it from the app's `.env`. A 401 while probing means the header is missing, not
that the route is absent.
