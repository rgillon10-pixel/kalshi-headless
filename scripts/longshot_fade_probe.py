#!/usr/bin/env python3
"""longshot_fade_probe.py — S1 longshot-fade real-ask calibration probe.

Dossier opportunity #2 (findings/2026-06-18-codebase-money-map.md). The binding test:
does Kalshi's KXHIGH daily-temperature ladder systematically OVERPRICE longshots and
UNDERPRICE favorites, and — crucially — is there a *dollar* edge in fading the longshots
*after* real-world taker frictions? Three peer-reviewed methodologies say the bias exists;
the prime directive demands we prove the dollar edge at REAL, fillable asks, not at a
synthetic or midpoint price, and only declare an edge if a bootstrapped CI strictly clears
zero. A null result is a VALID, valuable outcome: it falsifies the bias-chasing family.

This script is READ-ONLY against the recovered orderbook tape (opens the DB with
`mode=ro`). It never writes to the tape DB.

================================================================================
DATA SOURCE & THE REAL-ASK RECONSTRUCTION (why source_tag = "real_ask")
================================================================================
Tape: arb-bot-v2/data/tape_replica/orderbook_archive_recovered.db (read-only).
  orderbook_events(ts_utc, ticker, event_type, side, price, size_delta, size_total, raw_json)
  settlements(ticker, result)  -- result in {'yes','no'}; 1,056 KXHIGH brackets settled.

The tape holds two event_types per ticker:
  - 'delta'  : per-side (yes/no) price-level deltas with size_delta only (size_total is
               ALWAYS NULL). There is NO initial book snapshot anywhere in the tape, and the
               first deltas include negative size_deltas for levels never added in-tape —
               i.e. the archiver subscribed to a delta feed that assumed a snapshot we do
               not have. Integrating deltas from an empty book would therefore produce
               WRONG (negative) sizes. Delta integration is NOT a trustworthy ask source here.
  - 'ticker' : a self-contained BBO summary carrying absolute `yes_bid_dollars` and
               `yes_ask_dollars` (plus sizes). This is Kalshi's own published best yes ask.

Kalshi posts BIDS only per outcome; it computes the tradeable YES taker ask as the
complement of the best NO bid: yes_ask = 1 - best_no_bid (see collection/normalize.py).
The 'ticker' event's `yes_ask_dollars` IS that complement, published by the exchange —
it is the real, fillable taker price a market order would have lifted. Because there is
no snapshot to integrate deltas against, the 'ticker' BBO is the MOST reliable real-ask
source in this tape, not a fallback. We stamp it source_tag = "real_ask" (a real book
price), and we only ever turn it into a probability via core.pricing.normalized_ask
(Hard Rule #3 — never divide a raw ask by hand).

We additionally require yes_ask < 1.0 (an ask of exactly 1.0000 means best_no_bid == 0,
i.e. there is no NO liquidity to lift, so the side is not really fillable) and we record
the bid for coherence. A crossed book (yes_bid > yes_ask) is dropped as malformed.

================================================================================
T-24h DECISION-TIME DEFINITION (documented precisely, per the dossier)
================================================================================
A KXHIGH daily-high market settles on the observation day's high temperature. The CRON
`settled_at` in `settlements` is the cron RUN-TIME (a single timestamp shared by hundreds
of brackets), NOT the true settlement instant — so we do NOT use it for timing. We derive:

  close_T(group)  := the LATEST 'ticker'-event ts_utc across all 6 brackets of the
                     (city, contract-day) group. Empirically this lands at the market's
                     real close: ~00:00 local of the day AFTER the observation day
                     (~04:59 UTC for ET cities, ~05:59 CT, ~06:59 MT, ~09:00 PT). It is the
                     last moment the book is observed, i.e. the close.
  T               := close_T(group) - 24h.   <-- the pinned decision time.

The archiver subscribed to each daily market at a fixed ~04:00 UTC each morning, so the
tape for contract day D runs ~D 04:00 UTC .. D+1 close. That window is ~25-29h, so T-24h
falls just AFTER tape start and a book is available. For each bracket we take the most
recent 'ticker' event AT OR BEFORE T (a strictly causal, no-look-ahead read). If a bracket
has no 'ticker' event at/before T, that bracket is a DROP (honest completeness). A group is
USABLE only if ALL 6 brackets have a book at T (so bracket_sum is a complete partition);
otherwise the whole group is dropped (partial bracket_sum would mis-normalize the ladder).

The bracket set is a clean partition: every group is exactly {2 T-tails + 4 B-bands} = 6
mutually-exclusive, exhaustive outcomes; exactly one settles 'yes' (verified on all 176
groups). So bracket_sum sums the 6 yes_asks and the normalized implied probs sum to 1.0.

================================================================================
COST MODEL FOR THE MAKER-SIDE NO-ON-LONGSHOT RULE (assumptions stated explicitly)
================================================================================
Rule: SELL NO on the cheapest / longshot brackets (implied prob below a threshold). Selling
NO on a longshot YES = collecting premium that the longshot will (usually) expire worthless.
Equivalently a maker bet that the longshot does NOT happen.

Per-trade economics (all in dollars per 1 contract, $1 notional):
  - We want the NO outcome (fade the longshot YES). The displayed best NO bid is the
    complement of the yes ask (Kalshi posts bids only). A resting maker who wants a fill in
    a thin longshot must
    IMPROVE its price UP toward the ask — you do not get filled sitting at the stale bid while
    the longshot is collapsing; you get filled when you are the most aggressive resting order,
    i.e. you PAY MORE. We therefore book the effective NO entry as no_bid + HAIRCUT_SPREAD
    (a 2c WORSE price than the displayed bid — the dossier's "2c spread" cost, and the honest
    direction: a cost raises your entry price, it never improves it). Booking at no_bid - 0.02
    (a price *improvement*) was a sign bug that manufactured a false positive and is forbidden
    by the prime directive (#1: never manufacture an edge).
  - MAKER FEE: Kalshi's standard maker fee on these markets is 0.0 (makers are not charged
    the taker fee). We still carry a conservative MAKER_FEE = 0.0035 ($0.0035/contract) to
    avoid claiming a fee-free edge; set via constant below. (kb/kalshi-api/03-fees-and-
    breakeven.md: taker fee is 0.07*p*(1-p); maker side is the favorable side.)
  - FILL-PROBABILITY HAIRCUT: a resting maker order is NOT guaranteed a fill. We assume a
    fill probability FILL_PROB = 0.5 on the longshot NO (longshots are thin; you often do
    not get filled when you would most want to). Unfilled trades earn $0 and cost $0. We
    apply this by scaling each trade's net P&L by FILL_PROB (expected realized P&L), which is
    the honest expected-value treatment for a strategy you cannot always execute.

Settlement payoff for a SELL-NO position (entered at effective price e = no_bid - spread):
  - if outcome == 'no'  (longshot did NOT happen, the common case): NO pays $1, we keep
    (1 - e) gross  ... wait: selling NO means we are SHORT the NO contract. Cleaner framing:
    we BUY the NO contract at ask-equivalent? No — the rule is *maker* NO. We model BUYING
    the NO outcome as a resting bid at price e (we want NO to win). Then:
        payoff = (1.0 if result=='no' else 0.0)
        gross_pnl_per_contract = payoff - e
        net = (gross - MAKER_FEE)          # before fill-prob scaling
        expected_net = FILL_PROB * net
  This is buying the cheap-YES bracket's NO side as a maker (fade the longshot YES).

All four provenance fields are persisted per trade: raw_yes_ask, bracket_sum,
overround_absorbed, member_count, plus price_source_tag = "real_ask".

================================================================================
BOOTSTRAP (moving-block by contract-day)
================================================================================
Intra-day trades within one (city, day) are correlated (one weather realization drives all
6 brackets of that group, and city-days on the same calendar date share weather regimes).
To avoid double-counting that correlation we BLOCK the bootstrap by contract-day: each
resample draws whole contract-days (all city-day groups on that date, all their trades)
with replacement, then takes the mean net per-trade P&L. 10,000 resamples -> 95% CI.

Run:
  one-city validation:  python scripts/longshot_fade_probe.py --city MIA
  full run (all 176):   python scripts/longshot_fade_probe.py
  options: --longshot-max 0.20  --n-boot 10000  --limit N (cap groups, for a fast smoke)
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

# Make the substrate importable however this script is invoked.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.pricing import bracket_sum, normalized_ask, overround  # noqa: E402
from core.source_tag import tag_or_synthetic  # noqa: E402

TAPE_DB = ("/Users/ryan.gillon/Active/01-projects/arb-bot-v2/data/tape_replica/"
           "orderbook_archive_recovered.db")

# ── cost-model constants (see module docstring; stated assumptions) ──────────────
HAIRCUT_SPREAD = 0.02   # 2c spread cost applied to the maker entry price
MAKER_FEE = 0.0035      # conservative per-contract maker fee ($); Kalshi maker fee ~0
FILL_PROB = 0.50        # resting-maker fill probability on a thin longshot NO

_MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}
# KXHIGH<CODE>-YYMMMDD-<bucket>
_GROUP_RE = re.compile(r"^KXHIGH([A-Z]+)-(\d{2})([A-Z]{3})(\d{2})-")


def contract_day(ticker: str) -> Tuple[Optional[str], Optional[date]]:
    """(city_code, contract_day) parsed from the TICKER (Hard correctness note: derive the
    day from the ticker, never from settlements.settled_at which is the cron run-time)."""
    m = _GROUP_RE.match(ticker)
    if not m:
        return None, None
    return m.group(1), date(2000 + int(m.group(2)), _MONTHS[m.group(3)], int(m.group(4)))


def _connect_ro(db_path: str) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


def load_groups(con: sqlite3.Connection, city: Optional[str]) -> Dict[Tuple[str, date], Dict[str, str]]:
    """{(city_code, day): {ticker: result}} for settled KXHIGH brackets."""
    like = f"KXHIGH{city}-%" if city else "KXHIGH%"
    groups: Dict[Tuple[str, date], Dict[str, str]] = defaultdict(dict)
    for tk, result in con.execute(
            "SELECT ticker, result FROM settlements WHERE ticker LIKE ? AND platform='kalshi'",
            (like,)):
        code, day = contract_day(tk)
        if day is None:
            continue
        groups[(code, day)][tk] = result
    return groups


def group_close_ts(con: sqlite3.Connection, tickers: List[str]) -> Optional[str]:
    """close_T := latest 'ticker'-event ts across the group's brackets (the real close)."""
    q = ",".join("?" * len(tickers))
    row = con.execute(
        f"SELECT MAX(ts_utc) FROM orderbook_events "
        f"WHERE ticker IN ({q}) AND event_type='ticker'", tickers).fetchone()
    return row[0] if row and row[0] else None


