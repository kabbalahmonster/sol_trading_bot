# sol_trading_bot

A pragmatic Solana grid-trading bot that uses Jupiter's **Ultra API** (via `jup-python-sdk`) for execution.

This repo contains:
- `trading_bot/main.py` — the bot (grid buy/sell loop)
- `trading_bot/positions.json` — per-coin grid configuration/state (balances/costs)
- `trading_bot/gen_position_json.py` — generate a new grid file (staging)
- `trading_bot/migrate_positions.py` — migrate open positions into a new grid
- `trading_bot/coin_selector.py` — discover/rank coins (Dexscreener + RugCheck)
- `trading_bot/history_analyze.py` — rank "best to bot" over time (uses history)
- `trading_bot/swing_analyze.py` — track >=10% swing frequency from logged prices

> ⚠️ Trading is risky. This code is not audited. Use at your own risk.

## Quick start (fresh install)

### 1) Create a venv and install deps
```bash
cd trading_bot
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

### 2) Create `.env`
Create `trading_bot/.env` (never commit it):
```bash
cp .env.example .env
```

### 3) Run debug mode (quotes only)
```bash
RUN_MODE=debug python -u main.py
```

### 4) Generate a grid
Example:
```bash
python gen_position_json.py --low 1000 --high 64000 --n 36 --out positions.staging.json
```
Then promote staging to live:
```bash
cp positions.staging.json positions.json
```

### 5) Run main loop (live)
```bash
RUN_MODE=main python -u main.py
```

## Repo conventions

### `positions.json`
This file is both:
- your *grid definition* (`buyMin`, `buyMax`, `sellMin`, `stoploss`)
- and your *state* (`balance`, `cost`)

Back it up before changing.

### Staging + migration
- Generate new grid to `positions.staging.json`
- Migrate balances/costs into the new grid:
```bash
python migrate_positions.py --active positions.json --new positions.staging.json --out positions.merged.json
```
- Then replace:
```bash
cp positions.merged.json positions.json
```

## Coin discovery (selector)
Run:
```bash
python coin_selector.py --config selector_config.json --limit 25 --append-history selector_history.jsonl
```
Outputs:
- `shortlist.md/json` (latest)
- `selector_history.jsonl` (append-only)

## History ranking
```bash
python history_analyze.py selector_history.jsonl --limit 50
```

## Swing frequency (>=10% swings, 3+ per day)
Requires some history to accumulate.
```bash
python swing_analyze.py selector_history.jsonl --threshold 0.10 --days 7 --min-swings 3 --limit 50
```
