#!/bin/sh
# Claude Code hook: 10 minutes after session start, rename the workspace.
# Runs in the background so Claude Code doesn't wait.
set -eu

[ "${HERDR_ENV:-}" = "1" ] || exit 0
[ -n "${HERDR_PANE_ID:-}" ] || exit 0

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOCK_DIR="$HOME/.config/herdr-spaces/locks"
LOCK_FILE="$LOCK_DIR/${HERDR_PANE_ID}.pid"
DELAY=600

mkdir -p "$LOCK_DIR"

# Don't spawn a second timer for the same pane
if [ -f "$LOCK_FILE" ] && kill -0 "$(cat "$LOCK_FILE")" 2>/dev/null; then
  exit 0
fi

(
  echo $$ > "$LOCK_FILE"
  sleep "$DELAY"
  python3 "$SCRIPT_DIR/herdr-spaces.py" 2>/dev/null
  rm -f "$LOCK_FILE"
) &
disown