def book_at(con: sqlite3.Connection, ticker: str, t_iso: str) -> Optional[Tuple[float, float, str]]:
    """Most recent 'ticker'-event BBO AT OR BEFORE t_iso (strictly causal, no look-ahead).
    Returns (yes_ask, yes_bid, book_ts) or None if no book at/before t."""
    row = con.execute(
        "SELECT ts_utc, raw_json FROM orderbook_events "
        "WHERE ticker=? AND event_type='ticker' AND ts_utc<=? "
        "ORDER BY ts_utc DESC LIMIT 1", (ticker, t_iso)).fetchone()
    if row is None:
        return None
    d = json.loads(row[1])
    try:
        ya = float(d["yes_ask_dollars"])
        yb = float(d["yes_bid_dollars"])
    except (KeyError, TypeError, ValueError):
        return None
    return ya, yb, row[0]


def reconstruct(con: sqlite3.Connection, groups: Dict[Tuple[str, date], Dict[str, str]]
                ) -> Tuple[List[dict], dict]:
    """Build per-bracket real-ask rows at T-24h. Returns (trades, drop_stats).

    A 'trade' row = one bracket priced at T with its settlement outcome and provenance.
    Group is usable only if ALL brackets have a book at T (complete partition for bracket_sum).
    """
    trades: List[dict] = []
    drops = {"groups_total": 0, "groups_no_close": 0, "groups_incomplete_book": 0,
             "groups_crossed": 0, "groups_usable": 0,
             "brackets_total": 0, "brackets_no_book": 0, "brackets_ask_ge_1": 0,
             "brackets_crossed": 0}

    for (code, day), members in groups.items():
        drops["groups_total"] += 1
        tickers = sorted(members)
        drops["brackets_total"] += len(tickers)

        close = group_close_ts(con, tickers)
        if close is None:
            drops["groups_no_close"] += 1
            continue
        T = (datetime.fromisoformat(close) - timedelta(hours=24)).isoformat()

        # price every bracket at T
        priced: Dict[str, Tuple[float, float, str]] = {}
        complete = True
        bad = False
        for tk in tickers:
            bk = book_at(con, tk, T)
            if bk is None:
                drops["brackets_no_book"] += 1
                complete = False
                continue
            ya, yb, bts = bk
            if ya >= 0.9999:  # best_no_bid == 0 -> no fillable NO liquidity to lift
                drops["brackets_ask_ge_1"] += 1
                complete = False
                continue
            if yb > ya + 1e-9:  # crossed/malformed
                drops["brackets_crossed"] += 1
                bad = True
                continue
            priced[tk] = (ya, yb, bts)

        if bad:
            drops["groups_crossed"] += 1
            continue
        if not complete or len(priced) != len(tickers):
            drops["groups_incomplete_book"] += 1
            continue

        # group-level pricing (the only sanctioned ask->prob site is core.pricing)
        asks = [priced[tk][0] for tk in tickers]
        bs = bracket_sum(asks)
        ov = overround(asks)
        member_count = len(tickers)

        drops["groups_usable"] += 1
        for tk in tickers:
            ya, yb, bts = priced[tk]
            implied = normalized_ask(ya, bs)  # Hard Rule #3
            trades.append({
                "ticker": tk,
                "city": code,
                "contract_day": day.isoformat(),
                "decision_T": T,
                "book_ts": bts,
                "close_ts": close,
                "raw_yes_ask": round(ya, 4),
                "yes_bid": round(yb, 4),
                "no_bid": round(1.0 - ya, 4),          # = best_no_bid (Kalshi bid-only)
                "bracket_sum": round(bs, 4),
                "overround_absorbed": round(ov, 4),
                "member_count": member_count,
                "implied_prob": round(implied, 6),
                "result": members[tk],                 # 'yes' / 'no'
                "price_source_tag": tag_or_synthetic("real_ask"),  # real book price
            })
    return trades, drops


