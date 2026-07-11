#!/usr/bin/env python3
"""s6_maker_firstcut.py — S6 inventory-aware market-making, hourly-snapshot first cut.

The hypothesis (S6, kb/strategies/00-index.md row 18): resting a maker quote at the best
bid/ask earns the half-spread; net of adverse selection and the (4x-cheaper) maker fee that
income is positive — the Avellaneda-Stoikov "earn the spread instead of paying it" trade. The
binding gate: spread income > adverse-selection cost + maker fee; block-bootstrapped 95% CI
strictly > 0 at real fillable prices.

WHAT AN HOURLY-SNAPSHOT PROXY CAN AND CANNOT SUPPORT (read this before trusting a number)
========================================================================================
`tape/orderbook_depth/` is HOURLY L2 SNAPSHOTS, not message-level order flow. Consequences,
stated up front:

  * We CANNOT observe a real fill, a real fill probability, or true message-resolution adverse
    selection. There is no trade tape and no queue position.
  * We CANNOT use settlement here (unlike S10): this is a pure quote-displacement proxy, so
    "adverse selection" is proxied by how far the mid moved between two consecutive captures,
    NOT by a realized P&L against a broker_truth outcome.
  * We CAN observe, for a ticker seen in two consecutive hourly captures: the quoted half-
    spread at capture-1 (the notional maker income if a fill occurred) and how far the mid
    moved to capture-2 (the notional adverse-selection cost — a resting quote is picked off on
    exactly the side the market moves toward).

The proxy round-leg P&L, per the task's own construction, working entirely in YES-price space
(the NO-side spread equals the YES-side spread, and the NO mid is one minus the YES mid):

    half_spread = (yes_ask_1 - yes_bid_1) / 2                 # income if filled as maker
    dmid        = mid_2 - mid_1                               # market displacement over ~1h
    fill_price  = yes_ask_1 if dmid > 0 else yes_bid_1        # adverse side you'd be filled on
    maker_fee   = fee_per_contract(fill_price, MAKER_FEE_RATE)  # core.pricing — never hand-rolled
    net         = half_spread - |dmid| - maker_fee

Directionally this is the Glosten-Milgrom intuition: if the mid rises by dmid a buyer lifts your
resting ask at yes_ask_1 = mid_1 + half_spread and your mark-to-fair P&L is half_spread - dmid;
symmetric on the bid. It is OPTIMISTIC in that it assumes you always capture the full half-
spread, and CONSERVATIVE in that it charges the entire hour's mid move as adverse (a real fill
horizon is shorter and can revert). Neither bound is a true fill population; we report both a
frozen-inclusive and a movement-conditioned cut to bracket the honest range.

TWO ARTIFACTS THIS PROBE MUST NOT LAUNDER INTO AN EDGE (lessons L12 / L26 / L27 / L28)
-------------------------------------------------------------------------------------
  1. FROZEN BOOKS (L28 precheck): a consecutive pair whose BBO did not move at all represents
     NO fill — a resting quote just sits there earning nothing. Booking its nominal half-spread
     as riskless income (dmid=0, so net = half_spread - fee > 0) is the naive error. The
     precheck reports the frozen fraction first; the movement-conditioned cut removes them.
  2. WIDE-WING SPREADS (L12/L26 floor-artifact family): a far/one-sided bracket can quote a
     huge nominal spread (e.g. a 0.03 bid against a 0.89 ask -> a 43c half-spread) precisely
     BECAUSE there is no two-sided interest. That half-spread is not maker-capturable; the
     |dmid| proxy, seeing a frozen wing, spuriously books the entire unfillable spread as
     profit. The maker edge can only realistically live in genuinely-tight two-sided books, so
     the primary population caps the spread and the wide wing is reported SEPARATELY, flagged.

The maker fee turns out to be a FLAT $0.01/contract for every interior price: Kalshi's fee is
ceil(rate * P * (1-P) * 100)/100 and MAKER_FEE_RATE * max(P*(1-P)) = 0.0175 * 0.25 = 0.004375,
whose *100 = 0.4375 always ceils to 1 -> $0.01. So a maker must net MORE than a full cent of
half-spread-minus-adverse just to break even — a 1c-spread book (half-spread 0.5c, the modal
case) cannot (generalizes L5/L18: the maker fee is not merely "4x cheaper", it is a flat 1c
floor that a sub-2c spread can never clear).

Read-only over `tape/orderbook_depth/dt=*.jsonl` (FILES only; a stray dt=<date> directory is
skipped by the `*.jsonl` glob + is_file guard — lessons L25/L29). Never mutates tape, no
network, no order/execution code. Source tags: income derives from the tape's own `real_ask`
(yes_ask) and `real_bid` (yes_bid) ladders; no synthetic value is ever treated as fillable, and
no settlement/broker_truth is used.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from core.io import REPO_ROOT
from core.pricing import MAKER_FEE_RATE, fee_per_contract

TAPE_DIR = REPO_ROOT / "tape" / "orderbook_depth"

# Two genuinely-consecutive hourly captures sit ~30-60 min apart (two collectors + the hourly
# cron). A gap much larger than an hour is an overnight/multi-day stale comparison for a
# long-lived sports game ticker, not an hourly adverse-selection signal, so it is excluded.
MAX_GAP_MIN_DEFAULT = 90.0

# "Genuinely-tight two-sided book" = the population where a maker quote could realistically be
# crossed for its quoted spread. Wider than this the quoted spread is a wide-wing artifact
# (L12/L26), not capturable. The sweep shows the verdict is robust across the cap.
PRIMARY_SPREAD_CAP_CENTS = 10
SPREAD_CAP_SWEEP_CENTS = [2, 5, 10]


# --------------------------------------------------------------------------- #
# loading (read-only; FILES only — lessons L25/L29)
# --------------------------------------------------------------------------- #
def load_records(tape_dir: Path = TAPE_DIR) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for path in sorted(tape_dir.glob("dt=*.jsonl")):
        if not path.is_file():
            continue  # a stray dt=<date> directory of raw blobs is not our canonical tape
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    return records


def _parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s)


# --------------------------------------------------------------------------- #
# consecutive same-ticker snapshot pairs (pure)
# --------------------------------------------------------------------------- #
@dataclass
class MakerPair:
    ticker: str
    cap1_id: str
    cap2_id: str
    gap_min: float
    yes_ask1: float          # real_ask
    yes_bid1: float          # real_bid
    yes_ask2: float          # real_ask
    yes_bid2: float          # real_bid
    spread_cents: int        # round((yes_ask1 - yes_bid1) * 100)
    half_spread: float       # income proxy
    mid1: float
    mid2: float
    dmid: float              # mid2 - mid1 (signed)
    moved: bool              # dmid != 0 (a fill/trade plausibly occurred)
    fill_price: float        # adverse-side quote you'd be filled at (real_ask or real_bid)
    maker_fee: float         # core.pricing.fee_per_contract(fill_price, MAKER_FEE_RATE)
    net: float               # half_spread - |dmid| - maker_fee
    income_source_tags: str = "real_ask+real_bid"


def maker_net(half_spread: float, dmid: float, fill_price: float) -> float:
    """Proxy round-leg maker P&L: capture the half-spread, pay the full mid displacement as
    adverse selection, pay the maker fee (core.pricing — never hand-rolled, lesson L18)."""
    fee = fee_per_contract(fill_price, MAKER_FEE_RATE)
    return half_spread - abs(dmid) - fee


def _dedup_by_capture(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Order records by captured_at, dropping repeat capture_ids (a ticker should appear once
    per pass; belt-and-suspenders so a duplicated pass line never fakes a zero-gap pair)."""
    ordered = sorted(records, key=lambda r: r["captured_at"])
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for r in ordered:
        cid = r.get("capture_id")
        if cid in seen:
            continue
        seen.add(cid)
        out.append(r)
    return out


