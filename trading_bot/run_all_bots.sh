#!/bin/bash
"""Run multiple bots in a single tmux session (bot farm).

This is a template script.

- Fill in the `bots` array with paths to bot entrypoints.
- It creates a tmux session and tiles panes, one bot per pane.
- Each bot is wrapped in `while true; do ...; done` so crashes restart.

USAGE:
  ./run_all_bots.sh

NOTE:
- This is not used by default.
- For production, prefer systemd user services for each bot.
"""

set -euo pipefail

# Add absolute or relative paths to bot scripts.
declare -a bots=(
    #"/path/to/trading_bot/main.py"
)

SESSION="bot_farm"

if [ ${#bots[@]} -eq 0 ]; then
  echo "No bots configured. Edit run_all_bots.sh and populate the bots array." >&2
  exit 1
fi

# Start a new tmux session with the first bot
SCRIPT_DIR=$(dirname "${bots[0]}")
SCRIPT_FILE=$(basename "${bots[0]}")
tmux new-session -d -s "$SESSION" "cd \"$SCRIPT_DIR\" && while true; do python \"$SCRIPT_FILE\" || true; done"

# For each remaining bot, split the window and run the bot
for i in "${!bots[@]}"; do
    if [ "$i" -eq 0 ]; then
        continue
    fi
    sleep 1
    SCRIPT_DIR=$(dirname "${bots[$i]}")
    SCRIPT_FILE=$(basename "${bots[$i]}")
    tmux split-window -t "$SESSION":0
    tmux select-layout -t "$SESSION":0 tiled
    tmux send-keys -t "$SESSION":0."$i" "cd \"$SCRIPT_DIR\" && while true; do python \"$SCRIPT_FILE\" || true; done" C-m
done

# Ensure tiled layout
 tmux select-layout -t "$SESSION":0 tiled

# Attach to the session
 tmux attach-session -t "$SESSION"
