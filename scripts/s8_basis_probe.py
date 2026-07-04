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

Known confound in the LIVE-spot mode (default), stated plainly: the paired (settle, spot)
tape wasn't built for this precise question — `previous_settlement` is the exact index value
AT the hour boundary, but `spot` is whatever Coinbase/Kraken printed when the pass happened to
run (0-50 min later per the VPS :23 / cloud :53 cadence). So the measured gap mixes any genuine
feed mismatch with ordinary price drift over that lag. This first cut can only be a
conservative *upper bound* on the true instant-of-settlement gap, not the number itself — noted
per-record via `lag_seconds`.

`--historical-spot` fixes the confound: it fetches Coinbase's free, keyless `/candles` endpoint
(granularity=60) for the exact minute-bucket at each settlement's boundary instant (Kalshi's
hourly grid always lands on a UTC minute, confirmed empirically 2026-07-04) and uses that
candle's `open` price instead of the lagged live snapshot — lag drops from ~29min to ≤60s.
Fetched candles are cached to `tape/crypto_hourly_historical_spot/` (raw-bytes sha256,
`synthetic` tag — a historical print is still an external reference price, never a Kalshi
fill) so a rerun doesn't re-hit the endpoint for hours already resolved.

Second question this script answers (registry flag, un-investigated since Q2): is the +$9.27
BTC / +$1.23 ETH bracket overround real mispricing, or an artifact of ~180 deep-out-of-the-
money bands all pinned at Kalshi's 1c minimum ask? Composition breakdown below.

Read-only over `tape/crypto_hourly/*.jsonl` by default. `--historical-spot` additionally makes
GET requests to Coinbase's public candles endpoint (read-only market data, no key, no order).
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

from collection.crypto_hourly import COINBASE_BASE, COINBASE_PRODUCT, _UA
from core.canonical import canonical_json, sha256_hex
from core.io import REPO_ROOT
from core.stats import MIN_MEMBERS, safe_pstdev

TAPE_DIR = REPO_ROOT / "tape" / "crypto_hourly"
HISTORICAL_SPOT_TAPE_DIR = REPO_ROOT / "tape" / "crypto_hourly_historical_spot"
# Bracket strike spacing differs by symbol (empirically confirmed live 2026-07-04: BTC
# ladders step $100, ETH steps $20) — a fixed $100 width would understate how much of ETH's
# gap distribution crosses half a band. Falls back to $100 for an unrecognized symbol.
BAND_WIDTH_DOLLARS_BY_SYMBOL = {"BTC": 100.0, "ETH": 20.0}
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
    settle_close_iso: str  # the settlement boundary instant (previous hour's close = this hour's open)


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
            settle_close_iso=open_time,
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
        band_width = BAND_WIDTH_DOLLARS_BY_SYMBOL.get(symbol, 100.0)
        entry: Dict[str, Any] = {
            "n_hours": n,
            "mean_lag_seconds": sum(p.lag_seconds for p in ps) / n if n else None,
            "rho_settle_vs_spot_level": pearson(settle, spot),
            "mean_gap_dollars": sum(gap) / n if n else None,
            "mean_gap_bps": sum(gap_bps) / n if n else None,
            "max_abs_gap_dollars": max(abs(g) for g in gap) if gap else None,
            "frac_hours_gap_over_half_band": (
                sum(1 for g in gap if abs(g) > band_width / 2) / n if n else None
            ),
        }
        if n >= MIN_MEMBERS:
            entry["stdev_gap_dollars"] = safe_pstdev(gap)
        else:
            entry["stdev_gap_dollars"] = None
            entry["stdev_note"] = f"n={n} < MIN_MEMBERS={MIN_MEMBERS} (Hard Rule #2) — not computed"
        out[symbol] = entry
    return out


