#!/usr/bin/env python3
"""Analyze selector JSONL history and produce a stable "best to bot" ranking.

Input: JSONL produced by coin_selector.py --append-history history.jsonl
Output: summary JSON + markdown

Heuristic: for each mint, compute
- avg_health, avg_swing
- appearances (how often it passed)
- recency (last_seen)
- (optional) >=X% swing frequency per day from priceUsd samples

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


def day_id(ts: int) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ts))


def count_swings(prices, threshold: float) -> int:
    """Count back-and-forth swings >= threshold using a simple anchor/flip algorithm."""
    if len(prices) < 3:
        return 0

    anchor = prices[0][1]
    direction = 0
    swings = 0

    for _, p in prices[1:]:
        if anchor <= 0:
            anchor = p
            continue
        change = (p - anchor) / anchor

        if direction == 0:
            if change >= threshold:
                swings += 1
                direction = -1
                anchor = p
            elif change <= -threshold:
                swings += 1
                direction = +1
                anchor = p
        elif direction == +1:
            if change >= threshold:
                swings += 1
                direction = -1
                anchor = p
            elif p < anchor:
                anchor = p
        else:  # direction == -1
            if change <= -threshold:
                swings += 1
                direction = +1
                anchor = p
            elif p > anchor:
                anchor = p

    return swings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("history", help="Path to JSONL history file")
    ap.add_argument("--out", default="history_rank.json")
    ap.add_argument("--md", default="history_rank.md")
    ap.add_argument("--limit", type=int, default=50)

    # core ranking weights
    ap.add_argument("--w-health", type=float, default=0.6)
    ap.add_argument("--w-swing", type=float, default=0.4)
    ap.add_argument("--w-appearance", type=float, default=0.25, help="bonus for repeatedly passing")
    ap.add_argument("--half-life-hours", type=float, default=24.0, help="recency decay half-life")

    # optional >=X% swing frequency from priceUsd history
    ap.add_argument("--swing-threshold", type=float, default=0.10, help="swing threshold fraction (0.10 == 10%%)")
    ap.add_argument("--swing-days", type=int, default=7, help="rolling window days for swing counting")
    ap.add_argument("--min-swings", type=int, default=3, help="min swings/day to count a day as 'good'")
    ap.add_argument("--w-swingfreq", type=float, default=0.35, help="weight for swing frequency (>=threshold) metric")

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

    # price history for swing counting (mint -> day -> [(ts, priceUsd)])
    price_series: Dict[str, Dict[str, List[tuple[int, float]]]] = defaultdict(lambda: defaultdict(list))

    now = int(time.time())
    cutoff = now - int(args.swing_days) * 86400

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

                # optional price-based swing tracking
                if ts >= cutoff:
                    p = x.get("priceUsd")
                    try:
                        p = float(p) if p is not None else None
                    except Exception:
                        p = None
                    if p and p > 0:
                        price_series[mint][day_id(ts)].append((ts, p))

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
        if half_life > 0:
            recency = 2 ** (-(age_seconds / half_life))
        else:
            recency = 1.0

        # swing frequency (>= threshold) from price history (optional)
        by_day = price_series.get(mint) or {}
        day_counts: Dict[str, int] = {}
        for d, pts in by_day.items():
            pts.sort(key=lambda t: t[0])
            day_counts[d] = count_swings(pts, threshold=float(args.swing_threshold))

        days_seen = len(day_counts)
        total_swings = sum(day_counts.values())
        avg_swings_per_day = (total_swings / days_seen) if days_seen else 0.0
        days_ge_min = sum(1 for v in day_counts.values() if v >= int(args.min_swings))
        frac_days_ge = (days_ge_min / days_seen) if days_seen else 0.0

        base = args.w_health * avg_health + args.w_swing * avg_swing
        # swingfreq term rewards coins that repeatedly hit your "3+ swings/day" quality bar
        swingfreq_term = args.w_swingfreq * (frac_days_ge + 0.25 * clamp(avg_swings_per_day / 6.0, 0.0, 1.0))

        score = base * recency + args.w_appearance * appearance + swingfreq_term

        rows.append({
            "mint": mint,
            "symbol": s.get("symbol"),
            "score": round(score, 4),
            "avg_health": round(avg_health, 4),
            "avg_swing": round(avg_swing, 4),
            "appearances": n,
            "last_seen": int(s["last_seen"]),
            "dex": s.get("dex"),
            "swingfreq": {
                "window_days": int(args.swing_days),
                "threshold": float(args.swing_threshold),
                "min_swings": int(args.min_swings),
                "days_seen": days_seen,
                "days_ge_min": days_ge_min,
                "avg_swings_per_day": round(avg_swings_per_day, 3),
                "today_swings": day_counts.get(day_id(now), 0),
            },
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
            "swingfreq": args.w_swingfreq,
            "swing_threshold": args.swing_threshold,
            "swing_days": args.swing_days,
            "min_swings": args.min_swings,
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