def build_pairs(records: List[Dict[str, Any]],
                max_gap_min: float = MAX_GAP_MIN_DEFAULT) -> List[MakerPair]:
    """Every genuinely-consecutive (<= max_gap_min) same-ticker two-sided snapshot pair.

    One-sided books at capture-1 (empty bid OR empty ask ladder -> None best) are NOT a capture
    failure (lesson L23) — they simply have no two-sided spread to quote, so they cannot host a
    maker round-leg and are skipped here. capture-2 must also be two-sided to define mid2."""
    by_ticker: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in records:
        by_ticker[r["ticker"]].append(r)

    pairs: List[MakerPair] = []
    for ticker, recs in by_ticker.items():
        uu = _dedup_by_capture(recs)
        for a, b in zip(uu, uu[1:]):
            gap = (_parse_ts(b["captured_at"]) - _parse_ts(a["captured_at"])).total_seconds() / 60.0
            if gap > max_gap_min:
                continue
            ya1, yb1 = a.get("best_yes_ask"), a.get("best_yes_bid")
            ya2, yb2 = b.get("best_yes_ask"), b.get("best_yes_bid")
            if None in (ya1, yb1, ya2, yb2):
                continue  # need two-sided books both ends (L23: one-sided is valid, just not a quote)
            spread = ya1 - yb1
            if spread <= 0:
                continue  # crossed/locked -> not a quotable spread
            half_spread = spread / 2.0
            mid1 = (ya1 + yb1) / 2.0
            mid2 = (ya2 + yb2) / 2.0
            dmid = mid2 - mid1
            fill_price = ya1 if dmid > 0 else yb1
            pairs.append(MakerPair(
                ticker=ticker, cap1_id=a["capture_id"], cap2_id=b["capture_id"],
                gap_min=gap, yes_ask1=float(ya1), yes_bid1=float(yb1),
                yes_ask2=float(ya2), yes_bid2=float(yb2),
                spread_cents=round(spread * 100), half_spread=half_spread,
                mid1=mid1, mid2=mid2, dmid=dmid, moved=(dmid != 0),
                fill_price=float(fill_price),
                maker_fee=fee_per_contract(float(fill_price), MAKER_FEE_RATE),
                net=maker_net(half_spread, dmid, float(fill_price)),
            ))
    return pairs