# --------------------------------------------------------------------------- #
# historical spot — fixes the ~29min live-spot lag confound (network, cached)
# --------------------------------------------------------------------------- #
def fetch_historical_spot_coinbase(symbol: str, at: datetime, timeout: float = 15) -> Dict[str, Any]:
    """The Coinbase 1-minute candle for the exact minute-bucket containing `at` (a settlement
    boundary instant). Kalshi's hourly grid always lands on a UTC minute, so the requested
    bucket's own start time equals `at`'s epoch exactly when the data exists — no nearest-
    match guessing. A missing bucket (exchange gap) is recorded honestly, never interpolated."""
    product = COINBASE_PRODUCT[symbol]
    target_epoch = int(at.timestamp())
    start = at.isoformat().replace("+00:00", "Z")
    end = (at + timedelta(seconds=60)).isoformat().replace("+00:00", "Z")
    try:
        r = requests.get(f"{COINBASE_BASE}/products/{product}/candles",
                          params={"start": start, "end": end, "granularity": 60},
                          timeout=timeout, headers=_UA)
        r.raise_for_status()
        raw_text = r.text
        candles = json.loads(raw_text)
    except Exception as exc:
        return {"status": "fetch_error", "error": str(exc), "price_source_tag": "synthetic"}

    match = next((c for c in candles if int(c[0]) == target_epoch), None)
    if match is None:
        return {"status": "no_candle", "target_epoch": target_epoch,
                "raw_sha256": sha256_hex(raw_text), "price_source_tag": "synthetic"}
    return {
        "status": "ok", "source": "coinbase_historical", "product": product,
        "candle_epoch": int(match[0]), "price": float(match[3]),  # open of the matching minute
        "lag_seconds": int(match[0]) - target_epoch,
        "raw_sha256": sha256_hex(raw_text), "price_source_tag": "synthetic",
    }


def load_or_fetch_historical_spot(
    pairs: List[HourPair], tape_dir: Path = HISTORICAL_SPOT_TAPE_DIR,
    fetcher: Callable[[str, datetime], Dict[str, Any]] = fetch_historical_spot_coinbase,
) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """One cached historical-spot record per (symbol, event_ticker) — reruns after the first
    reuse the cache instead of re-hitting Coinbase for hours already resolved."""
    cached: Dict[Tuple[str, str], Dict[str, Any]] = {}
    if tape_dir.exists():
        for path in sorted(tape_dir.glob("dt=*.jsonl")):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    cached[(rec["symbol"], rec["event_ticker"])] = rec

    new_lines: List[str] = []
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for p in pairs:
        key = (p.symbol, p.event_ticker)
        if key in cached:
            continue
        fetched = fetcher(p.symbol, _parse_iso(p.settle_close_iso))
        rec = {
            "schema_version": "crypto_hourly_historical_spot.v1",
            "symbol": p.symbol, "event_ticker": p.event_ticker,
            "settle_close_iso": p.settle_close_iso,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            **fetched,
        }
        cached[key] = rec
        new_lines.append(canonical_json(rec))

    if new_lines:
        tape_dir.mkdir(parents=True, exist_ok=True)
        with open(tape_dir / f"dt={day}.jsonl", "a", encoding="utf-8") as f:
            for ln in new_lines:
                f.write(ln + "\n")
    return cached


