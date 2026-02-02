# OPERATIONS.md — How to operate this trading bot (human/agent)

This is the “do it from zero” operator guide for the scripts in `trading_bot/`.

## Safety model

- `RUN_MODE=debug` prints quotes only (no trades).
- `RUN_MODE=main` runs the live trading loop.
- The bot reads secrets from `.env`. Do **not** commit `.env`.

## 0) Prereqs

- Python 3
- Recommended: `tmux`
- Optional (for wallet checks): Solana CLI (`solana`)

## 1) Install

```bash
cd trading_bot
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

## 2) Configure `.env`

```bash
cp .env.example .env
```

Fill in at least:
- `PRIVATE_KEY=...` (required for live trading)
- `TOKEN_MINT=...` (required)
- `TICKER=...` (optional)

Optional:
- `JUPITER_API_KEY=...` (helps with rate limits/priority; not required)

## 3) Sanity check: quote scale (debug mode)

```bash
source .venv/bin/activate
RUN_MODE=debug python -u main.py
```

You’ll see numbers (Jupiter `outAmount`) printed every few seconds.
That value is the “quote scale” you use for your grid bounds.

## 4) Generate a grid (positions)

Create a staging grid file:
```bash
python gen_position_json.py --low 1000 --high 64000 --n 36 --out positions.staging.json
```

Promote to live:
```bash
cp positions.staging.json positions.json
```

## 5) Run live

```bash
RUN_MODE=main python -u main.py
```

Recommended (keeps running after you close your terminal):
```bash
./run_debug_tmux.sh bot_debug          # debug
# for live trading in tmux, do manually:
# tmux new -s bot_live "bash -lc 'cd $(pwd) && source .venv/bin/activate && RUN_MODE=main python -u main.py'"
```

## 6) Selector / ranking tools

### Coin selector (build shortlist)
```bash
python coin_selector.py --config selector_config.json --limit 25 --append-history selector_history.jsonl
```

### History ranking
```bash
python history_analyze.py selector_history.jsonl --limit 50 --out history_rank.json --md history_rank.md
```

### Swing ranking (>=10% swings)
```bash
python swing_analyze.py selector_history.jsonl --threshold 0.10 --days 7 --min-swings 3 --limit 50
```

## 7) Maintenance utilities (positions.json editing)

### Migrate open positions into a new grid
```bash
python migrate_positions.py --active positions.json --new positions.staging.json --out positions.merged.json
cp positions.merged.json positions.json
```

### Update sellMin across the grid
```bash
python update_sell.py --file positions.json --factor 1.08
```

### Reset costs on empty slots
```bash
python cost_reset.py --file positions.json
```

### Show total token holdings across all slots
```bash
python total_positions.py --file positions.json --divisor 1000000000
```

### Disable buys in the JSON (sell-only mode)
```bash
python sellall.py --in positions.json --out positions.sellonly.json
cp positions.sellonly.json positions.json
```

## 8) Troubleshooting

- If you see lots of quote failures (timeouts / 429):
  - increase sleep time in the bot
  - consider setting `JUPITER_API_KEY`
  - ensure your VPS IP isn’t blocked / rate limited

- If trades fail:
  - ensure wallet has SOL for fees + buy amount
  - ensure `PRIVATE_KEY` is correct
  - check the printed Solscan tx link

- If you want on-chain balance/history monitoring:
  - set a public RPC in solana CLI (`solana config set --url https://api.mainnet-beta.solana.com`)
  - or use a provider RPC (Helius/QuickNode) for reliability
