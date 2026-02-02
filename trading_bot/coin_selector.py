#!/usr/bin/env python3
"""Coin selector (Solana-focused, pump.fun-friendly).

Goal: produce a shortlist of "tradeable" coins with a simple health score.

Data sources (no API keys):
- Dexscreener: discovery + liquidity/volume basics
- RugCheck: authority/holder/market risk report (hard-gate)

Defaults are tuned for high-risk memecoin markets; adjust in selector_config.json.

USAGE:
  python coin_selector.py
  python coin_selector.py --out shortlist.json --md shortlist.md --limit 20

NOTES:
- This does NOT place trades.
- This does NOT guarantee safety. It's a landmine filter + ranking tool.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import requests

DEX_SEARCH_URL = "https://api.dexscreener.com/latest/dex/search"
DEX_TOKEN_URL = "https://api.dexscreener.com/latest/dex/tokens/{mint}"
JUP_SEARCH_URL = "https://lite-api.jup.ag/ultra/v1/search"
PUMPFUN_API_BASE = "https://frontend-api-v3.pump.fun"
RUGCHECK_URL = "https://api.rugcheck.xyz/v1/tokens/{mint}/report"

WSOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

DEFAULTS = {
    "chainId": "solana",
    "limit": 20,
    "discover_source": "pumpfun",  # pumpfun | jup | dexscreener
    "discover_query": "pump",  # legacy single-query field
    "discover_queries": ["SOL", "USDC", "Raydium", "Orca"],
    "prefer_pump_suffix": True,
    "candidates_max": 300,  # how many pairs to consider before filtering
    "min_liquidity_usd": 100_000,
    "min_age_minutes": 60,
    "min_volume_h1_usd": 50_000,
    "hard_reject_freeze_authority": True,
    "hard_reject_mint_authority": True,
    "pump_bonus": 0.10,  # +10% score if mint ends with 'pump'
    "request_timeout": 20,
    "sleep_between_rugchecks_ms": 150,
}


def now_ms() -> int:
    return int(time.time() * 1000)


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def log1p_norm(x: float, scale: float) -> float:
    """Log-normalize roughly into 0..1 with a scale where x==scale -> ~0.5-ish."""
    if x <= 0:
        return 0.0
    # Map with log1p and clamp
    return clamp(math.log1p(x) / math.log1p(scale * 4), 0.0, 1.0)


@dataclass
class Candidate:
    pair: Dict[str, Any]
    base_mint: str
    quote_mint: str
    base_symbol: str
    dex_url: str
    liquidity_usd: float
    vol_h1_usd: float
    age_minutes: float
    is_pump: bool


def dexscreener_search(query: str, timeout: int) -> List[Dict[str, Any]]:
    r = requests.get(DEX_SEARCH_URL, params={"q": query}, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    return data.get("pairs", []) or []


def dexscreener_pairs_for_token(mint: str, timeout: int) -> List[Dict[str, Any]]:
    url = DEX_TOKEN_URL.format(mint=mint)
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    return data.get("pairs", []) or []


def jup_search(query: str, timeout: int) -> List[Dict[str, Any]]:
    r = requests.get(JUP_SEARCH_URL, params={"query": query}, timeout=timeout)
    r.raise_for_status()
    return r.json() if r.text else []


def pumpfun_list(endpoint: str, timeout: int) -> Any:
    # Pump.fun APIs often want an Origin header.
    r = requests.get(
        f"{PUMPFUN_API_BASE}{endpoint}",
        headers={"accept": "application/json", "origin": "https://pump.fun"},
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json() if r.text else None


def pumpfun_discover_mints(timeout: int) -> List[str]:
    mints: List[str] = []

    # currently-live appears to return a list with mints
    live = pumpfun_list("/coins/currently-live", timeout=timeout)
    if isinstance(live, list):
        for item in live:
            if isinstance(item, dict) and item.get("mint"):
                mints.append(item["mint"])

    # king-of-the-hill sometimes returns a list or object; handle both
    koth = pumpfun_list("/coins/king-of-the-hill", timeout=timeout)
    if isinstance(koth, list):
        for item in koth:
            if isinstance(item, dict) and item.get("mint"):
                mints.append(item["mint"])
    elif isinstance(koth, dict) and koth.get("mint"):
        mints.append(koth["mint"])

    # de-dupe while preserving order
    seen = set()
    out: List[str] = []
    for m in mints:
        if m not in seen:
            out.append(m)
            seen.add(m)
    return out


def parse_candidate(pair: Dict[str, Any]) -> Optional[Candidate]:
    if pair.get("chainId") != "solana":
        return None

    base = pair.get("baseToken") or {}
    quote = pair.get("quoteToken") or {}
    base_mint = base.get("address") or ""
    quote_mint = quote.get("address") or ""
    if not base_mint or not quote_mint:
        return None

    # Prefer quoting tokens that route well for our world: WSOL/USDC.
    # We'll still allow others, but penalize later if desired.
    liq = float((pair.get("liquidity") or {}).get("usd") or 0)
    vol_h1 = float(((pair.get("volume") or {}).get("h1")) or 0)

    created_at = pair.get("pairCreatedAt")
    if created_at is None:
        # If missing, treat as very new
        age_min = 0.0
    else:
        age_min = max(0.0, (now_ms() - int(created_at)) / 60000.0)

    dex_url = pair.get("url") or ""
    sym = (base.get("symbol") or "").strip() or base_mint[:4]

    is_pump = base_mint.lower().endswith("pump")

    return Candidate(
        pair=pair,
        base_mint=base_mint,
        quote_mint=quote_mint,
        base_symbol=sym,
        dex_url=dex_url,
        liquidity_usd=liq,
        vol_h1_usd=vol_h1,
        age_minutes=age_min,
        is_pump=is_pump,
    )


def rugcheck_report(mint: str, timeout: int) -> Dict[str, Any]:
    url = RUGCHECK_URL.format(mint=mint)
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.json()


def hard_reject(report: Dict[str, Any], cfg: Dict[str, Any]) -> Tuple[bool, List[str]]:
    reasons: List[str] = []

    freeze_auth = report.get("freezeAuthority")
    mint_auth = report.get("mintAuthority")

    if cfg.get("hard_reject_freeze_authority", True) and freeze_auth:
        reasons.append("freezeAuthority present")

    if cfg.get("hard_reject_mint_authority", True) and mint_auth:
        reasons.append("mintAuthority present")

    # If RugCheck includes explicit risks list, optionally fail on critical items.
    risks = report.get("risks")
    if isinstance(risks, list):
        critical = [r for r in risks if isinstance(r, dict) and (r.get("level") in ("danger", "critical"))]
        # Don't hard-fail on this by default because RugCheck can be noisy.
        if critical:
            reasons.append(f"rugcheck critical risks: {len(critical)}")

    return (len(reasons) > 0), reasons


def _num(x: Any) -> float:
    try:
        if x is None:
            return 0.0
        return float(x)
    except Exception:
        return 0.0


def compute_swing_score(pair: Dict[str, Any]) -> Tuple[float, List[str]]:
    """Heuristic swing/chop score (0..1) using only free snapshot fields.

    Intuition:
    - Need activity (txns) and enough volume
    - Want movement (abs % change) but avoid pure one-way trend
    """

    notes: List[str] = []

    pc = pair.get("priceChange") or {}
    tx = pair.get("txns") or {}
    vol = pair.get("volume") or {}
    liq = (pair.get("liquidity") or {}).get("usd")

    pc_m5 = abs(_num(pc.get("m5")))
    pc_h1 = abs(_num(pc.get("h1")))
    pc_h6 = abs(_num(pc.get("h6")))

    # activity: sum buys+sells
    tx_h1 = tx.get("h1") or {}
    buys = _num(tx_h1.get("buys"))
    sells = _num(tx_h1.get("sells"))
    txn_cnt = buys + sells

    vol_h1 = _num(vol.get("h1"))
    liq_usd = _num(liq)

    # normalized components
    move = clamp((pc_h1 / 15.0) + (pc_m5 / 5.0) * 0.5 + (pc_h6 / 40.0) * 0.25, 0.0, 1.0)
    churn = clamp(math.log1p(txn_cnt) / math.log1p(400.0), 0.0, 1.0)
    vliq = 0.0
    if liq_usd > 0:
        vliq = clamp((vol_h1 / liq_usd) / 1.0, 0.0, 1.0)  # 1.0 == vol ~= liq in 1h (very active)

    # trend penalty: if m5/h1/h6 are all same sign and large, it may be trending hard (less mean-reverting)
    raw_m5 = _num(pc.get("m5"))
    raw_h1 = _num(pc.get("h1"))
    raw_h6 = _num(pc.get("h6"))
    same_sign = (raw_m5 > 0 and raw_h1 > 0 and raw_h6 > 0) or (raw_m5 < 0 and raw_h1 < 0 and raw_h6 < 0)
    trend_pen = 0.0
    if same_sign and (abs(raw_h6) > 30.0):
        trend_pen = 0.25
        notes.append("trend-penalty")

    score = 0.45 * churn + 0.40 * move + 0.15 * vliq
    score = clamp(score - trend_pen, 0.0, 1.0)

    if txn_cnt < 50:
        notes.append("low-txns")
    if vol_h1 < 25_000:
        notes.append("low-vol")

    return score, notes


def compute_health_score(c: Candidate, report: Dict[str, Any], cfg: Dict[str, Any]) -> Tuple[float, List[str]]:
    """Return score (0..1) and explanation reasons."""
    reasons: List[str] = []

    # Primary components
    liq_score = log1p_norm(c.liquidity_usd, cfg["min_liquidity_usd"])
    vol_score = log1p_norm(c.vol_h1_usd, cfg["min_volume_h1_usd"])

    # Age: saturate after ~24h.
    age_score = clamp(c.age_minutes / (60.0 * 24.0), 0.0, 1.0)

    # RugCheck score: lower is better.
    rug_norm = report.get("score_normalised")
    if rug_norm is None:
        rug_score = 0.5
        reasons.append("rugcheck score missing")
    else:
        try:
            rn = float(rug_norm)
            rug_score = clamp(1.0 - (rn / 10.0), 0.0, 1.0)
        except Exception:
            rug_score = 0.5
            reasons.append("rugcheck score parse error")

    # pump suffix preference
    prefer_pump = bool(cfg.get("prefer_pump_suffix", True))
    pump_bonus = cfg.get("pump_bonus", 0.0) if (prefer_pump and c.is_pump) else 0.0

    # Weighting: emphasize liquidity + volume + rug score.
    score = (
        0.35 * liq_score
        + 0.30 * vol_score
        + 0.20 * rug_score
        + 0.15 * age_score
    )

    score = score * (1.0 + pump_bonus)
    score = clamp(score, 0.0, 1.0)

    # explanations
    if prefer_pump and c.is_pump:
        reasons.append("pump mint bonus")
    if c.liquidity_usd < cfg["min_liquidity_usd"]:
        reasons.append(f"low liquidity ${c.liquidity_usd:,.0f}")
    if c.vol_h1_usd < cfg["min_volume_h1_usd"]:
        reasons.append(f"low 1h vol ${c.vol_h1_usd:,.0f}")
    if c.age_minutes < cfg["min_age_minutes"]:
        reasons.append(f"young age {c.age_minutes:.0f}m")

    return score, reasons


def load_cfg(path: Optional[str]) -> Dict[str, Any]:
    cfg = dict(DEFAULTS)
    if path:
        with open(path, "r", encoding="utf-8") as f:
            user = json.load(f)
        cfg.update(user)
    return cfg


def main():
    ap = argparse.ArgumentParser(description="Select healthier Solana coins for botting.")
    ap.add_argument("--config", default=None, help="Optional selector_config.json")
    ap.add_argument("--out", default="shortlist.json", help="Output JSON file")
    ap.add_argument("--md", default="shortlist.md", help="Output markdown summary")
    ap.add_argument("--limit", type=int, default=DEFAULTS["limit"], help="How many coins to output (per list)")
    ap.add_argument(
        "--append-history",
        default=None,
        help="Optional path to append JSONL history (one line per run)",
    )
    args = ap.parse_args()

    cfg = load_cfg(args.config)
    cfg["limit"] = args.limit

    # Discovery:
    # - pumpfun: pull live mints from pump.fun, then look up those mints on Dexscreener
    # - jup: use Jupiter search to get mints, then look up on Dexscreener
    # - dexscreener: use several broad queries (SOL/USDC/Raydium/Orca) to get high-activity pairs,
    #   then locally prefer mints ending with 'pump'

    discover_source = (cfg.get("discover_source") or "pumpfun").lower().strip()

    ordered_mints: List[str] = []
    pairs: List[Dict[str, Any]] = []

    if discover_source == "pumpfun":
        try:
            ordered_mints = pumpfun_discover_mints(timeout=cfg["request_timeout"])[: cfg["candidates_max"]]
        except Exception:
            ordered_mints = []

    if not ordered_mints and discover_source in ("pumpfun", "jup"):
        jup_items = jup_search(cfg.get("discover_query") or "pump", timeout=cfg["request_timeout"])
        mints: List[str] = []
        for item in jup_items:
            mid = (item.get("id") or "").strip()
            if mid:
                mints.append(mid)
        ordered_mints = mints[: cfg["candidates_max"]]

    if discover_source == "dexscreener":
        queries = cfg.get("discover_queries") or [cfg.get("discover_query") or "SOL"]
        for q in queries:
            try:
                pairs.extend(dexscreener_search(str(q), timeout=cfg["request_timeout"]))
            except Exception:
                continue
        pairs = pairs[: cfg["candidates_max"]]

    if ordered_mints:
        for mint in ordered_mints:
            try:
                pairs.extend(dexscreener_pairs_for_token(mint, timeout=cfg["request_timeout"]))
            except Exception:
                continue

    # If we still have nothing, last-ditch search
    if not pairs:
        pairs = dexscreener_search(cfg.get("discover_query") or "SOL", timeout=cfg["request_timeout"])[: cfg["candidates_max"]]

    # Parse + prefilter
    candidates: List[Candidate] = []
    # Keep only the best pair per base mint (highest liquidity)
    best_by_mint: Dict[str, Candidate] = {}
    for p in pairs:
        c = parse_candidate(p)
        if not c:
            continue
        prev = best_by_mint.get(c.base_mint)
        if prev is None or c.liquidity_usd > prev.liquidity_usd:
            best_by_mint[c.base_mint] = c

    candidates = list(best_by_mint.values())

    # Soft prefilter to reduce rugcheck calls
    filtered: List[Candidate] = []
    for c in candidates:
        if c.liquidity_usd < cfg["min_liquidity_usd"] * 0.25:
            continue
        filtered.append(c)

    results: List[Dict[str, Any]] = []
    rejects: List[Dict[str, Any]] = []

    for idx, c in enumerate(filtered):
        try:
            report = rugcheck_report(c.base_mint, timeout=cfg["request_timeout"])
        except Exception as e:
            rejects.append(
                {
                    "mint": c.base_mint,
                    "symbol": c.base_symbol,
                    "reason": f"rugcheck fetch failed: {e}",
                    "dex": c.dex_url,
                }
            )
            continue

        rejected, why_reject = hard_reject(report, cfg)
        if rejected:
            rejects.append(
                {
                    "mint": c.base_mint,
                    "symbol": c.base_symbol,
                    "reason": "; ".join(why_reject),
                    "dex": c.dex_url,
                }
            )
        else:
            health, reasons = compute_health_score(c, report, cfg)
            swing, swing_notes = compute_swing_score(c.pair)
            results.append(
                {
                    "mint": c.base_mint,
                    "symbol": c.base_symbol,
                    "health": round(health, 4),
                    "swing": round(swing, 4),
                    "is_pump": c.is_pump,
                    "liquidity_usd": c.liquidity_usd,
                    "volume_h1_usd": c.vol_h1_usd,
                    "age_minutes": c.age_minutes,
                    "dex": c.dex_url,
                    "dex_pair": c.pair.get("pairAddress"),
                    "priceChange": (c.pair.get("priceChange") or {}),
                    "txns": (c.pair.get("txns") or {}),
                    "rugcheck": {
                        "score": report.get("score"),
                        "score_normalised": report.get("score_normalised"),
                        "freezeAuthority": report.get("freezeAuthority"),
                        "mintAuthority": report.get("mintAuthority"),
                    },
                    "notes": reasons,
                    "swing_notes": swing_notes,
                }
            )

        time.sleep(cfg["sleep_between_rugchecks_ms"] / 1000.0)

    safest = sorted(results, key=lambda x: x["health"], reverse=True)
    swingiest = sorted(results, key=lambda x: (x["swing"], x["health"]), reverse=True)

    limit = int(cfg["limit"])
    shortlist_safe = safest[:limit]
    shortlist_swing = swingiest[:limit]

    # Full passed set (sorted by health) so you can inventory all eligible coins
    passed_all = sorted(results, key=lambda x: x["health"], reverse=True)

    payload = {
        "generated_at": int(time.time()),
        "config": {
            k: cfg.get(k)
            for k in [
                "discover_source",
                "discover_query",
                "discover_queries",
                "prefer_pump_suffix",
                "min_liquidity_usd",
                "min_age_minutes",
                "min_volume_h1_usd",
                "hard_reject_freeze_authority",
                "hard_reject_mint_authority",
                "pump_bonus",
                "candidates_max",
            ]
        },
        "lists": {
            "safest": shortlist_safe,
            "swingiest": shortlist_swing,
        },
        "passed": passed_all,
        "counts": {
            "pairs_seen": len(pairs),
            "candidates_parsed": len(candidates),
            "prefiltered": len(filtered),
            "passed": len(results),
            "rejected": len(rejects),
        },
        "rejected_examples": rejects[:50],
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    # Optional history append (JSONL)
    if args.append_history:
        hist_line = {
            "generated_at": payload["generated_at"],
            "config": payload["config"],
            "counts": payload["counts"],
            # store only compact per-coin fields to keep the file sane
            "passed": [
                {
                    "mint": x["mint"],
                    "symbol": x["symbol"],
                    "health": x["health"],
                    "swing": x["swing"],
                    "is_pump": x["is_pump"],
                    "liquidity_usd": x["liquidity_usd"],
                    "volume_h1_usd": x["volume_h1_usd"],
                    "age_minutes": x["age_minutes"],
                    "dex": x["dex"],
                }
                for x in passed_all
            ],
        }
        with open(args.append_history, "a", encoding="utf-8") as hf:
            hf.write(json.dumps(hist_line, separators=(",", ":")) + "\n")

    # Simple markdown summary
    lines: List[str] = []
    lines.append(f"# Shortlists (top {limit} each)")
    lines.append("")
    lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    lines.append("")
    lines.append(f"Passed total: {len(passed_all)}")
    lines.append("")
    lines.append("## Config")
    lines.append("```json")
    lines.append(json.dumps(payload["config"], indent=2))
    lines.append("```")

    def render_list(title: str, items: List[Dict[str, Any]]):
        lines.append("")
        lines.append(f"## {title}")
        lines.append("")
        for i, item in enumerate(items, 1):
            lines.append(
                f"{i}. **{item['symbol']}** ({'pump' if item['is_pump'] else 'non-pump'}) — "
                f"health **{item['health']}**, swing **{item['swing']}**\\\n"
                f"   - liq: ${item['liquidity_usd']:,.0f}, vol1h: ${item['volume_h1_usd']:,.0f}, age: {item['age_minutes']:.0f}m\\\n"
                f"   - pc(m5/h1/h6): {item.get('priceChange',{}).get('m5','?')}/{item.get('priceChange',{}).get('h1','?')}/{item.get('priceChange',{}).get('h6','?')}\\\n"
                f"   - txns(h1): {item.get('txns',{}).get('h1',{})}\\\n"
                f"   - mint: `{item['mint']}`\\\n"
                f"   - dexscreener: {item['dex']}\\\n"
                f"   - notes: {', '.join(item.get('notes') or [])}\\\n"
                f"   - swing_notes: {', '.join(item.get('swing_notes') or [])}"
            )
            lines.append("")

    render_list("Safest (highest health)", shortlist_safe)
    render_list("Swingiest (highest swing, tie-breaker health)", shortlist_swing)

    with open(args.md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Wrote {args.out} and {args.md}")
    print(f"Passed: {len(results)}  Rejected: {len(rejects)}  Safest: {len(shortlist_safe)}  Swingiest: {len(shortlist_swing)}")


if __name__ == "__main__":
    main()