def corrected_basis_report(
    pairs: List[HourPair], historical_by_key: Dict[Tuple[str, str], Dict[str, Any]],
) -> Dict[str, Any]:
    """Same shape as basis_report, but settle is paired against the historical-spot price at
    the boundary instant instead of the lagged live snapshot. Pairs whose historical fetch
    failed/gapped are dropped from the n (never a fabricated substitute) — reported via
    `n_dropped_no_historical_spot`."""
    by_symbol: Dict[str, List[Tuple[float, float, int]]] = {}
    dropped: Dict[str, int] = {}
    for p in pairs:
        hist = historical_by_key.get((p.symbol, p.event_ticker))
        if hist is None or hist.get("status") != "ok":
            dropped[p.symbol] = dropped.get(p.symbol, 0) + 1
            continue
        by_symbol.setdefault(p.symbol, []).append(
            (p.settle_value, hist["price"], hist["lag_seconds"]))

    out: Dict[str, Any] = {}
    for symbol, triples in sorted(by_symbol.items()):
        settle = [t[0] for t in triples]
        spot = [t[1] for t in triples]
        lag = [t[2] for t in triples]
        gap = [s - sp for s, sp in zip(settle, spot)]
        gap_bps = [g / sp * 1e4 for g, sp in zip(gap, spot)]
        n = len(triples)
        band_width = BAND_WIDTH_DOLLARS_BY_SYMBOL.get(symbol, 100.0)
        entry: Dict[str, Any] = {
            "n_hours": n,
            "n_dropped_no_historical_spot": dropped.get(symbol, 0),
            "mean_lag_seconds": sum(lag) / n if n else None,
            "max_lag_seconds": max(lag) if lag else None,
            "rho_settle_vs_spot_level": pearson(settle, spot),
            "mean_gap_dollars": sum(gap) / n if n else None,
            "mean_gap_bps": sum(gap_bps) / n if n else None,
            "max_abs_gap_dollars": max(abs(g) for g in gap) if gap else None,
            "frac_hours_gap_over_half_band": (
                sum(1 for g in gap if abs(g) > band_width / 2) / n if n else None
            ),
        }
        if n >= MIN_MEMBERS:
            entry["stdev_gap_dollars"] = safe_pstdev(gap)
        else:
            entry["stdev_gap_dollars"] = None
            entry["stdev_note"] = f"n={n} < MIN_MEMBERS={MIN_MEMBERS} (Hard Rule #2) — not computed"
        out[symbol] = entry
    for symbol, n_dropped in dropped.items():
        out.setdefault(symbol, {"n_hours": 0, "n_dropped_no_historical_spot": n_dropped})
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
    ap.add_argument("--historical-spot", action="store_true",
                     help="fetch Coinbase historical candles at the settlement instant "
                          "(network; fixes the ~29min live-spot lag confound)")
    ap.add_argument("--historical-spot-tape-dir", default=str(HISTORICAL_SPOT_TAPE_DIR))
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
        print(f"  {symbol} (LIVE spot, lagged): n={entry['n_hours']} "
              f"rho(level)={entry['rho_settle_vs_spot_level']!r} "
              f"mean_gap=${entry['mean_gap_dollars']:+.2f} "
              f"({entry['mean_gap_bps']:+.1f}bps) "
              f"max_abs_gap=${entry['max_abs_gap_dollars']:.2f} "
              f"frac>half-band={entry['frac_hours_gap_over_half_band']:.2%} "
              f"mean_lag={entry['mean_lag_seconds']:.0f}s")

    if args.historical_spot:
        historical = load_or_fetch_historical_spot(pairs, Path(args.historical_spot_tape_dir))
        corrected = corrected_basis_report(pairs, historical)
        result["basis_by_symbol_historical_spot"] = corrected
        for symbol, entry in corrected.items():
            if entry["n_hours"] == 0:
                print(f"  {symbol} (HISTORICAL spot): 0 usable hours, "
                      f"{entry['n_dropped_no_historical_spot']} dropped (fetch error/gap)")
                continue
            print(f"  {symbol} (HISTORICAL spot, lag<=~60s): n={entry['n_hours']} "
                  f"dropped={entry['n_dropped_no_historical_spot']} "
                  f"rho(level)={entry['rho_settle_vs_spot_level']!r} "
                  f"mean_gap=${entry['mean_gap_dollars']:+.2f} "
                  f"({entry['mean_gap_bps']:+.1f}bps) "
                  f"max_abs_gap=${entry['max_abs_gap_dollars']:.2f} "
                  f"frac>half-band={entry['frac_hours_gap_over_half_band']:.2%} "
                  f"mean_lag={entry['mean_lag_seconds']:.1f}s "
                  f"max_lag={entry['max_lag_seconds']}s")

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
