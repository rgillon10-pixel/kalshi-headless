#!/usr/bin/env python3
"""q42_crossvenue_funding_join.py — Q42 part (2): join Kalshi finalized 8h perp funding
against Hyperliquid's same-underlying hourly funding and characterize the differential
(READ-ONLY, OFFLINE over committed tape).

LOOP-QUEUE.md Q42. Part (1) (`scripts/q42_funding_clamp_probe.py`) proved Kalshi's finalized
funding prints are a GENUINE ±1bp dead-band/clamp — exactly 0 in ~76% of 8h windows pooled
(67% for BTC). The cross-venue thesis: while Kalshi's leg is clamped to 0 most windows,
Hyperliquid's same-underlying funding is essentially never 0, so a long-Kalshi / short-HL
delta-neutral pair pays ~0 on Kalshi and collects HL funding — a mechanical basis. This
script SIZES that differential distribution. It is explicitly NOT a P&L verdict: no fee/carry
model (that is part 3, blocked on an authenticated Kalshi endpoint), no block-bootstrap CI,
no registry change. Every funding number is `broker_truth` (finalized venue prints, not fills).

THE JOIN (apples-to-apples across two funding cadences):
  * Kalshi finalizes funding every 8 HOURS (observed boundaries 04/12/20 UTC — NOT the naive
    0/8/16; the window is anchored to each print's ACTUAL `funding_time` T, never assumed).
  * Hyperliquid pays HOURLY. For a Kalshi print at time T, the matching 8h window is the 8
    hourly HL rates at hours (T-7h … T]. Hours are matched by rounding each timestamp to the
    nearest hour (HL stamps a few ms past :00; a strict `<=` compare would drop the edge row).
  * The 8 hourly HL rates are COMPOUNDED into an 8h-equivalent: prod(1+r)-1 (a simple sum is
    also reported — at ~1e-4/hr the two agree to ~1e-7, so the choice is immaterial, but we
    compound to be honest about the cadence mismatch the task flags).
  * differential = HL 8h-equivalent  -  Kalshi finalized print, per (asset, window).

A window is only joined if all 8 HL hours are present; a partial window (HL history gap /
boundary) is counted and EXCLUDED, never zero-filled (a missing rate is not a zero — same
discipline as part 1). The Kalshi zero-fraction on the JOINED set is reported as a join-sanity
check: it must reproduce part 1's ~67% BTC figure, else the join lost/duplicated windows.

Read-only. NO network. Run:
    python3 scripts/q42_crossvenue_funding_join.py
    python3 scripts/q42_crossvenue_funding_join.py --json-out /tmp/q42j.json
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DEFAULT_PERP_GLOB = "tape/perp_tape/dt=*.jsonl"
DEFAULT_HL_GLOB = "tape/hyperliquid_funding/dt=*.jsonl"
PRICE_SOURCE_TAG = "broker_truth"

# asset -> (kalshi perp ticker, hyperliquid coin). The Kalshi side of part 1 focused on BTC;
# both legs of the deep-liquid pair (perp_tape.L2_TICKERS) are carried. Widen deliberately.
ASSET_MAP = {
    "BTC": {"kalshi_ticker": "KXBTCPERP", "hl_coin": "BTC"},
    "ETH": {"kalshi_ticker": "KXETHPERP", "hl_coin": "ETH"},
}

HOUR_MS = 3600_000
WINDOW_HOURS = 8  # Kalshi finalizes every 8h; each window sums 8 HL hourly rates

# part-1 BTC zero-fraction (66.9%); a joined-set zero-fraction far from this flags a join bug.
PART1_BTC_ZERO_FRACTION = 0.669
JOIN_SANITY_TOLERANCE = 0.05


# --------------------------------------------------------------------------- #
# loading — injectable so tests are fully offline (path/glob OR a record list)
# --------------------------------------------------------------------------- #
def load_records(source: Any) -> List[Dict[str, Any]]:
    """Return a flat list of JSONL records from `source`, which may be a list/tuple of
    already-parsed dicts (returned as-is) or a str/Path to a .jsonl file or glob. Pure:
    no network, no mutation; a path matching nothing yields []."""
    if isinstance(source, (list, tuple)):
        return list(source)
    pattern = str(source)
    paths = sorted(glob.glob(pattern)) if any(c in pattern for c in "*?[") else [pattern]
    records: List[Dict[str, Any]] = []
    for p in paths:
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    return records


def _iso_to_ms(iso: str) -> Optional[int]:
    """Epoch-ms from an ISO8601 '…Z' timestamp, or None on a grammar mismatch."""
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except (ValueError, TypeError):
        return None


def _hour_index(ms: Optional[int]) -> Optional[int]:
    """Round an epoch-ms to its nearest whole hour index (hours since epoch). None-safe."""
    if ms is None:
        return None
    return int(round(ms / HOUR_MS))


# --------------------------------------------------------------------------- #
# collect each leg
# --------------------------------------------------------------------------- #
def collect_kalshi_prints(records: Sequence[Dict[str, Any]], tickers: Sequence[str],
                          mode: str = "backfill") -> List[Dict[str, Any]]:
    """Flatten Kalshi finalized funding prints for the given perp tickers, deduped on
    (market_ticker, funding_time). Only `funding_rates` records of `mode` are read."""
    want = set(tickers)
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for rec in records:
        if rec.get("record_type") != "funding_rates" or rec.get("mode") != mode:
            continue
        for pr in rec.get("prints") or []:
            t = pr.get("market_ticker")
            if t not in want:
                continue
            key = (t, pr.get("funding_time"))
            if key in seen:
                continue
            seen.add(key)
            ms = _iso_to_ms(pr.get("funding_time", ""))
            out.append({
                "ticker": t,
                "funding_time": pr.get("funding_time"),
                "t_ms": ms,
                "hour_index": _hour_index(ms),
                "funding_rate": pr.get("funding_rate"),
            })
    return out


def collect_hl_hourly(records: Sequence[Dict[str, Any]], coins: Sequence[str]
                      ) -> Dict[str, Dict[int, float]]:
    """Build {coin -> {hour_index -> funding_rate}} from HL `funding_history` records,
    deduped on hour_index (keep first; a re-run's overlapping snapshot is idempotent).
    A None rate or unparseable time is skipped (never coerced to 0)."""
    want = set(coins)
    out: Dict[str, Dict[int, float]] = {c: {} for c in want}
    for rec in records:
        if rec.get("record_type") != "funding_history":
            continue
        coin = rec.get("coin")
        if coin not in want:
            continue
        table = out[coin]
        for pr in rec.get("prints") or []:
            r = pr.get("funding_rate")
            hi = _hour_index(pr.get("time_ms"))
            if r is None or hi is None or hi in table:
                continue
            table[hi] = float(r)
    return out


# --------------------------------------------------------------------------- #
# window join
# --------------------------------------------------------------------------- #
def _compound(rates: Sequence[float]) -> float:
    """8h-equivalent of hourly rates: prod(1+r)-1."""
    acc = 1.0
    for r in rates:
        acc *= (1.0 + r)
    return acc - 1.0


def join_asset(kalshi_prints: Sequence[Dict[str, Any]], hl_hours: Dict[int, float]
               ) -> Tuple[List[Dict[str, Any]], int]:
    """Join one asset's Kalshi 8h prints to its HL hourly table. Returns (joined, n_partial).

    A Kalshi print at hour index hT matches HL hours {hT-7 … hT}. Only a window with all 8
    HL hours present is joined; a partial window is counted (n_partial) and excluded."""
    joined: List[Dict[str, Any]] = []
    n_partial = 0
    for kp in kalshi_prints:
        hT = kp.get("hour_index")
        krate = kp.get("funding_rate")
        if hT is None or krate is None:
            continue
        hours = [hT - i for i in range(WINDOW_HOURS - 1, -1, -1)]  # hT-7 … hT
        rates = [hl_hours[h] for h in hours if h in hl_hours]
        if len(rates) < WINDOW_HOURS:
            n_partial += 1
            continue
        hl_compound = _compound(rates)
        hl_sum = math.fsum(rates)
        joined.append({
            "funding_time": kp.get("funding_time"),
            "kalshi_rate": float(krate),
            "hl_8h_compound": hl_compound,
            "hl_8h_sum": hl_sum,
            "hl_n_hours": len(rates),
            "differential": hl_compound - float(krate),
            "price_source_tag": PRICE_SOURCE_TAG,
        })
    return joined, n_partial


# --------------------------------------------------------------------------- #
# descriptive stats (NO bootstrap / NO CI — sizing memo only)
# --------------------------------------------------------------------------- #
def _percentiles(xs: Sequence[float], ps=(0.1, 0.25, 0.5, 0.75, 0.9)) -> Dict[str, float]:
    if not xs:
        return {f"p{int(p*100)}": None for p in ps}
    s = sorted(xs)
    out = {}
    for p in ps:
        # linear-interpolation percentile
        idx = p * (len(s) - 1)
        lo = int(math.floor(idx))
        hi = int(math.ceil(idx))
        frac = idx - lo
        out[f"p{int(p*100)}"] = s[lo] + (s[hi] - s[lo]) * frac
    return out


def _tercile_split(joined: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Split joined windows into terciles by |hl_8h_compound| (the thesis: the differential
    the pair harvests concentrates when HL funding is large). Reports each tercile's n and
    the differential mean/median — a direct read of 'does the basis blow out with HL spikes'."""
    if len(joined) < 3:
        return []
    by_mag = sorted(joined, key=lambda w: abs(w["hl_8h_compound"]))
    n = len(by_mag)
    cuts = [by_mag[: n // 3], by_mag[n // 3: 2 * n // 3], by_mag[2 * n // 3:]]
    labels = ["low|HL|", "mid|HL|", "high|HL|"]
    out = []
    for label, grp in zip(labels, cuts):
        diffs = [w["differential"] for w in grp]
        mags = [abs(w["hl_8h_compound"]) for w in grp]
        out.append({
            "tercile": label, "n": len(grp),
            "abs_hl_range": [min(mags), max(mags)] if mags else [None, None],
            "diff_mean": statistics.fmean(diffs) if diffs else None,
            "diff_median": statistics.median(diffs) if diffs else None,
        })
    return out


def _sign_split(joined: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Split by sign of the HL 8h rate (which way the delta-neutral carry points). n + mean
    differential per side; the exactly-0 HL side is reported separately (expected empty)."""
    pos = [w for w in joined if w["hl_8h_compound"] > 0]
    neg = [w for w in joined if w["hl_8h_compound"] < 0]
    zero = [w for w in joined if w["hl_8h_compound"] == 0]
    return {
        "hl_positive": {"n": len(pos),
                        "diff_mean": statistics.fmean([w["differential"] for w in pos]) if pos else None},
        "hl_negative": {"n": len(neg),
                        "diff_mean": statistics.fmean([w["differential"] for w in neg]) if neg else None},
        "hl_zero": {"n": len(zero)},
    }


def characterize_asset(joined: Sequence[Dict[str, Any]], n_partial: int,
                       full_pop_zero_fraction: Optional[float] = None,
                       is_btc: bool = False) -> Dict[str, Any]:
    diffs = [w["differential"] for w in joined]
    krates = [w["kalshi_rate"] for w in joined]
    hl_c = [w["hl_8h_compound"] for w in joined]
    n = len(joined)
    kalshi_zero = sum(1 for r in krates if r == 0.0)
    hl_zero = sum(1 for r in hl_c if r == 0.0)
    kalshi_zero_frac = (kalshi_zero / n) if n else None
    # join sanity: the joined-set Kalshi zero-fraction must match this asset's FULL-population
    # zero-fraction (else the join silently dropped/duplicated windows). For BTC we ALSO pin it
    # against part 1's published 0.669 as an external cross-check.
    sanity = None
    if kalshi_zero_frac is not None:
        sanity = {
            "full_population_zero_fraction": full_pop_zero_fraction,
            "tolerance": JOIN_SANITY_TOLERANCE,
            "joined_matches_full_population":
                (full_pop_zero_fraction is None
                 or abs(kalshi_zero_frac - full_pop_zero_fraction) <= JOIN_SANITY_TOLERANCE),
        }
        if is_btc:
            sanity["expected_part1_btc"] = PART1_BTC_ZERO_FRACTION
            sanity["within_tolerance_of_part1_btc"] = (
                abs(kalshi_zero_frac - PART1_BTC_ZERO_FRACTION) <= JOIN_SANITY_TOLERANCE)
    return {
        "n_windows_joined": n,
        "n_windows_partial_excluded": n_partial,
        "kalshi_zero_count": kalshi_zero,
        "kalshi_zero_fraction": kalshi_zero_frac,
        "hl_zero_count": hl_zero,
        "hl_zero_fraction": (hl_zero / n) if n else None,
        "kalshi_rate_mean": statistics.fmean(krates) if krates else None,
        "hl_8h_compound_mean": statistics.fmean(hl_c) if hl_c else None,
        "hl_8h_compound_median": statistics.median(hl_c) if hl_c else None,
        "differential_mean": statistics.fmean(diffs) if diffs else None,
        "differential_median": statistics.median(diffs) if diffs else None,
        "differential_percentiles": _percentiles(diffs),
        "regime_tercile_by_abs_hl": _tercile_split(joined),
        "regime_sign_of_hl": _sign_split(joined),
        "join_sanity": sanity,
        "price_source_tag": PRICE_SOURCE_TAG,
    }


def analyze(perp_records: Sequence[Dict[str, Any]], hl_records: Sequence[Dict[str, Any]],
            asset_map: Dict[str, Dict[str, str]] = ASSET_MAP,
            mode: str = "backfill") -> Dict[str, Any]:
    """End-to-end per-asset cross-venue join + characterization. JSON-able report."""
    tickers = [v["kalshi_ticker"] for v in asset_map.values()]
    coins = [v["hl_coin"] for v in asset_map.values()]
    kalshi_all = collect_kalshi_prints(perp_records, tickers, mode=mode)
    hl_tables = collect_hl_hourly(hl_records, coins)

    per_asset: Dict[str, Any] = {}
    for asset, spec in asset_map.items():
        kp = [p for p in kalshi_all if p["ticker"] == spec["kalshi_ticker"]]
        hl_hours = hl_tables.get(spec["hl_coin"], {})
        joined, n_partial = join_asset(kp, hl_hours)
        # full-population Kalshi zero-fraction (ALL prints, not just joined) — the join-sanity
        # anchor: joined must reproduce it (0 dropped/duplicated windows).
        kp_rated = [p["funding_rate"] for p in kp if p["funding_rate"] is not None]
        full_pop_zf = (sum(1 for r in kp_rated if r == 0.0) / len(kp_rated)) if kp_rated else None
        per_asset[asset] = {
            "kalshi_ticker": spec["kalshi_ticker"],
            "hl_coin": spec["hl_coin"],
            "n_kalshi_prints": len(kp),
            "n_hl_hours": len(hl_hours),
            "kalshi_full_population_zero_fraction": full_pop_zf,
            **characterize_asset(joined, n_partial, full_pop_zero_fraction=full_pop_zf,
                                 is_btc=(spec["hl_coin"] == "BTC")),
        }
    return {
        "price_source_tag": PRICE_SOURCE_TAG,
        "mode": mode,
        "window_hours": WINDOW_HOURS,
        "assets": per_asset,
    }


# --------------------------------------------------------------------------- #
# reporting
# --------------------------------------------------------------------------- #
def _f(v: Optional[float], nd: int = 6) -> str:
    return "None" if v is None else f"{v:.{nd}f}"


def _print_report(rep: Dict[str, Any]) -> None:
    print("=" * 100)
    print("Q42 (2) — KALSHI vs HYPERLIQUID CROSS-VENUE FUNDING JOIN (read-only, offline)")
    print("=" * 100)
    print(f"source_tag={rep['price_source_tag']}  mode={rep['mode']}  "
          f"window_hours={rep['window_hours']}  (differential = HL 8h-equiv − Kalshi print)")
    for asset, a in rep["assets"].items():
        print("-" * 100)
        print(f"[{asset}]  kalshi={a['kalshi_ticker']}  hl_coin={a['hl_coin']}  "
              f"kalshi_prints={a['n_kalshi_prints']}  hl_hours={a['n_hl_hours']}")
        print(f"  windows joined={a['n_windows_joined']}  "
              f"partial_excluded={a['n_windows_partial_excluded']}")
        print(f"  Kalshi zero-fraction (joined set) = {_f(a['kalshi_zero_fraction'], 4)}  "
              f"({a['kalshi_zero_count']}/{a['n_windows_joined']})   "
              f"[full-pop {_f(a['kalshi_full_population_zero_fraction'], 4)}]")
        s = a.get("join_sanity")
        if s is not None:
            msg = f"    join-sanity: joined matches full-population = {s['joined_matches_full_population']}"
            if "within_tolerance_of_part1_btc" in s:
                msg += (f"   |   part1-BTC cross-check ({PART1_BTC_ZERO_FRACTION}) = "
                        f"{s['within_tolerance_of_part1_btc']}")
            print(msg)
        print(f"  HL zero-fraction (joined set)     = {_f(a['hl_zero_fraction'], 4)}  "
              f"({a['hl_zero_count']}/{a['n_windows_joined']})")
        print(f"  Kalshi rate mean = {_f(a['kalshi_rate_mean'], 8)}   "
              f"HL 8h-equiv mean = {_f(a['hl_8h_compound_mean'], 8)}  "
              f"median = {_f(a['hl_8h_compound_median'], 8)}")
        print(f"  DIFFERENTIAL  mean={_f(a['differential_mean'], 8)}  "
              f"median={_f(a['differential_median'], 8)}")
        pcts = a["differential_percentiles"]
        print("  differential percentiles: " +
              "  ".join(f"{k}={_f(v, 8)}" for k, v in pcts.items()))
        print("  regime — tercile by |HL 8h|:")
        for t in a["regime_tercile_by_abs_hl"]:
            rng = t["abs_hl_range"]
            print(f"    {t['tercile']:<9} n={t['n']:>4}  |HL| in "
                  f"[{_f(rng[0],8)},{_f(rng[1],8)}]  "
                  f"diff_mean={_f(t['diff_mean'],8)}  diff_median={_f(t['diff_median'],8)}")
        sg = a["regime_sign_of_hl"]
        print(f"  regime — sign of HL 8h:  pos n={sg['hl_positive']['n']} "
              f"diff_mean={_f(sg['hl_positive']['diff_mean'],8)}   "
              f"neg n={sg['hl_negative']['n']} "
              f"diff_mean={_f(sg['hl_negative']['diff_mean'],8)}   "
              f"zero n={sg['hl_zero']['n']}")
    print("=" * 100)
    print("NOTE: characterization / sizing memo only — NOT a P&L verdict (no fee/carry model, "
          "no bootstrap CI). Both legs broker_truth (finalized venue prints, not fills).")
    print("=" * 100)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Q42 (2) — Kalshi vs Hyperliquid cross-venue funding join (offline)")
    ap.add_argument("--perp-tape", default=DEFAULT_PERP_GLOB,
                    help="Kalshi perp tape path/glob (default: %(default)s)")
    ap.add_argument("--hl-tape", default=DEFAULT_HL_GLOB,
                    help="Hyperliquid funding tape path/glob (default: %(default)s)")
    ap.add_argument("--mode", default="backfill", choices=["backfill", "recent"])
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    perp_records = load_records(args.perp_tape)
    hl_records = load_records(args.hl_tape)
    rep = analyze(perp_records, hl_records, mode=args.mode)
    _print_report(rep)

    if args.json_out:
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "price_source_tag": PRICE_SOURCE_TAG,
            "perp_tape": args.perp_tape,
            "hl_tape": args.hl_tape,
            "report": rep,
        }
        Path(args.json_out).write_text(json.dumps(payload, indent=2, default=str))
        print(f"[q42-join] wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
