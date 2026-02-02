#!/usr/bin/env python3
"""Compute ">=10% swings" frequency per coin from selector history.

Requires selector_history.jsonl produced by coin_selector.py --append-history.
History must include priceUsd (added in newer versions).

We count a "swing" when price moves >= threshold from a local anchor and then resets.
This is a coarse approximation but works well with 5-minute sampling.

USAGE:
  python swing_analyze.py selector_history.jsonl --threshold 0.10 --days 7 --min-swings 3

Outputs:
  swing_rank.json / swing_rank.md
"""

from __future__ import annotations

import argparse
import json
import math
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def day_id(ts: int) -> str:
    # ts is unix seconds
    return time.strftime("%Y-%m-%d", time.gmtime(ts))


def parse_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def count_swings(prices: List[Tuple[int, float]], threshold: float) -> int:
    """Count swings in a time-ordered (ts, price) list.

    Algorithm:
    - Track mode: looking_for_up or looking_for_down based on last direction.
    - Maintain an anchor price.
    - When price moves >= threshold from anchor in the relevant direction, count a swing and flip direction,
      setting new anchor at current price.

    This counts back-and-forth swings rather than a single monotonic move.
    """

    if len(prices) < 3:
        return 0

    # Start with first price as anchor, looking for either direction.
    anchor = prices[0][1]
    direction = 0  # 0 unknown, +1 looking for up swing completion, -1 looking for down swing completion

    swings = 0

    for _, p in prices[1:]:
        if anchor <= 0:
            anchor = p
            continue

        change = (p - anchor) / anchor

        if direction == 0:
            # pick direction once it moves meaningfully
            if change >= threshold:
                swings += 1
                direction = -1
                anchor = p
            elif change <= -threshold:
                swings += 1
                direction = +1
                anchor = p

        elif direction == +1:
            # looking for an up move from anchor
            if change >= threshold:
                swings += 1
                direction = -1
                anchor = p
            # if it makes a new low, update anchor (keeps it honest)
            elif p < anchor:
                anchor = p

        elif direction == -1:
            # looking for a down move from anchor
            if change <= -threshold:
                swings += 1
                direction = +1
                anchor = p
            elif p > anchor:
                anchor = p

    return swings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("history", help="selector_history.jsonl")
    ap.add_argument("--threshold", type=float, default=0.10, help="swing threshold as fraction (0.10 == 10%%)")
    ap.add_argument("--days", type=int, default=7, help="rolling window in days")
    ap.add_argument("--min-swings", type=int, default=3, help="minimum swings/day to be considered")
    ap.add_argument("--out", default="swing_rank.json")
    ap.add_argument("--md", default="swing_rank.md")
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args()

    now = int(time.time())
    cutoff = now - args.days * 86400

    # mint -> day -> list[(ts, price)]
    series: Dict[str, Dict[str, List[Tuple[int, float]]]] = defaultdict(lambda: defaultdict(list))
    meta: Dict[str, Dict[str, Any]] = defaultdict(dict)

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
            if ts < cutoff:
                continue

            for x in (rec.get("passed") or []):
                mint = x.get("mint")
                if not mint:
                    continue
                price = parse_float(x.get("priceUsd"))
                if price is None or price <= 0:
                    continue
                d = day_id(ts)
                series[mint][d].append((ts, price))

                # store meta
                meta[mint]["symbol"] = x.get("symbol")
                meta[mint]["dex"] = x.get("dex")
                meta[mint]["is_pump"] = x.get("is_pump")

    rows: List[Dict[str, Any]] = []

    for mint, by_day in series.items():
        day_counts: Dict[str, int] = {}
        for d, pts in by_day.items():
            pts.sort(key=lambda t: t[0])
            n = count_swings(pts, threshold=args.threshold)
            day_counts[d] = n

        if not day_counts:
            continue

        days_total = len(day_counts)
        total_swings = sum(day_counts.values())
        avg_swings = total_swings / max(1, days_total)
        days_ge_min = sum(1 for v in day_counts.values() if v >= args.min_swings)

        # rank score: prioritize frequency of meeting min-swings, then avg swings
        score = days_ge_min * 1000 + avg_swings

        rows.append({
            "mint": mint,
            "symbol": meta[mint].get("symbol"),
            "is_pump": bool(meta[mint].get("is_pump")),
            "dex": meta[mint].get("dex"),
            "days_seen": days_total,
            "days_ge_min": days_ge_min,
            "avg_swings_per_day": round(avg_swings, 3),
            "total_swings": total_swings,
            "today_swings": day_counts.get(day_id(now), 0),
            "day_counts": day_counts,
            "score": round(score, 3),
        })

    rows.sort(key=lambda r: r["score"], reverse=True)
    top = rows[: args.limit]

    payload = {
        "generated_at": now,
        "window_days": args.days,
        "threshold": args.threshold,
        "min_swings": args.min_swings,
        "ranked": top,
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    lines: List[str] = []
    lines.append(f"# Swing rank (>= {int(args.threshold*100)}% swings, window {args.days}d)")
    lines.append("")
    lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    lines.append("")
    lines.append(f"Minimum swings/day: {args.min_swings}")
    lines.append("")

    for i, r in enumerate(top, 1):
        lines.append(
            f"{i}. **{r.get('symbol')}** ({'pump' if r.get('is_pump') else 'non-pump'}) — "
            f"days>=min: {r['days_ge_min']}/{r['days_seen']}, avg/day: {r['avg_swings_per_day']}, today: {r['today_swings']}\\\n"
            f"   - mint: `{r['mint']}`\\\n"
            f"   - dexscreener: {r.get('dex')}"
        )
        lines.append("")

    with open(args.md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Wrote {args.out} and {args.md} (ranked {len(rows)} mints)")


if __name__ == "__main__":
    main()