# --------------------------------------------------------------------------- #
# L28 cheap precheck: is there any signal, or is the book frozen/pinned?
# --------------------------------------------------------------------------- #
def precheck(pairs: List[MakerPair]) -> Dict[str, Any]:
    """Before any bootstrap: what fraction of consecutive two-sided pairs are FROZEN (BBO did
    not move at all -> no fill, no signal)? If the vast majority are frozen there is nothing to
    measure. Also report the spread distribution to expose the wide-wing artifact up front."""
    n = len(pairs)
    if n == 0:
        return {"n_pairs": 0}
    frozen_bbo = sum(1 for p in pairs if p.yes_ask1 == p.yes_ask2 and p.yes_bid1 == p.yes_bid2)
    mid_moved = sum(1 for p in pairs if p.moved)
    spread_hist = Counter(
        ("1-2c" if p.spread_cents <= 2 else "3-5c" if p.spread_cents <= 5
         else "6-10c" if p.spread_cents <= 10 else "11-30c" if p.spread_cents <= 30
         else ">30c(wing)")
        for p in pairs
    )
    return {
        "n_pairs": n,
        "n_frozen_bbo": frozen_bbo, "frac_frozen_bbo": frozen_bbo / n,
        "n_mid_moved": mid_moved, "frac_mid_moved": mid_moved / n,
        "spread_bucket_counts": dict(spread_hist),
        "price_source_tag": "real_ask+real_bid",
    }


# --------------------------------------------------------------------------- #
# block bootstrap BY TICKER (the instrument you rest a quote on; consecutive pairs within one
# game/bracket are correlated draws — lesson L6 / CLAUDE.md / S7c "by game")
# --------------------------------------------------------------------------- #
def block_bootstrap_by_ticker(pairs: List[MakerPair],
                              predicate: Optional[Callable[[MakerPair], bool]] = None,
                              n_boot: int = 10000, seed: int = 42) -> Dict[str, Any]:
    by_ticker: Dict[str, List[float]] = defaultdict(list)
    for p in pairs:
        if predicate is None or predicate(p):
            by_ticker[p.ticker].append(p.net)
    tickers = [t for t, v in by_ticker.items() if v]
    if not tickers:
        return {"n_tickers": 0, "n_pairs": 0, "mean": None, "ci95": [None, None]}
    total = sum(sum(by_ticker[t]) for t in tickers)
    count = sum(len(by_ticker[t]) for t in tickers)
    grand_mean = total / count

    rng = random.Random(seed)
    means: List[float] = []
    for _ in range(n_boot):
        tot = 0.0
        cnt = 0
        for _ in tickers:
            v = by_ticker[rng.choice(tickers)]
            tot += sum(v)
            cnt += len(v)
        means.append(tot / cnt)
    means.sort()
    return {
        "n_tickers": len(tickers), "n_pairs": count, "mean": grand_mean,
        "ci95": [means[int(0.025 * n_boot)], means[int(0.975 * n_boot)]],
        "n_boot": n_boot, "seed": seed, "price_source_tag": "real_ask+real_bid",
    }