# ── calibration ────────────────────────────────────────────────────────────────
def calibration_table(trades: List[dict], bin_width: float = 0.05) -> List[dict]:
    """Win-rate (P(result=='yes')) per 5c implied-prob bin = the favorite-longshot curve."""
    bins: Dict[int, List[dict]] = defaultdict(list)
    for t in trades:
        b = min(int(t["implied_prob"] / bin_width), int(round(1 / bin_width)) - 1)
        bins[b].append(t)
    out = []
    for b in sorted(bins):
        lo, hi = b * bin_width, (b + 1) * bin_width
        ts = bins[b]
        n = len(ts)
        wins = sum(1 for t in ts if t["result"] == "yes")
        mean_implied = float(np.mean([t["implied_prob"] for t in ts]))
        out.append({
            "bin": f"[{lo:.2f},{hi:.2f})",
            "n": n,
            "mean_implied_prob": round(mean_implied, 4),
            "realized_win_rate": round(wins / n, 4) if n else None,
            "calibration_gap": round((wins / n) - mean_implied, 4) if n else None,
        })
    return out


# ── the maker-side NO-on-longshot rule + net P&L ────────────────────────────────
def make_pnl(trades: List[dict], longshot_max: float) -> List[dict]:
    """For every bracket with implied_prob < longshot_max, SELL/BUY-NO as a maker and book
    expected net per-trade P&L after spread + maker fee + fill-prob haircut."""
    out = []
    for t in trades:
        if t["implied_prob"] >= longshot_max:
            continue
        no_bid = t["no_bid"]                      # complement of the yes ask (bid-only)
        entry = no_bid + HAIRCUT_SPREAD           # 2c WORSE: a cost raises the entry price
        payoff = 1.0 if t["result"] == "no" else 0.0  # NO pays $1 if longshot YES did not happen
        gross = payoff - entry
        net = gross - MAKER_FEE
        expected_net = FILL_PROB * net            # resting-maker fill-prob haircut
        out.append({**t,
                    "entry_no_price": round(entry, 4),
                    "payoff": payoff,
                    "gross_pnl": round(gross, 4),
                    "net_pnl": round(net, 4),
                    "expected_net_pnl": round(expected_net, 6)})
    return out


