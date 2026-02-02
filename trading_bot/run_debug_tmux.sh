#!/bin/bash
# Run the bot in tmux (debug / quote-printing mode).
#
# This is a safe way to leave the bot running in the background while you
# observe quote scale and tune grid parameters.
#
# USAGE:
#   ./run_debug_tmux.sh            # uses session name bot_debug
#   ./run_debug_tmux.sh mysession

set -euo pipefail

SESSION=${1:-bot_debug}

cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo ".venv not found. Create it first:" >&2
  echo "  python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt" >&2
  exit 1
fi

# Start session detached if not exists
if ! tmux has-session -t "$SESSION" 2>/dev/null; then
  tmux new-session -d -s "$SESSION" "bash -lc 'cd "$(pwd)" && source .venv/bin/activate && RUN_MODE=debug python -u main.py'"
fi

echo "tmux session: $SESSION"
echo "attach with: tmux attach -t $SESSION"