def population_report(pairs: List[MakerPair], name: str,
                      predicate: Callable[[MakerPair], bool], n_boot: int) -> Dict[str, Any]:
    sel = [p for p in pairs if predicate(p)]
    boot = block_bootstrap_by_ticker(pairs, predicate=predicate, n_boot=n_boot)
    pos = sum(1 for p in sel if p.net > 0)
    return {
        "name": name, "n_pairs": len(sel),
        "frac_net_positive": (pos / len(sel)) if sel else None,
        "mean_net": boot["mean"], "ci95": boot["ci95"],
        "n_tickers": boot["n_tickers"],
        "price_source_tag": "real_ask+real_bid",
    }


# --------------------------------------------------------------------------- #
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="S6 maker spread-vs-adverse-selection first cut (read-only)")
    ap.add_argument("--tape-dir", default=str(TAPE_DIR))
    ap.add_argument("--max-gap-min", type=float, default=MAX_GAP_MIN_DEFAULT)
    ap.add_argument("--n-boot", type=int, default=10000)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    records = load_records(Path(args.tape_dir))
    pairs = build_pairs(records, max_gap_min=args.max_gap_min)
    pc = precheck(pairs)

    cap = PRIMARY_SPREAD_CAP_CENTS
    populations = [
        population_report(pairs, "ALL two-sided (naive; frozen booked as free spread)",
                          lambda p: True, args.n_boot),
        population_report(pairs, f"WIDE WING >30c (UNFILLABLE ARTIFACT — not a maker edge)",
                          lambda p: p.spread_cents > 30, args.n_boot),
    ]
    sweep = [
        population_report(pairs, f"tight <= {c}c (realistic two-sided book)",
                          (lambda c: lambda p: p.spread_cents <= c)(c), args.n_boot)
        for c in SPREAD_CAP_SWEEP_CENTS
    ]
    primary_frozen_incl = population_report(
        pairs, f"PRIMARY tight <= {cap}c, frozen-inclusive (max generous income)",
        lambda p: p.spread_cents <= cap, args.n_boot)
    primary_moved = population_report(
        pairs, f"PRIMARY tight <= {cap}c AND mid moved (honest adverse-selection test)",
        lambda p: p.spread_cents <= cap and p.moved, args.n_boot)

    result = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "n_records": len(records),
        "max_gap_min": args.max_gap_min,
        "maker_fee_flat_per_contract": fee_per_contract(0.5, MAKER_FEE_RATE),
        "precheck": pc,
        "populations": populations,
        "spread_cap_sweep": sweep,
        "primary_frozen_inclusive": primary_frozen_incl,
        "primary_moved_conditioned": primary_moved,
    }

    def fmt(rep: Dict[str, Any]) -> str:
        if rep["mean_net"] is None:
            return f"  {rep['name']}: 0 pairs"
        return (f"  {rep['name']}:\n"
                f"      n_tickers={rep['n_tickers']} n_pairs={rep['n_pairs']} "
                f"frac_net>0={rep['frac_net_positive']:.1%}\n"
                f"      mean_net={rep['mean_net']:+.5f} "
                f"95% CI [{rep['ci95'][0]:+.5f}, {rep['ci95'][1]:+.5f}] [real_ask+real_bid]")

    print(f"[s6] {len(records)} depth records -> {pc['n_pairs']} consecutive two-sided pairs "
          f"(<= {args.max_gap_min:.0f} min gap)")
    print(f"[s6] PRECHECK (L28): frozen BBO {pc['n_frozen_bbo']}/{pc['n_pairs']} "
          f"({pc['frac_frozen_bbo']:.1%}); mid moved {pc['frac_mid_moved']:.1%}; "
          f"spread buckets {pc['spread_bucket_counts']}")
    print(f"[s6] maker fee is FLAT ${result['maker_fee_flat_per_contract']:.2f}/contract at every interior price")
    for rep in populations:
        print(fmt(rep))
    print("[s6] spread-cap sweep (realistic two-sided books):")
    for rep in sweep:
        print(fmt(rep))
    print("[s6] PRIMARY verdict populations:")
    print(fmt(primary_frozen_incl))
    print(fmt(primary_moved))

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, indent=2, default=str))
        print(f"[s6] wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
