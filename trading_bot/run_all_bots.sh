#!/bin/bash

declare -a bots=(
    #"PATH/TO/BOT1.py"
    #"PATH/TO/BOT2.py"
    #"PATH/TO/BOT3.py"
)

SESSION="bot_farm"

# Start a new tmux session with the first bot
SCRIPT_DIR=$(dirname "${bots[0]}")
SCRIPT_FILE=$(basename "${bots[0]}")
tmux new-session -d -s $SESSION "cd \"$SCRIPT_DIR\" && while true; do python \"$SCRIPT_FILE\" || true; done"

# For each remaining bot, split the window and run the bot
for i in "${!bots[@]}"; do
    if [ $i -eq 0 ]; then
        continue
    fi
    sleep 1
    SCRIPT_DIR=$(dirname "${bots[$i]}")
    SCRIPT_FILE=$(basename "${bots[$i]}")
    tmux split-window -t $SESSION:0
    tmux select-layout -t $SESSION:0 tiled
    tmux send-keys -t $SESSION:0.$i "cd \"$SCRIPT_DIR\" && while true; do python \"$SCRIPT_FILE\" || true; done" C-m
done

# Ensure tiled layout
tmux select-layout -t $SESSION:0 tiled

# Attach to the session
tmux attach-session -t $SESSION