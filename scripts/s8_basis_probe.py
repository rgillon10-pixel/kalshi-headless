#!/usr/bin/env python3
"""s8_basis_probe.py — S8 crypto-hourly settlement-basis first cut (LOOP-QUEUE.md Q5).

The hypothesis: Kalshi settles KXBTC/KXETH hourly brackets on the CF Benchmarks BRRNY/BRTI
index (a ~60s cross-exchange TWAP), while a retail trader prices the book off a single
visible spot print (e.g. Coinbase). If that index genuinely diverges from spot by more than
a rounding error, brackets near a $100 strike boundary could be mispriced relative to the
index that actually settles them — unlike the weather case (NWS vs WU, ρ=0.99999: two
sensors reporting the *same* physical reading, dead on arrival).

Q5's own spec: run the ρ-guard FIRST — if spot-vs-settle move together with no meaningful
residual, the feed-mismatch thesis dies cheap. Only if it survives does a real basis-vs-
overround comparison + block-bootstrap (by hour) make sense.

A naive Pearson ρ on raw price *levels* is close to useless here on its own: BTC's spot and
settle both track the same intraday trend, so ρ→1 is close to guaranteed regardless of
whether there's an exploitable gap (unlike two temperature sensors, there's no reason two
price series both roughly following the same asset over a few hours would NOT correlate on
levels). This script reports ρ for continuity with the weather precedent, but treats the
decision-relevant number as the **dollar gap** (settle − spot) measured against the $100
bracket width — that's the unit that actually matters for "did the wrong bracket get the
better ask."

Known confound, stated plainly: the paired (settle, spot) tape wasn't built for this precise
question — `previous_settlement` is the exact index value AT the hour boundary, but `spot` is
whatever Coinbase/Kraken printed when the pass happened to run (0-50 min later per the VPS
:23 / cloud :53 cadence). So the measured gap mixes any genuine feed mismatch with ordinary
price drift over that lag. This first cut can only be a conservative *upper bound* on the true
instant-of-settlement gap, not the number itself — noted per-record via `lag_seconds`, and any
verdict this script reaches is bounded by that caveat, not a final answer.

Second question this script answers (registry flag, un-investigated since Q2): is the +$9.27
BTC / +$1.23 ETH bracket overround real mispricing, or an artifact of ~180 deep-out-of-the-
money bands all pinned at Kalshi's 1c minimum ask? Composition breakdown below.

Read-only over `tape/crypto_hourly/*.jsonl`. No network calls.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.io import REPO_ROOT
from core.stats import MIN_MEMBERS, safe_pstdev

TAPE_DIR = REPO_ROOT / "tape" / "crypto_hourly"
BAND_WIDTH_DOLLARS = 100.0
YES_ASK_FLOOR = 0.01


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def load_records(tape_dir: Path = TAPE_DIR) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for path in sorted(tape_dir.glob("dt=*.jsonl")):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    return records


@dataclass
class HourPair:
    symbol: str
    event_ticker: str
    settle_value: float
    spot_price: float
    lag_seconds: float
    captured_at: str


def dedupe_settled_hours(records: List[Dict[str, Any]]) -> List[HourPair]:
    """One row per (symbol, settled event_ticker): the earliest pass_complete capture of it
    (smallest lag from the settlement instant), so a duplicate VPS+cloud pass on the same
    hour doesn't double-count a block in the eventual bootstrap."""
    best: Dict[Tuple[str, str], HourPair] = {}
    for r in records:
        ps = r.get("previous_settlement", {})
        if ps.get("status") != "settled":
            continue
        if ps.get("expiration_values_disagree"):
            continue  # disagreeing settle sources — not a clean point, drop rather than guess
        expv = ps.get("expiration_value")
        spot = r.get("spot", {})
        if expv is None or "price" not in spot:
            continue
        current = r.get("current", {})
        open_time = current.get("open_time")
        if not open_time:
            continue
        settle_close = _parse_iso(open_time)
        captured_at = r["captured_at"]
        lag = (_parse_iso(captured_at) - settle_close).total_seconds()
        if lag < 0:
            continue  # captured before the hour it's settling actually closed — malformed

        key = (r["symbol"], ps["event_ticker"])
        cand = HourPair(
            symbol=r["symbol"], event_ticker=ps["event_ticker"],
            settle_value=float(expv), spot_price=float(spot["price"]),
            lag_seconds=lag, captured_at=captured_at,
        )
        prev = best.get(key)
        if prev is None or cand.lag_seconds < prev.lag_seconds:
            best[key] = cand
    return list(best.values())


def pearson(xs: List[float], ys: List[float]) -> Optional[float]:
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return None
    return cov / (vx * vy) ** 0.5


