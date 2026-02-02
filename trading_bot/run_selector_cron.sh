#!/bin/bash
# Run the coin selector once and append to selector_history.jsonl.
#
# Intended to be called by cron/systemd timer every ~5 minutes.
# Safety features:
# - Uses flock to prevent overlapping runs.
# - Uses timeout so the scheduler can't pile up.
# - Silences stdout/stderr (write outputs are the files).

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

LOCKFILE="$DIR/.selector.lock"
HISTORY="$DIR/selector_history.jsonl"

# Use a hard timeout so cron can't pile up.
# Use flock so only one run happens at a time.
flock -n "$LOCKFILE" timeout 240s \
  python3 coin_selector.py --config selector_config.json --limit 25 --append-history "$HISTORY" \
  >/dev/null 2>&1
