#!/usr/bin/env python3
"""Seed 5 — perp-funding directional prior on Kalshi crypto-hourly ladders (read-only probe).

HYPOTHESIS (falsifiable): elevated perpetual funding at a Kalshi crypto-hourly window's
open is a directional prior for the within-hour settle side that the range-ladder
underprices — enough to clear the TAKER round-trip on the ACTIVE (fillable) band.

This is a PROVISIONAL first-cut SCOPING probe, explicitly NOT a graduation. The honest
prior is NULL: within-hour crypto direction is ~martingale and funding is a slow 8h signal
against a 1h horizon.

Nearest dead cousins respected:
  - S8 (settlement-feed basis, DEAD): that was a spot-vs-CF-BRRNY feed gap (rho 0.9997).
    This is a return-DIRECTION prior, a different object — we do NOT re-test settlement corr.
  - S10 (reachability, STRUCTURAL DEAD): the far wings are 1c-YES-floor-pinned and mirror to
    a $1.00 NO ask (no fillable price). We therefore trade ONLY the ACTIVE band — brackets
    whose RAW yes_ask sits meaningfully off both pins. No fillable ask on the implied side =>
    no trade, counted honestly, never a synthetic fill.

PRICE-SOURCE TAGS (CLAUDE.md trust defaults):
  - Kalshi bracket asks / entry price ............ real_ask  (exchange BBO)
  - Kalshi settlement (winning bracket + value) .. broker_truth (previous_settlement)
  - spot at capture (S0) ......................... synthetic (Coinbase read in the tape)
  - perp funding (the directional PRIOR) ......... synthetic (OKX perp; a prior, never a fill)

FUNDING SOURCE NOTE: the spec named Binance USDs-M funding, but fapi.binance.com is
geo-blocked from this environment (HTTP 451). Perp funding is highly correlated across
venues, so we use OKX's free, key-less funding-rate-history for BTC-USD-SWAP / ETH-USD-SWAP
as the directional-prior proxy. It is tagged `synthetic` and is a PRIOR only, never a
settlement predictor or a fillable price. State this substitution in any writeup.

Bootstrap: block-bootstrap BY EVENT-HOUR (event_ticker) via core.bootstrap (L6/L33). Each
event contributes exactly one hold-to-settlement trade, so the event IS the independent
unit. Verdict gates: clears_tick_magnitude (L27) AND bootstrap_verdict_admissible (L41).

Read-only over tape/. Never mutates tape. No network write. The only network call is the
OKX funding fetch (read-only, no key).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import statistics
import sys
import urllib.request
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import pricing  # noqa: E402
from core.bootstrap import (  # noqa: E402
    block_bootstrap,
    bootstrap_verdict_admissible,
    clears_tick_magnitude,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAPE_GLOB = os.path.join(REPO, "tape", "crypto_hourly", "dt=*.jsonl")

OKX_FUNDING_URL = (
    "https://www.okx.com/api/v5/public/funding-rate-history?instId={inst}&limit=100"
)
OKX_INST = {"BTC": "BTC-USD-SWAP", "ETH": "ETH-USD-SWAP"}


# ─────────────────────────── pure helpers (offline-testable) ───────────────────────────

def parse_iso_utc(s: str) -> datetime:
    """ISO-8601 (with 'Z' or offset) -> tz-aware UTC datetime."""
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def funding_at_time(series: List[Tuple[int, float]], dt: datetime) -> Optional[float]:
    """The funding rate IN FORCE at `dt`: the most recent funding print whose settlement
    time is <= dt. `series` is a time-sorted list of (funding_time_ms, rate). Returns None
    if `dt` precedes every print (no prior funding known)."""
    ms = dt.timestamp() * 1000.0
    prev = None
    for t, r in series:
        if t <= ms:
            prev = r
        else:
            break
    return prev


def implied_side(funding_rate: float, convention: str) -> str:
    """Map a funding sign to the directional band under a stated sign convention.

    - 'momentum'   : positive funding (crowded long) -> bet price drifts UP.
    - 'contrarian' : positive funding (over-crowded long) -> bet mean-reversion DOWN.

    Testing BOTH is mandated because the sign convention is genuinely ambiguous; a sign
    chosen ex-post is a fishing hazard, reported honestly for both.
    """
    if convention == "momentum":
        return "up" if funding_rate > 0 else "down"
    if convention == "contrarian":
        return "down" if funding_rate > 0 else "up"
    raise ValueError(f"unknown convention {convention!r}")


def nearest_fillable_bracket(outcomes: List[dict], s0: float, side: str,
                             lo: float, hi: float) -> Optional[dict]:
    """The nearest genuinely-fillable bracket on the given side of spot S0.

    'Fillable' = RAW yes_ask in [lo, hi] — off the 1c YES floor (S10 pin) and off the $1
    NO-mirror pin. We gate on the RAW ask, NOT normalized_ask: the crypto ladder's
    bracket_sum spans ~188 members (mostly 1c-floor wings), so the ask-over-bracket_sum
    ratio is a fee-floor artifact (L12) that would mis-scale the band. The raw ask is the
    price we actually pay, exactly what fillability requires.

    up-side   = bracket entirely above spot (floor_strike >= S0), nearest above.
    down-side = bracket entirely below spot (cap_strike <= S0), nearest below.
    Returns None if no fillable bracket exists on that side (=> no trade, S10-honest).
    """
    cands = []
    for o in outcomes:
        ya = float(o["yes_ask"])
        if not (lo <= ya <= hi):
            continue
        if side == "up" and float(o["floor_strike"]) >= s0:
            cands.append((float(o["floor_strike"]) - s0, o))
        elif side == "down" and float(o["cap_strike"]) <= s0:
            cands.append((s0 - float(o["cap_strike"]), o))
    if not cands:
        return None
    cands.sort(key=lambda x: x[0])
    return cands[0][1]


def trade_net_pnl(entry_ask: float, won: bool,
                  rate: float = pricing.TAKER_FEE_RATE) -> float:
    """Hold-to-settlement net P&L of BUYing one YES contract at `entry_ask` (real_ask):
    payout ($1 if the bracket settled YES else $0) minus the entry and the taker fee.
    Fee via the sanctioned core.pricing.fee_per_contract (never hand-rolled, L5/L18)."""
    payout = 1.0 if won else 0.0
    cost = float(entry_ask)
    fee = pricing.fee_per_contract(cost, rate)
    return payout - cost - fee


# ─────────────────────────── tape / funding loaders (I/O) ───────────────────────────

def load_events(tape_glob: str = TAPE_GLOB) -> Dict[str, dict]:
    """Build per-(symbol, window-hour) event records from the crypto_hourly tape.

    For each event_ticker: the EARLIEST `current` capture (open ladder + spot + open/close
    time), joined to its `broker_truth` settlement (winning bracket + expiration_value) read
    from a later capture's `previous_settlement`. Only MECE/complete, uniquely-settled events
    are returned. Skips the L25 stray directory (dt=2026-07-10/) by requiring a regular file.
    """
    files = sorted(f for f in glob.glob(tape_glob) if os.path.isfile(f))
    earliest: Dict[str, dict] = {}
    settle: Dict[str, Tuple[float, str]] = {}
    for f in files:
        with open(f) as fh:
            for line in fh:
                if not line.strip():
                    continue
                d = json.loads(line)
                cur = d.get("current")
                if cur and cur.get("event_ticker"):
                    et = cur["event_ticker"]
                    ca = d["captured_at"]
                    if et not in earliest or ca < earliest[et]["captured_at"]:
                        rec = dict(cur)
                        rec["captured_at"] = ca
                        rec["symbol"] = d.get("symbol")
                        rec["spot"] = d.get("spot")
                        earliest[et] = rec
                ps = d.get("previous_settlement")
                if ps and ps.get("event_ticker") and ps.get("results"):
                    wins = [k for k, v in ps["results"].items() if v == "yes"]
                    if len(wins) == 1 and ps.get("expiration_value") is not None:
                        settle[ps["event_ticker"]] = (float(ps["expiration_value"]), wins[0])
    events: Dict[str, dict] = {}
    for et, rec in earliest.items():
        if et not in settle:
            continue
        if not rec.get("completeness_ok"):
            continue
        if not rec.get("spot") or rec["spot"].get("price") is None:
            continue
        rec["settle_value"] = settle[et][0]
        rec["winning_ticker"] = settle[et][1]
        events[et] = rec
    return events


def fetch_okx_funding() -> Dict[str, List[Tuple[int, float]]]:
    """Fetch OKX perp funding-rate history (read-only, no key) for BTC/ETH. Returns
    {symbol: sorted[(funding_time_ms, rate)]}. One page (100 prints) spans ~5 weeks at 8h
    cadence, covering the whole crypto_hourly tape window."""
    out: Dict[str, List[Tuple[int, float]]] = {}
    for sym, inst in OKX_INST.items():
        req = urllib.request.Request(
            OKX_FUNDING_URL.format(inst=inst), headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.load(r)
        rows = d.get("data", [])
        out[sym] = sorted((int(x["fundingTime"]), float(x["fundingRate"])) for x in rows)
    return out


# ─────────────────────────── the probe ───────────────────────────

def build_trades(events: Dict[str, dict], funding: Dict[str, List[Tuple[int, float]]],
                 *, convention: str, lo: float, hi: float,
                 abs_funding_threshold: float) -> Tuple[Dict[str, List[float]], dict]:
    """Return (unit_values, diag). unit_values maps event_ticker -> [net_pnl] for every
    event that (a) has funding >= threshold in |rate| and (b) has a fillable bracket on the
    funding-implied side. diag carries counts for the honesty report."""
    unit_values: Dict[str, List[float]] = {}
    n_events = 0
    n_funding_ok = 0
    n_elevated = 0
    n_no_fillable = 0
    n_up_side = 0
    n_down_side = 0
    wins = 0
    norm_asks: List[float] = []
    entry_asks: List[float] = []
    member_counts: List[int] = []
    for et, e in events.items():
        n_events += 1
        ot = parse_iso_utc(e["open_time"])
        fr = funding_at_time(funding.get(e["symbol"], []), ot)
        if fr is None:
            continue
        n_funding_ok += 1
        if abs(fr) < abs_funding_threshold:
            continue
        n_elevated += 1
        s0 = float(e["spot"]["price"])
        side = implied_side(fr, convention)
        o = nearest_fillable_bracket(e["outcomes"], s0, side, lo, hi)
        if o is None:
            n_no_fillable += 1
            continue
        if side == "up":
            n_up_side += 1
        else:
            n_down_side += 1
        entry = float(o["yes_ask"])
        won = o["ticker"] == e["winning_ticker"]
        if won:
            wins += 1
        net = trade_net_pnl(entry, won)
        unit_values[et] = [net]
        entry_asks.append(entry)
        member_counts.append(int(e.get("member_count", 0)))
        # Hard Rule #3 descriptive: de-overround implied prob via the sanctioned site.
        bs = float(e.get("bracket_sum", 0.0))
        if bs > 0:
            norm_asks.append(pricing.normalized_ask(entry, bs))
    n_trades = len(unit_values)
    diag = {
        "convention": convention,
        "band_raw_ask": [lo, hi],
        "abs_funding_threshold": abs_funding_threshold,
        "n_events": n_events,
        "n_funding_ok": n_funding_ok,
        "n_elevated_funding": n_elevated,
        "n_no_fillable_bracket": n_no_fillable,
        "n_trades": n_trades,
        "n_wins": wins,
        "win_rate": (wins / n_trades) if n_trades else None,
        "n_up_side": n_up_side,
        "n_down_side": n_down_side,
        "side_degeneracy_flag": _side_degeneracy(n_up_side, n_down_side),
        "mean_entry_ask_real_ask": (statistics.mean(entry_asks) if entry_asks else None),
        "mean_normalized_ask": (statistics.mean(norm_asks) if norm_asks else None),
        "mean_member_count": (statistics.mean(member_counts) if member_counts else None),
    }
    return unit_values, diag


def _side_degeneracy(n_up: int, n_down: int) -> Optional[str]:
    """L41: flag if the signal only ever picked one side (a one-sided population cannot
    support a real directional CI)."""
    tot = n_up + n_down
    if tot == 0:
        return "no_trades"
    frac_majority = max(n_up, n_down) / tot
    if frac_majority >= 0.90:
        return f"one_sided_{frac_majority:.2f}"
    return None


def run_cell(events, funding, *, convention, lo, hi, abs_funding_threshold,
             min_units=10, n_boot=10000) -> dict:
    unit_values, diag = build_trades(
        events, funding, convention=convention, lo=lo, hi=hi,
        abs_funding_threshold=abs_funding_threshold,
    )
    boot = block_bootstrap(unit_values, n_boot=n_boot)
    adm = bootstrap_verdict_admissible(unit_values, min_units=min_units)
    ci = boot["ci95"]
    clears = clears_tick_magnitude(ci) if ci and ci[0] is not None else False
    pos_units = sum(1 for v in unit_values.values() if statistics.mean(v) > 0)
    n_units = len(unit_values)
    alive = bool(ci and ci[0] is not None and ci[0] > 0 and clears and adm["admissible"])
    if n_units < min_units:
        verdict = "DEAD-by-data-adequacy"
    elif alive:
        verdict = "ALIVE"
    else:
        verdict = "DEAD"
    return {
        **diag,
        "bootstrap": boot,
        "admissible": adm,
        "clears_tick_magnitude": clears,
        "frac_positive_mean_units": (pos_units / n_units) if n_units else None,
        "verdict": verdict,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="emit full JSON result")
    ap.add_argument("--n-boot", type=int, default=10000)
    ap.add_argument("--funding-cache", default=None,
                    help="path to a cached OKX-funding JSON (offline replay); else live fetch")
    args = ap.parse_args()

    events = load_events()
    if args.funding_cache and os.path.isfile(args.funding_cache):
        with open(args.funding_cache) as fh:
            raw = json.load(fh)
        funding = {k: [tuple(x) for x in v] for k, v in raw.items()}
        fund_src = f"cache:{args.funding_cache}"
    else:
        funding = fetch_okx_funding()
        fund_src = "OKX live"

    abs_thr = _median_abs_funding(events, funding)

    print(f"# Seed 5 — perp-funding directional prior probe")
    print(f"# events joined (MECE/complete/settled): {len(events)}  funding_src={fund_src} (synthetic)")
    print(f"# entry = earliest capture (~24min into hour); settle = broker_truth; "
          f"funding = perp prior (synthetic)")
    print(f"# median |funding| over events (elevated threshold) = {abs_thr:.3e}\n")

    results = []
    # Primary = raw-ask band [0.05,0.95]; sensitivity bands + both conventions + threshold sweep.
    bands = [(0.05, 0.95), (0.03, 0.97), (0.10, 0.90)]
    for lo, hi in bands:
        for conv in ["momentum", "contrarian"]:
            for label, thr in [("all", 0.0), ("elevated", abs_thr)]:
                r = run_cell(events, funding, convention=conv, lo=lo, hi=hi,
                             abs_funding_threshold=thr, n_boot=args.n_boot)
                r["threshold_label"] = label
                results.append(r)
                ci = r["bootstrap"]["ci95"]
                ci_s = (f"[{ci[0]:+.5f},{ci[1]:+.5f}]" if ci and ci[0] is not None else "[--,--]")
                mean = r["bootstrap"]["mean"]
                mean_s = f"{mean:+.5f}" if mean is not None else "None"
                print(f"band[{lo:.2f},{hi:.2f}] {conv:10s} {label:8s} "
                      f"n={r['n_trades']:3d} win={r['win_rate'] if r['win_rate'] is None else round(r['win_rate'],3)} "
                      f"mean={mean_s} CI={ci_s} "
                      f"clears_tick={r['clears_tick_magnitude']} adm={r['admissible']['admissible']} "
                      f"side_deg={r['side_degeneracy_flag']} => {r['verdict']}")

    if args.json:
        print("\n" + json.dumps(results, indent=1, default=str))
    return 0


def _median_abs_funding(events, funding) -> float:
    vals = []
    for e in events.values():
        fr = funding_at_time(funding.get(e["symbol"], []), parse_iso_utc(e["open_time"]))
        if fr is not None:
            vals.append(abs(fr))
    return statistics.median(vals) if vals else 0.0


if __name__ == "__main__":
    raise SystemExit(main())
