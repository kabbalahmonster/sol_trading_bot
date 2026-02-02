# Swing analyzer notes

Right now swing_analyze can only count swings once we have **priceUsd** in history.
We only started recording priceUsd on 2026-02-02, so we need more history.

Once you have ~1 day of 5-minute samples, swing_analyze will start showing non-zero swings.

Run selector manually (or wait for timer) to accumulate history:
- systemd timer solbot-selector.timer runs every 5 minutes.

Then run:
  python swing_analyze.py selector_history.jsonl --threshold 0.10 --days 7 --min-swings 3 --limit 50

Outputs:
- swing_rank.md
- swing_rank.json