def block_bootstrap(pnl_trades: List[dict], n_boot: int, seed: int = 12345
                    ) -> Tuple[float, float, float, int]:
    """Moving-block bootstrap by contract-day. Block = a calendar contract-day (all city-day
    groups + all their trades on that date). Returns (mean, lo95, hi95, n_blocks)."""
    by_day: Dict[str, List[float]] = defaultdict(list)
    for t in pnl_trades:
        by_day[t["contract_day"]].append(t["expected_net_pnl"])
    days = sorted(by_day)
    blocks = [np.array(by_day[d], dtype=float) for d in days]
    if not blocks:
        return float("nan"), float("nan"), float("nan"), 0
    rng = np.random.default_rng(seed)
    n_blocks = len(blocks)
    point = float(np.mean(np.concatenate(blocks)))
    means = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n_blocks, size=n_blocks)
        sample = np.concatenate([blocks[j] for j in idx])
        means[i] = sample.mean()
    lo, hi = np.percentile(means, [2.5, 97.5])
    return point, float(lo), float(hi), n_blocks


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="S1 longshot-fade real-ask calibration probe")
    ap.add_argument("--city", default=None, help="city code (e.g. MIA) for one-city validation")
    ap.add_argument("--limit", type=int, default=None, help="cap number of groups (smoke test)")
    ap.add_argument("--longshot-max", type=float, default=0.20,
                    help="implied-prob threshold defining a longshot (default 0.20)")
    ap.add_argument("--n-boot", type=int, default=10000, help="bootstrap resamples")
    ap.add_argument("--db", default=TAPE_DB, help="tape DB path (opened READ-ONLY)")
    ap.add_argument("--json-out", default=None, help="optional path to dump full result JSON")
    args = ap.parse_args(argv)

    con = _connect_ro(args.db)
    try:
        groups = load_groups(con, args.city)
        if args.limit is not None:
            groups = dict(list(sorted(groups.items()))[:args.limit])
        trades, drops = reconstruct(con, groups)
    finally:
        con.close()

    calib = calibration_table(trades)
    pnl = make_pnl(trades, args.longshot_max)
    mean, lo, hi, n_blocks = block_bootstrap(pnl, args.n_boot)

    # ── report ──
    print("=" * 78)
    print(f"S1 LONGSHOT-FADE REAL-ASK PROBE  city={args.city or 'ALL'}  "
          f"longshot_max={args.longshot_max}")
    print("=" * 78)
    print(f"groups: total={drops['groups_total']} usable={drops['groups_usable']} "
          f"(no_close={drops['groups_no_close']} incomplete_book={drops['groups_incomplete_book']} "
          f"crossed={drops['groups_crossed']})")
    print(f"brackets: total={drops['brackets_total']} priced(trades)={len(trades)} "
          f"(no_book={drops['brackets_no_book']} ask>=1={drops['brackets_ask_ge_1']} "
          f"crossed={drops['brackets_crossed']})")
    if trades:
        ovs = [t["overround_absorbed"] for t in trades]
        print(f"overround at T-24h: mean={np.mean(ovs):.4f} median={np.median(ovs):.4f} "
              f"min={min(ovs):.4f} max={max(ovs):.4f}  (price_source_tag=real_ask)")

    print("\nCALIBRATION (win-rate vs implied prob, 5c bins):")
    print(f"  {'bin':<14}{'n':>6}{'mean_implied':>14}{'win_rate':>10}{'gap':>9}")
    for r in calib:
        print(f"  {r['bin']:<14}{r['n']:>6}{r['mean_implied_prob']:>14}"
              f"{r['realized_win_rate']:>10}{r['calibration_gap']:>9}")

    print(f"\nMAKER NO-ON-LONGSHOT RULE (implied<{args.longshot_max}): "
          f"n_trades={len(pnl)}  blocks(contract-days)={n_blocks}")
    print(f"  cost model: spread={HAIRCUT_SPREAD} maker_fee={MAKER_FEE} fill_prob={FILL_PROB}")
    print(f"  mean expected net P&L/trade = ${mean:+.5f}")
    print(f"  95% block-bootstrap CI       = [${lo:+.5f}, ${hi:+.5f}]  (n_boot={args.n_boot})")
    clears = lo > 0.0
    print(f"\n  VERDICT: lower CI bound {'STRICTLY CLEARS' if clears else 'does NOT clear'} "
          f"zero -> {'EDGE (graduate)' if clears else 'NO EDGE (null result)'}")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps({
            "city": args.city, "longshot_max": args.longshot_max,
            "cost_model": {"spread": HAIRCUT_SPREAD, "maker_fee": MAKER_FEE, "fill_prob": FILL_PROB},
            "drops": drops, "n_trades_priced": len(trades),
            "n_longshot_trades": len(pnl), "n_blocks": n_blocks,
            "calibration": calib,
            "net_pnl_mean": mean, "net_pnl_ci95": [lo, hi], "n_boot": args.n_boot,
            "verdict_clears_zero": clears,
            "sample_trades": pnl[:20],
        }, indent=2, default=str))
        print(f"\nwrote {args.json_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
