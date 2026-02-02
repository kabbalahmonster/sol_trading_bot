#!/bin/bash
set -euo pipefail

SESSION=${1:-bot_debug}

cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo ".venv not found. Create it first: python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt" >&2
  exit 1
fi

# start session detached if not exists
if ! tmux has-session -t "$SESSION" 2>/dev/null; then
  tmux new-session -d -s "$SESSION" "bash -lc 'cd "$(pwd)" && source .venv/bin/activate && RUN_MODE=debug python main.py'"
fi

echo "tmux session: $SESSION"
echo "attach with: tmux attach -t $SESSION"
