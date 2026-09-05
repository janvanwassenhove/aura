---
feature: "021-robot-deployment"
---

# Implementation Plan: Getting Code onto the Robot

**Prerequisites**: `spec.md`. Retro-written from the scripts.

## Shape

```
laptop (self-updating)          robot / Raspberry Pi
  aura-brain  ──── HTTP ────▶  robot-runtime :8001
       │                            ▲
       │                            │ git pull + restart
       │                       robot_selfupdate.sh  ◀── systemd timer
       │
  deploy_robot.py --check ──▶ compares commits, reports BEHIND
```

## Decisions

### The asymmetry is permanent, so design for it

The laptop updates itself the moment a release lands; the robot is a Raspberry
Pi in a living room. Even with the self-update timer (U241) there is a window,
and a household that never reboots the robot can sit in it for weeks. So
constitution X is a *design rule*, not an aspiration: a new brain→runtime call
goes in its own `try`, must not break the sequence around it on a 404, and
reports the degradation rather than plain success.

U238 is what happens when it is ignored: one 404 made the sleep button do
nothing and report that it had worked.

### The updater lives outside the tree it updates

U242. A script that `git pull`s the directory it is executing from can be
replaced mid-run. It is copied out and driven by a timer.

### Check, then diff — a commit behind is not always work to do

U240 gives the honest signal (`robot: 98481ac / here: 609146d — BEHIND`), but
"behind" counts every commit, and most units never touch `robot-runtime`. The
routine is therefore two steps: the check tells you the robot is behind, and
`git diff` on `services/robot-runtime` tells you whether that matters. Deploying
anyway is not free — it restarts the runtime, which drops the conversation.

### Diagnose in the place the fix lives

U198 → U199 → U200 were three units in a row because each stopped one step
short. Saying "connection refused" is better than a spinner, but the owner then
has to find where to set the address; offering the field is better, but they
still have to know the address. The finished shape says what is wrong, offers
the pre-filled field, and can scan the network for the robot — on one screen.

## Files

| Path | Role |
|---|---|
| `scripts/deploy_robot.py` | `--check` (drift) and the deploy itself |
| `scripts/robot_selfupdate.sh` | Pull + restart, run by a timer on the Pi |
| `.gitattributes` | Line endings pinned so two hosts share one tree |
| `services/robot-runtime/` | Everything that runs on the Pi |
| `apps/operator-console/src/views/RobotView.vue` | The Connection card: reason, address, scan |
