#!/usr/bin/env python3
"""Analyze selector JSONL history and produce a stable "best to bot" ranking.

Input: JSONL produced by coin_selector.py --append-history history.jsonl
Output: summary JSON + markdown

Heuristic: for each mint, compute
- avg_health, avg_swing
- appearances (how often it passed)
- recency (last_seen)
Then rank by a weighted score.

USAGE:
  python history_analyze.py history.jsonl --out history_rank.json --md history_rank.md --limit 50
"""

from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from typing import Any, Dict, List


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("history", help="Path to JSONL history file")
    ap.add_argument("--out", default="history_rank.json")
    ap.add_argument("--md", default="history_rank.md")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--w-health", type=float, default=0.6)
    ap.add_argument("--w-swing", type=float, default=0.4)
    ap.add_argument("--w-appearance", type=float, default=0.25, help="bonus for repeatedly passing")
    ap.add_argument("--half-life-hours", type=float, default=24.0, help="recency decay half-life")
    args = ap.parse_args()

    stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "mint": None,
        "symbol": None,
        "n": 0,
        "sum_health": 0.0,
        "sum_swing": 0.0,
        "last_seen": 0,
        "dex": None,
    })

    now = int(time.time())

    with open(args.history, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue

            ts = int(rec.get("generated_at") or 0)
            passed = rec.get("passed") or []
            for x in passed:
                mint = x.get("mint")
                if not mint:
                    continue
                s = stats[mint]
                s["mint"] = mint
                s["symbol"] = x.get("symbol") or s.get("symbol")
                s["dex"] = x.get("dex") or s.get("dex")
                s["n"] += 1
                s["sum_health"] += float(x.get("health") or 0)
                s["sum_swing"] += float(x.get("swing") or 0)
                s["last_seen"] = max(s["last_seen"], ts)

    rows: List[Dict[str, Any]] = []
    for mint, s in stats.items():
        n = s["n"]
        if n <= 0:
            continue
        avg_health = s["sum_health"] / n
        avg_swing = s["sum_swing"] / n

        # appearance factor (0..1) saturating
        appearance = clamp(n / 20.0, 0.0, 1.0)

        # recency decay
        age_seconds = max(0, now - int(s["last_seen"]))
        half_life = args.half_life_hours * 3600.0
        recency = 0.0
        if half_life > 0:
            recency = 2 ** (-(age_seconds / half_life))  # 1.0 now, 0.5 at half-life
        else:
            recency = 1.0

        base = args.w_health * avg_health + args.w_swing * avg_swing
        score = base * recency + args.w_appearance * appearance
        rows.append({
            "mint": mint,
            "symbol": s.get("symbol"),
            "score": round(score, 4),
            "avg_health": round(avg_health, 4),
            "avg_swing": round(avg_swing, 4),
            "appearances": n,
            "last_seen": int(s["last_seen"]),
            "dex": s.get("dex"),
        })

    rows.sort(key=lambda r: r["score"], reverse=True)
    top = rows[: args.limit]

    payload = {
        "generated_at": int(time.time()),
        "limit": args.limit,
        "weights": {
            "health": args.w_health,
            "swing": args.w_swing,
            "appearance": args.w_appearance,
            "half_life_hours": args.half_life_hours,
        },
        "ranked": top,
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    # markdown
    lines: List[str] = []
    lines.append(f"# History ranking (top {len(top)})")
    lines.append("")
    lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    lines.append("")
    lines.append("## Weights")
    lines.append("```json")
    lines.append(json.dumps(payload["weights"], indent=2))
    lines.append("```")
    lines.append("")
    lines.append("## Ranked")
    lines.append("")
    for i, r in enumerate(top, 1):
        lines.append(
            f"{i}. **{r.get('symbol')}** — score **{r['score']}** (avg_health {r['avg_health']}, avg_swing {r['avg_swing']}, seen {r['appearances']})\\\n"
            f"   - mint: `{r['mint']}`\\\n"
            f"   - dexscreener: {r.get('dex')}"
        )
        lines.append("")

    with open(args.md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Wrote {args.out} and {args.md} (processed {len(rows)} mints)")


if __name__ == "__main__":
    main()