def basis_report(pairs: List[HourPair]) -> Dict[str, Any]:
    by_symbol: Dict[str, List[HourPair]] = {}
    for p in pairs:
        by_symbol.setdefault(p.symbol, []).append(p)

    out: Dict[str, Any] = {}
    for symbol, ps in sorted(by_symbol.items()):
        settle = [p.settle_value for p in ps]
        spot = [p.spot_price for p in ps]
        gap = [s - sp for s, sp in zip(settle, spot)]
        gap_bps = [g / sp * 1e4 for g, sp in zip(gap, spot)]
        n = len(ps)
        entry: Dict[str, Any] = {
            "n_hours": n,
            "mean_lag_seconds": sum(p.lag_seconds for p in ps) / n if n else None,
            "rho_settle_vs_spot_level": pearson(settle, spot),
            "mean_gap_dollars": sum(gap) / n if n else None,
            "mean_gap_bps": sum(gap_bps) / n if n else None,
            "max_abs_gap_dollars": max(abs(g) for g in gap) if gap else None,
            "frac_hours_gap_over_half_band": (
                sum(1 for g in gap if abs(g) > BAND_WIDTH_DOLLARS / 2) / n if n else None
            ),
        }
        if n >= MIN_MEMBERS:
            entry["stdev_gap_dollars"] = safe_pstdev(gap)
        else:
            entry["stdev_gap_dollars"] = None
            entry["stdev_note"] = f"n={n} < MIN_MEMBERS={MIN_MEMBERS} (Hard Rule #2) — not computed"
        out[symbol] = entry
    return out


def overround_composition(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """For every successfully-captured 'current' bracket book: how much of bracket_sum's
    excess over 1.0 comes from outcomes pinned at Kalshi's 1c minimum ask (deep out-of-the-
    money, can't price any lower no matter how remote) vs from the rest of the ladder."""
    by_symbol: Dict[str, List[Dict[str, Any]]] = {}
    for r in records:
        cur = r.get("current", {})
        if cur.get("status") != "ok" or not cur.get("completeness_ok"):
            continue
        by_symbol.setdefault(r["symbol"], []).append(cur)

    out: Dict[str, Any] = {}
    for symbol, curs in sorted(by_symbol.items()):
        n_passes = len(curs)
        floor_sum_total = 0.0
        nonfloor_sum_total = 0.0
        floor_count_total = 0
        member_count_total = 0
        bracket_sum_total = 0.0
        for cur in curs:
            outcomes = cur.get("outcomes", [])
            member_count_total += len(outcomes)
            bracket_sum_total += cur.get("bracket_sum") or 0.0
            for o in outcomes:
                ya = o.get("yes_ask")
                if ya is None:
                    continue
                if ya <= YES_ASK_FLOOR:
                    floor_sum_total += ya
                    floor_count_total += 1
                else:
                    nonfloor_sum_total += ya
        overround_total = bracket_sum_total - n_passes  # each pass's coherent-market baseline is 1.0
        out[symbol] = {
            "n_passes": n_passes,
            "mean_member_count": member_count_total / n_passes if n_passes else None,
            "mean_overround_absorbed": overround_total / n_passes if n_passes else None,
            "mean_floor_pinned_count": floor_count_total / n_passes if n_passes else None,
            "floor_share_of_bracket_sum": (
                floor_sum_total / bracket_sum_total if bracket_sum_total else None
            ),
            # The decision-relevant split: of the *excess over 1.0* (the overround itself,
            # not the whole bracket_sum), how much is mechanically forced by ~170 deep-OTM
            # bands sitting at Kalshi's 1c minimum ask (an exchange floor, not a probability
            # judgment) vs. how much comes from the handful of near-the-money bands where a
            # real bid-ask spread decision is being made.
            # floor_sum_total is treated as ~all excess: a coherent market prices a deep-OTM
            # band near 0, not 0.01, so its true "fair" contribution is ~0 and its whole 1c
            # counts as overround. The complement is what the near-the-money bands add on
            # top of their own genuine (~1.0-summing) probability mass.
            "floor_share_of_overround": (
                floor_sum_total / overround_total if overround_total else None
            ),
            "nonfloor_share_of_overround": (
                1 - (floor_sum_total / overround_total) if overround_total else None
            ),
        }
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="S8 crypto settlement-basis first cut (read-only)")
    ap.add_argument("--tape-dir", default=str(TAPE_DIR))
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    records = load_records(Path(args.tape_dir))
    pairs = dedupe_settled_hours(records)
    basis = basis_report(pairs)
    overround = overround_composition(records)

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_records_total": len(records),
        "n_settled_hour_pairs": len(pairs),
        "basis_by_symbol": basis,
        "overround_composition_by_symbol": overround,
    }

    print(f"[s8_basis_probe] {len(records)} records, {len(pairs)} unique settled-hour pairs")
    for symbol, entry in basis.items():
        print(f"  {symbol}: n={entry['n_hours']} rho(level)={entry['rho_settle_vs_spot_level']!r} "
              f"mean_gap=${entry['mean_gap_dollars']:+.2f} "
              f"({entry['mean_gap_bps']:+.1f}bps) "
              f"max_abs_gap=${entry['max_abs_gap_dollars']:.2f} "
              f"frac>half-band={entry['frac_hours_gap_over_half_band']:.2%} "
              f"mean_lag={entry['mean_lag_seconds']:.0f}s")
    for symbol, entry in overround.items():
        print(f"  {symbol} overround: n_passes={entry['n_passes']} "
              f"mean_overround=${entry['mean_overround_absorbed']:+.2f} "
              f"floor_pinned_outcomes/pass={entry['mean_floor_pinned_count']:.1f} "
              f"floor_share_of_bracket_sum={entry['floor_share_of_bracket_sum']:.1%} "
              f"floor_share_of_OVERROUND={entry['floor_share_of_overround']:.1%} "
              f"nonfloor_share_of_OVERROUND={entry['nonfloor_share_of_overround']:.1%}")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, indent=2))
        print(f"[s8_basis_probe] wrote {args.json_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
