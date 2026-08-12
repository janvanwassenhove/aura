#!/usr/bin/env bash
# Self-update for the robot — U241. Runs ON the Pi, on a timer.
#
# The Pi drifted 74 commits behind because updating it needed a human at a
# laptop. Now it follows RELEASE TAGS by itself: the same cadence the desktop
# app already uses, and every tag has been through CI.
#
# Four rules, each of them the difference between an unattended update and an
# unattended outage:
#
#   1. Releases only. Never master — the robot must not follow a commit that
#      was true for ninety seconds.
#   2. Never mid-sentence. It restarts the service, which cuts audio and motion;
#      it waits for an idle robot and tries again next hour.
#   3. --extra reachy, always. A plain sync REMOVES the SDK and the next restart
#      takes the robot offline (U239, learned the hard way).
#   4. Verify, then roll back on its own. An update nobody watched must be able
#      to undo itself, or it is a gamble with somebody's living room.
#
# It runs from /usr/local/bin, NOT from the checkout. Two reasons, both found
# by testing rather than by thinking:
#
#   * `git reset --hard` swaps files while bash is still reading this one. A
#     shell script edited underneath a running shell executes garbage.
#   * A robot far enough behind predates the script entirely — reset to an older
#     tag and the updater deletes itself. The one thing that must survive being
#     out of date is the thing that fixes being out of date.
#
# After a healthy update it refreshes that installed copy, so improvements to
# the updater still reach the robot — one release later, deliberately.
#
# Everything lands in the journal: journalctl -u aura-robot-update

set -uo pipefail

REPO_DIR="${REPO_DIR:-$HOME/aura}"
SERVICE="${SERVICE:-aura-robot-runtime}"
UV="${UV:-$HOME/.local/bin/uv}"
HEALTH="${HEALTH:-http://127.0.0.1:8001/health}"
ROLLBACK_FILE="${ROLLBACK_FILE:-$HOME/aura-rollback.sha}"
HEALTH_TRIES="${HEALTH_TRIES:-20}"

log() { echo "[selfupdate] $*"; }
die() { log "ERROR: $*"; exit 1; }

cd "$REPO_DIR" || die "no repo at $REPO_DIR"

# --- what is available, and what are we on? --------------------------------
git fetch --tags --quiet origin || die "cannot reach the remote"
latest_tag="$(git tag --list 'v*' --sort=-v:refname | head -1)"
[ -n "$latest_tag" ] || die "no release tags found"

target="$(git rev-list -n1 "$latest_tag")"
current="$(git rev-parse HEAD)"

if [ "$target" = "$current" ]; then
  log "in step with $latest_tag — nothing to do"
  exit 0
fi
log "update available: $latest_tag ($(echo "$target" | cut -c1-7)), currently $(echo "$current" | cut -c1-7)"

# --- rule 2: never mid-sentence --------------------------------------------
# A restart cuts audio and motion. Waiting an hour costs nothing; interrupting
# a conversation costs the owner's trust in the thing.
state="$(curl -sf --max-time 5 "$HEALTH" | sed -n 's/.*"behavior_state"[: ]*"\([a-z_]*\)".*/\1/p')"
if [ -z "$state" ]; then
  log "the runtime is not answering /health — leaving it alone"
  exit 0
fi
if [ "$state" != "idle" ]; then
  log "robot is busy (state=$state) — trying again on the next timer"
  exit 0
fi

# --- do it, remembering how to undo it -------------------------------------
echo "$current" > "$ROLLBACK_FILE"
log "rollback point recorded: $(echo "$current" | cut -c1-7)"

git reset --hard "$target" --quiet || die "checkout failed — nothing restarted"
log "checked out $latest_tag"

# rule 3 — the extra is not optional on real hardware
if ! "$UV" sync --package robot-runtime --extra reachy >/tmp/selfupdate-sync.log 2>&1; then
  log "dependency sync failed, see /tmp/selfupdate-sync.log — rolling back"
  git reset --hard "$current" --quiet
  "$UV" sync --package robot-runtime --extra reachy >/dev/null 2>&1
  exit 1
fi
log "dependencies synced"

# The one check that is still free: before the restart.
if ! "$UV" run --package robot-runtime python -c "import reachy_mini" >/dev/null 2>&1; then
  log "the reachy SDK is not importable after the sync — rolling back, NOT restarting"
  git reset --hard "$current" --quiet
  "$UV" sync --package robot-runtime --extra reachy >/dev/null 2>&1
  exit 1
fi
log "reachy sdk importable"

sudo systemctl restart "$SERVICE" || die "restart failed"

# --- rule 4: verify, and undo itself if it cannot ---------------------------
ok=""
for _ in $(seq 1 "$HEALTH_TRIES"); do
  sleep 3
  if curl -sf --max-time 5 "$HEALTH" | grep -q '"status"'; then ok=1; break; fi
done

if [ -z "$ok" ]; then
  log "the robot did not come back after $((HEALTH_TRIES * 3))s — rolling back to $(echo "$current" | cut -c1-7)"
  git reset --hard "$current" --quiet
  "$UV" sync --package robot-runtime --extra reachy >/dev/null 2>&1
  sudo systemctl restart "$SERVICE"
  sleep 10
  if curl -sf --max-time 5 "$HEALTH" >/dev/null; then
    log "rolled back and healthy again"
  else
    log "ROLLED BACK AND STILL UNHEALTHY — this needs a human"
  fi
  exit 1
fi

# Now that the new code is proven healthy, adopt its version of this script for
# next time. Never before: a broken updater must not be able to break a robot.
INSTALLED="${INSTALLED:-/usr/local/bin/aura-robot-selfupdate}"
if [ -f "$REPO_DIR/scripts/robot_selfupdate.sh" ] && [ -w "$(dirname "$INSTALLED")" -o -n "$(sudo -n true 2>/dev/null && echo yes)" ]; then
  if ! cmp -s "$REPO_DIR/scripts/robot_selfupdate.sh" "$INSTALLED"; then
    sudo install -m 0755 "$REPO_DIR/scripts/robot_selfupdate.sh" "$INSTALLED"       && log "self-update script refreshed for next time"
  fi
fi

log "updated to $latest_tag and healthy"
