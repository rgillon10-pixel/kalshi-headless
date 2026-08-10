#!/usr/bin/env python3
"""q56_s80_print_vwap_overshoot_maker_fade.py — Q56 / S80 binding test.

LOOP-QUEUE.md Q56 (S80 milestone) · kb/strategies/00-index.md row S80
("Print-VWAP-overshoot contrarian maker fade on late-flow sports moneylines").

READ-ONLY, FULLY OFFLINE. Every byte read comes from already-committed tape
(`tape/kalshi_trades/`, `tape/orderbook_depth/`) plus already-committed settlement
(`core.settlement_sources`, all `broker_truth`). There is NO network path in this module,
no credential read, no order of any kind — not even a paper order. A verifier re-runs it
with the network unplugged and gets byte-identical numbers.

---------------------------------------------------------------------------------------
MECHANISM UNDER TEST (as registered 2026-08-10, direction fixed BEFORE this build)
---------------------------------------------------------------------------------------
Late in a Kalshi sports moneyline, retail chases the side that is winning, pushing executed
prints (`tape/kalshi_trades/`, `broker_truth`) away from settlement-fair. A MAKER resting on
the TRAILING side of that chase is filled by it, and collects the overshoot — profitable iff
the overshoot exceeds the maker fee.

The DIRECTION of the trade ("rest on the TRAILING side") is pre-registered by the S80 registry
row, which was written by the 2026-08-10 Q21 round-#26 idea-gen pass and its independent
verifier attack, i.e. BEFORE any line of this probe existed. That external pre-registration is
what makes the headline direction honest; the FREE PARAMETERS below (the trailing window, the
print minima, the trigger threshold) were chosen at build time by this probe's author, so every
one of them is swept in `sensitivity_grid` and the whole grid is reported, verdict or no verdict.
The exact sign-flip of the registered trade is ALSO computed (`mirror_leg`) and is DESCRIPTIVE
ONLY — it is a post-hoc direction and may never be quoted as a verdict (L41's family of
selection artifacts; a mirror that "works" is the same one number read backwards).

---------------------------------------------------------------------------------------
SIGNAL (look-ahead-free by construction)
---------------------------------------------------------------------------------------
For a market ticker T and a book snapshot at t_i (interval (t_i, t_{i+1}]):

  anchor_vwap  = volume-weighted mean `yes_price` over prints on T with
                 created_time <  t_i - RECENT_WINDOW      (>= MIN_ANCHOR_PRINTS prints)
  recent_vwap  = volume-weighted mean `yes_price` over prints on T with
                 t_i - RECENT_WINDOW <= created_time < t_i (>= MIN_RECENT_PRINTS prints)
  chase        = recent_vwap - anchor_vwap

Both windows end STRICTLY BEFORE the snapshot instant, the resting price is read AT the
snapshot, and the fill evidence comes from prints STRICTLY AFTER it. No settlement value is
consulted anywhere upstream of the leg's construction.

TRIGGER: abs(chase) >= OVERSHOOT_MIN. `OVERSHOOT_MIN` defaults to 2 ticks (0.02) because the
Kalshi maker fee is a FLAT $0.01 on the whole interior price range (`fee_per_contract` rounds
`MAKER_FEE_RATE * p * (1-p)` UP to the cent, so it is $0.01 for every p in ~[0.006, 0.994] —
L18/L30), and a trigger inside the fee cannot pay for itself even when it is right.

LEG (the registered "rest on the TRAILING side"):
  chase > 0  (YES was chased UP)   -> trailing side is NO  -> rest a NO  bid at `best_no_bid`
  chase < 0  (YES was dumped DOWN) -> trailing side is YES -> rest a YES bid at `best_yes_bid`
Both are the same economic trade written on the two available ladders; a resting NO bid at q
IS the resting YES offer at 1-q on Kalshi's single book.

---------------------------------------------------------------------------------------
FILL MODEL (queue-aware, L39-free — S14/S19/S21/S23/Q51 discipline)
---------------------------------------------------------------------------------------
This is NOT a candlestick "the price printed through my level" proxy (L39) and NOT a
queue-departure turnover proxy (L48). Fills are read off `broker_truth` executed prints:

  queue_ahead = sum of resting sizes on OUR OWN ladder at price >= our bid, observed at t_i
                (price-time priority: everyone at or above our price fills first; we rest at
                the touch, so this is the size sitting at the touch). Sizes are FLOATS (L47).

  consuming volume in (t_i, t_{i+1}]:
    NO-bid  leg: prints with `taker_book_side == "bid"` (a taker whose own order sat on the
                 BID is a BUYER and LIFTS a resting offer; our NO bid IS that offer) and
                 `yes_price >= 1 - our_no_bid`.
    YES-bid leg: prints with `taker_book_side == "ask"` (a taker whose own order sat on the
                 ASK is a SELLER and HITS a resting bid) and `yes_price <= our_yes_bid`.
  The orientation above is the CORRECTED one (Q51 milestone 2, measured on committed tape;
  reading it the other way inverts every fill). See collection/kalshi_trades.py's banner.

  FILL iff cumulative consuming volume STRICTLY exceeds queue_ahead. The `trade_id` of the
  print that crosses the queue is persisted on the row; a synthesised fill cannot occur here
  by construction (the predicate reads a print or returns False).

P&L per FILLED contract, held to settlement (no exit modelling, no mid marks):
    payout(broker_truth) - fill_price(real_bid) - fee_per_contract(fill_price, MAKER_FEE_RATE)
The losing leg (our side settles worthless) is fully in the P&L and is NEVER conditioned away:
the fill predicate never sees an outcome, so adverse fills are included by construction (G2).

---------------------------------------------------------------------------------------
GATES / KILL CONDITIONS (from the Q56 spec; none may be weakened)
---------------------------------------------------------------------------------------
  K1  overshoot within the maker fee  -> KILL. Measured as the per-ticker print-VWAP minus
      `broker_truth` settlement, aligned to the fade direction, block-bootstrapped by GAME.
      If the aligned gross overshoot does not exceed the flat $0.01 maker fee, the mechanism
      cannot pay for its own execution and nothing downstream can rescue it.
  K2  fillable population < 10 GAMES  -> DEAD-by-adequacy (L41 floor), not a CI falsification.
  K3  CI <= 0 (or fails `bootstrap_verdict_admissible` / `clears_tick_magnitude`) -> KILL.

  Bootstrap unit is the GAME (`event_ticker`), never the outcome and never the interval (L6).
  n_boot=10000, seed=42. Reported beside `n_units`: Kish effective n (L322) and the
  INFORMATIVE unit count (units carrying >= 1 non-zero leg, L326) — a design with a
  structural zero (an unfilled maker leg) must quote both.
  Maker fee 0.0175 via `core.pricing.MAKER_FEE_RATE` ONLY (L5 — a 4x taker overcharge sank an
  S13 draft; `scripts/invariants.py::no_handrolled_fee_rate` forbids a local literal).

---------------------------------------------------------------------------------------
BOOK-CADENCE RECONCILIATION (owed by the Q56 spec — L283 scope)
---------------------------------------------------------------------------------------
`cadence_report()` measures the intra-ticker consecutive-snapshot gap in `tape/orderbook_depth/`
on three populations (all tickers / traded tickers / traded sports-GAME tickers) and reports
the pooled median AND the median-of-per-ticker-medians plus quartiles, so the ~29-min figure
the round-#26 verifier measured and the "~3h book cadence" figure the graveyard quotes can be
placed on the same axis instead of contradicting each other in prose.

Run:
    python3 scripts/q56_s80_print_vwap_overshoot_maker_fade.py
    python3 scripts/q56_s80_print_vwap_overshoot_maker_fade.py --json-out reports/x.json
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.bootstrap import (block_bootstrap, bootstrap_verdict_admissible,  # noqa: E402
                            clears_tick_magnitude, kish_effective_n)
from core.io import REPO_ROOT, write_report  # noqa: E402
from core.pricing import MAKER_FEE_RATE, fee_per_contract  # noqa: E402
from core.settlement_sources import resolve_market_results  # noqa: E402
from core.timeutil import parse_iso_utc  # noqa: E402

TRADES_GLOB = str(REPO_ROOT / "tape" / "kalshi_trades" / "dt=*.jsonl")
DEPTH_GLOB = str(REPO_ROOT / "tape" / "orderbook_depth" / "dt=*.jsonl")
DEFAULT_REPORT_STEM = "q56_s80_print_vwap_overshoot_maker_fade"

# --- free parameters (author-chosen at build time; every one is swept, see sensitivity_grid)
RECENT_WINDOW_MIN = 30      # trailing "recent flow" window, minutes (~ the measured book cadence)
MIN_ANCHOR_PRINTS = 5       # prints required in the pre-window anchor leg
MIN_RECENT_PRINTS = 3       # prints required in the recent leg
OVERSHOOT_MIN = 0.02        # trigger threshold on |chase|, in dollars (2 ticks > the 1c maker fee)
THETA_GRID = (0.01, 0.02, 0.03, 0.05)
WINDOW_GRID_MIN = (15, 30, 60)

# --- fixed gates (NOT free parameters)
PRICE_TICK = 0.01           # Kalshi minimum tick (L27 magnitude gate)
MIN_CI_UNITS = 10           # L41 unit floor (games)
N_BOOT = 10000
SEED = 42
_EPS = 1e-9

PRICE_SOURCE_TAGS = {
    "fill_price": "real_bid",       # the resting maker price, read off the depth ladder touch
    "fill_evidence": "broker_truth",  # the executed print that crosses our queue
    "signal": "broker_truth",       # print VWAPs are executed-trade facts
    "settlement": "broker_truth",   # core.settlement_sources
}


# --------------------------------------------------------------------------- #
# Pure ticker helpers
# --------------------------------------------------------------------------- #
def series_of(market_ticker: str) -> str:
    """'KXMLBGAME-26JUL07AAABBB-AAA' -> 'KXMLBGAME'."""
    return market_ticker.split("-", 1)[0]


def event_ticker_of(market_ticker: str) -> str:
    """The GAME key — the bootstrap unit (L6). Strips the trailing outcome segment:
    'KXMLBGAME-26JUL07AAABBB-AAA' -> 'KXMLBGAME-26JUL07AAABBB'. A ticker with no trailing
    '-<code>' returns itself unchanged."""
    return market_ticker.rsplit("-", 1)[0]


def is_game_series(market_ticker: str) -> bool:
    """Sports moneyline GAME series — the S80 population. Deliberately a suffix test on the
    series token rather than an allow-list, so a newly backfilled league is not silently
    dropped from the denominator."""
    return series_of(market_ticker).endswith("GAME")


# --------------------------------------------------------------------------- #
# Pure signal helpers (no clock, no I/O — offline-testable)
# --------------------------------------------------------------------------- #
def vwap(prints: Sequence[Tuple[datetime, float, float, str, str]]) -> Optional[float]:
    """Volume-weighted mean `yes_price` over (ts, yes_price, count, taker_book_side, trade_id)
    tuples. None on an empty sequence or a non-positive total size (L23: empty is valid data,
    not a crash)."""
    tot = sum(float(p[2]) for p in prints)
    if tot <= 0:
        return None
    return sum(float(p[1]) * float(p[2]) for p in prints) / tot


def split_windows(prints: Sequence[Tuple[datetime, float, float, str, str]],
                  t_i: datetime, window: timedelta
                  ) -> Tuple[List[tuple], List[tuple]]:
    """(anchor, recent) split of prints strictly BEFORE `t_i`. anchor = created_time <
    t_i - window; recent = [t_i - window, t_i). Nothing at or after t_i is ever returned —
    this is the look-ahead firewall."""
    cut = t_i - window
    anchor = [p for p in prints if p[0] < cut]
    recent = [p for p in prints if cut <= p[0] < t_i]
    return anchor, recent


def chase_signal(prints: Sequence[tuple], t_i: datetime, window: timedelta,
                 min_anchor: int = MIN_ANCHOR_PRINTS, min_recent: int = MIN_RECENT_PRINTS
                 ) -> Optional[dict]:
    """The look-ahead-free signal at snapshot instant `t_i`, or None if either leg is too
    thin to compute. `chase` > 0 means the recent prints ran ABOVE the anchor VWAP (YES chased
    up); < 0 means YES was dumped."""
    anchor, recent = split_windows(prints, t_i, window)
    if len(anchor) < min_anchor or len(recent) < min_recent:
        return None
    av, rv = vwap(anchor), vwap(recent)
    if av is None or rv is None:
        return None
    return {"anchor_vwap": av, "recent_vwap": rv, "chase": rv - av,
            "n_anchor_prints": len(anchor), "n_recent_prints": len(recent)}


def fade_side(chase: float) -> Optional[str]:
    """The REGISTERED direction: rest on the TRAILING side of the chase.
    chase > 0 -> 'no' (rest a NO bid); chase < 0 -> 'yes'. Exactly 0 -> None (no trade)."""
    if chase > 0:
        return "no"
    if chase < 0:
        return "yes"
    return None


def mirror_side(chase: float) -> Optional[str]:
    """The exact sign-flip of `fade_side`. DESCRIPTIVE ONLY — a post-hoc direction is not a
    verdict and this probe never reports a CI for it as one."""
    s = fade_side(chase)
    if s is None:
        return None
    return "yes" if s == "no" else "no"


# --------------------------------------------------------------------------- #
# Pure queue / fill helpers (sizes are FLOATS, L47; an empty ladder is VALID, L23)
# --------------------------------------------------------------------------- #
def queue_ahead_at(ladder: Optional[Sequence[Sequence[float]]], price: float) -> float:
    """Resting size at price >= `price` on our own ladder — everyone at or above our bid has
    priority over a newly rested order. Returns 0.0 on an empty/None ladder (L23)."""
    if not ladder:
        return 0.0
    return float(sum(float(lvl[1]) for lvl in ladder
                     if lvl and float(lvl[0]) >= price - _EPS))


def print_consumes(side: str, bid: float, yes_price: float, taker_book_side: str) -> bool:
    """Does this executed print consume a resting maker bid of `side` at `bid`?

    NO-bid  at q  == a YES offer at 1-q -> lifted by a BUYER  (`taker_book_side == 'bid'`)
                                            printing at yes_price >= 1 - q.
    YES-bid at p               -> hit    by a SELLER (`taker_book_side == 'ask'`)
                                            printing at yes_price <= p.
    (Q51-m2 corrected orientation: `taker_book_side` names the side the TAKER'S OWN order sat
    on, so a taker holding a BID lifts the ASK.)"""
    if side == "no":
        return taker_book_side == "bid" and yes_price >= (1.0 - bid) - _EPS
    if side == "yes":
        return taker_book_side == "ask" and yes_price <= bid + _EPS
    return False


def simulate_fill(side: str, bid: float, queue_ahead: float,
                  window_prints: Sequence[Tuple[datetime, float, float, str, str]]
                  ) -> dict:
    """Walk the interval's executed prints in time order and fill once cumulative consuming
    volume STRICTLY exceeds `queue_ahead`. Returns the crossing print's `trade_id` so every
    fill traces to a `broker_truth` record."""
    cum = 0.0
    for ts, yes_price, count, tbs, trade_id in window_prints:
        if not print_consumes(side, bid, float(yes_price), tbs):
            continue
        cum += float(count)
        if cum > queue_ahead + _EPS:
            return {"filled": True, "fill_trade_id": trade_id,
                    "consuming_volume": cum, "queue_ahead": queue_ahead}
    return {"filled": False, "fill_trade_id": None,
            "consuming_volume": cum, "queue_ahead": queue_ahead}


def leg_pnl(side: str, fill_price: float, result: str) -> float:
    """Net dollars per FILLED contract held to settlement. `result` is Kalshi's own binary
    `broker_truth` result ('yes'/'no'). The losing leg is fully priced, never dropped."""
    won = (side == "yes" and result == "yes") or (side == "no" and result == "no")
    payout = 1.0 if won else 0.0
    return payout - fill_price - fee_per_contract(fill_price, MAKER_FEE_RATE)


# --------------------------------------------------------------------------- #
# Loaders (committed tape only)
# --------------------------------------------------------------------------- #
def load_prints(trades_glob: str = TRADES_GLOB, sports_only: bool = True
                ) -> Dict[str, List[Tuple[datetime, float, float, str, str]]]:
    """Per-ticker executed prints, sorted by (created_time, trade_id). The trade_id tie-break
    is deliberate: the tape carries exact-timestamp ties (L-note from Q54), and read order is
    not a reproducible ordering."""
    out: Dict[str, List[tuple]] = collections.defaultdict(list)
    for path in sorted(glob.glob(trades_glob)):
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                tk = r.get("ticker")
                if not tk or (sports_only and not is_game_series(tk)):
                    continue
                ts = r.get("created_time")
                if not ts:
                    continue
                out[tk].append((parse_iso_utc(ts), float(r.get("yes_price") or 0.0),
                                float(r.get("count") or 0.0),
                                str(r.get("taker_book_side") or ""),
                                str(r.get("trade_id") or "")))
    for tk in out:
        out[tk].sort(key=lambda p: (p[0], p[4]))
    return dict(out)


def load_books(depth_glob: str = DEPTH_GLOB, wanted: Optional[Iterable[str]] = None
               ) -> Dict[str, List[dict]]:
    """Per-ticker `orderbook_depth` snapshots sorted by `captured_at`."""
    want = set(wanted) if wanted is not None else None
    out: Dict[str, List[dict]] = collections.defaultdict(list)
    for path in sorted(glob.glob(depth_glob)):
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                tk = r.get("ticker")
                if not tk or (want is not None and tk not in want):
                    continue
                out[tk].append(r)
    for tk in out:
        out[tk].sort(key=lambda r: r.get("captured_at") or "")
    return dict(out)


def settlement_map(tickers: Iterable[str]) -> Tuple[Dict[str, str], dict]:
    """(ticker -> 'yes'/'no', coverage-report dict). All `broker_truth` (L300 registry)."""
    rep = resolve_market_results(sorted(set(tickers)))
    obj = rep.to_json_obj()
    res = {k: v["result"] for k, v in obj.get("resolved", {}).items()
           if v.get("result") in ("yes", "no")}
    cov = {k: v for k, v in obj.items() if k != "resolved"}
    return res, cov


# --------------------------------------------------------------------------- #
# Book-cadence reconciliation (L283 scope, owed by the Q56 spec)
# --------------------------------------------------------------------------- #
def _gap_minutes(snaps: Sequence[dict]) -> List[float]:
    ts = sorted(parse_iso_utc(s["captured_at"]) for s in snaps if s.get("captured_at"))
    return [(b - a).total_seconds() / 60.0 for a, b in zip(ts, ts[1:])]


def _quantiles(xs: Sequence[float]) -> dict:
    xs = sorted(float(x) for x in xs)
    if not xs:
        return {"n": 0, "median": None, "p25": None, "p75": None, "p90": None}
    def q(f: float) -> float:
        if len(xs) == 1:
            return xs[0]
        i = f * (len(xs) - 1)
        lo, hi = int(i), min(int(i) + 1, len(xs) - 1)
        return xs[lo] + (xs[hi] - xs[lo]) * (i - lo)
    return {"n": len(xs), "median": statistics.median(xs),
            "p25": q(0.25), "p75": q(0.75), "p90": q(0.90)}


def cadence_report(books_by_ticker: Dict[str, List[dict]],
                   traded_tickers: Iterable[str]) -> dict:
    """L283 reconciliation. Pooled-gap and per-ticker-median views of the intra-ticker
    `orderbook_depth` revisit interval on three nested populations. The two numbers the
    graveyard and the round-#26 verifier disagree about (~3h vs ~29min) are BOTH readable
    here, because they are different statistics of the same distribution on different
    populations — not a contradiction."""
    traded = set(traded_tickers)
    pops = {
        "all_depth_tickers": list(books_by_ticker.keys()),
        "traded_tickers": [t for t in books_by_ticker if t in traded],
        "traded_sports_game_tickers": [t for t in books_by_ticker
                                       if t in traded and is_game_series(t)],
    }
    out = {}
    for name, tks in pops.items():
        pooled: List[float] = []
        per_ticker_medians: List[float] = []
        snaps_per_ticker: List[int] = []
        for t in tks:
            gaps = _gap_minutes(books_by_ticker[t])
            snaps_per_ticker.append(len(books_by_ticker[t]))
            pooled.extend(gaps)
            if gaps:
                per_ticker_medians.append(statistics.median(gaps))
        out[name] = {
            "n_tickers": len(tks),
            "snapshots_per_ticker": _quantiles(snaps_per_ticker),
            "pooled_gap_minutes": _quantiles(pooled),
            "per_ticker_median_gap_minutes": _quantiles(per_ticker_medians),
        }
    return out


# --------------------------------------------------------------------------- #
# K1 — the overshoot-vs-fee gate (print VWAP minus broker_truth settlement)
# --------------------------------------------------------------------------- #
def overshoot_rows(prints_by_ticker: Dict[str, List[tuple]],
                   results: Dict[str, str]) -> List[dict]:
    """Per settled ticker: full-sample print VWAP vs its `broker_truth` settlement value.

    `overshoot` = VWAP - settlement. Positive = the tape's prints sat ABOVE what the market
    was worth. `fade_gross` is that overshoot ALIGNED to the registered trade: a maker who
    rests on the trailing side is short the chased side, so its gross per-contract edge is
    +overshoot when the chased side is YES and -overshoot when it is NO. `chased_side` is
    taken from the ticker's own VWAP level (>= 0.5 means the market IS the chased/leading
    side), which is the only chase proxy available at full-sample granularity."""
    rows = []
    for tk, prs in prints_by_ticker.items():
        if tk not in results:
            continue
        v = vwap(prs)
        if v is None:
            continue
        settle = 1.0 if results[tk] == "yes" else 0.0
        overshoot = v - settle
        chased_side = "yes" if v >= 0.5 else "no"
        rows.append({
            "ticker": tk, "game": event_ticker_of(tk), "n_prints": len(prs),
            "vwap": v, "settlement_value": settle, "overshoot": overshoot,
            "chased_side": chased_side,
            "fade_gross": overshoot if chased_side == "yes" else -overshoot,
        })
    return rows


def overshoot_gate(rows: Sequence[dict], *, fee: Optional[float] = None,
                   n_boot: int = N_BOOT, seed: int = SEED) -> dict:
    """K1. Block-bootstrap the fade-aligned gross overshoot by GAME (L6) and compare it to the
    flat maker fee. `passes` is True only if the point estimate STRICTLY exceeds the fee — the
    kill reads 'overshoot within the maker fee'.

    The fee defaults to `core.pricing.fee_per_contract` at the MAKER rate, bound here in this
    function's own scope — L228: a fee threaded in as a caller-supplied scalar is exactly how a
    flat non-schedule rate survived 16 days and decided a verdict. The keyword stays only so a
    test can exercise the comparison at a chosen floor."""
    if fee is None:
        fee = fee_per_contract(0.5, MAKER_FEE_RATE)
    units: Dict[str, List[float]] = collections.defaultdict(list)
    for r in rows:
        units[r["game"]].append(float(r["fade_gross"]))
    if not units:
        return {"n_rows": 0, "n_units": 0, "mean": None, "ci95": [None, None],
                "maker_fee": fee, "passes": False, "reason": "empty"}
    boot = block_bootstrap(dict(units), n_boot=n_boot, seed=seed)
    mean = boot["mean"]
    by_side = {}
    for side in ("yes", "no"):
        vals = [r["overshoot"] for r in rows if r["chased_side"] == side]
        by_side[side] = {"n": len(vals),
                         "mean_overshoot": statistics.mean(vals) if vals else None,
                         "mean_vwap": (statistics.mean(r["vwap"] for r in rows
                                                       if r["chased_side"] == side)
                                       if vals else None),
                         "settlement_rate": (statistics.mean(r["settlement_value"] for r in rows
                                                             if r["chased_side"] == side)
                                             if vals else None)}
    return {"n_rows": len(rows), "n_units": len(units), "mean": mean,
            "ci95": list(boot["ci95"]), "maker_fee": fee,
            "passes": bool(mean is not None and mean > fee + _EPS),
            "by_chased_side": by_side,
            "price_source_tags": {"vwap": "broker_truth", "settlement": "broker_truth"}}


# --------------------------------------------------------------------------- #
# Candidate construction + scoring
# --------------------------------------------------------------------------- #
def build_candidates(prints_by_ticker: Dict[str, List[tuple]],
                     books_by_ticker: Dict[str, List[dict]],
                     results: Dict[str, str], *,
                     window_min: int = RECENT_WINDOW_MIN,
                     theta: float = OVERSHOOT_MIN,
                     min_anchor: int = MIN_ANCHOR_PRINTS,
                     min_recent: int = MIN_RECENT_PRINTS) -> Tuple[List[dict], dict]:
    """One candidate per (ticker, book interval) that has a computable signal, a triggered
    |chase|, a settled ticker and a two-sided touch on the leg's own ladder. Fully
    outcome-blind up to the point the P&L is scored."""
    window = timedelta(minutes=window_min)
    rows: List[dict] = []
    stats: collections.Counter = collections.Counter()
    for tk, snaps in sorted(books_by_ticker.items()):
        prs = prints_by_ticker.get(tk) or []
        if not prs:
            stats["ticker_no_prints"] += 1
            continue
        if tk not in results:
            stats["ticker_unsettled"] += 1
            continue
        for i in range(len(snaps) - 1):
            b, nxt = snaps[i], snaps[i + 1]
            if not b.get("captured_at") or not nxt.get("captured_at"):
                continue
            t_i = parse_iso_utc(b["captured_at"])
            t_n = parse_iso_utc(nxt["captured_at"])
            stats["intervals_seen"] += 1
            sig = chase_signal(prs, t_i, window, min_anchor, min_recent)
            if sig is None:
                stats["signal_uncomputable"] += 1
                continue
            stats["signal_computable"] += 1
            if abs(sig["chase"]) < theta - _EPS:
                stats["below_theta"] += 1
                continue
            stats["triggered"] += 1
            side = fade_side(sig["chase"])
            if side is None:
                stats["zero_chase"] += 1
                continue
            touch = {"no": b.get("best_no_bid"), "yes": b.get("best_yes_bid")}
            touch = {k: (float(v) if v is not None else None) for k, v in touch.items()}
            queue = {k: (queue_ahead_at((b.get("no_bids") if k == "no"
                                         else b.get("yes_bids")) or [], v)
                         if v is not None else None)
                     for k, v in touch.items()}
            bid, qa = touch[side], queue[side]
            if bid is None:
                stats["no_touch_on_leg"] += 1
                continue
            win_prints = [p for p in prs if t_i < p[0] <= t_n]
            rows.append({
                "ticker": tk, "game": event_ticker_of(tk), "series": series_of(tk),
                "t_i": b["captured_at"], "t_next": nxt["captured_at"],
                "interval_minutes": (t_n - t_i).total_seconds() / 60.0,
                "anchor_vwap": sig["anchor_vwap"], "recent_vwap": sig["recent_vwap"],
                "chase": sig["chase"], "n_anchor_prints": sig["n_anchor_prints"],
                "n_recent_prints": sig["n_recent_prints"],
                "side": side, "mirror_side": mirror_side(sig["chase"]),
                "fill_price": bid, "queue_ahead": qa,
                "n_window_prints": len(win_prints),
                "_window_prints": win_prints, "_touch": touch, "_queue": queue,
                "price_source_tag": "real_bid",
            })
            stats["candidates"] += 1
    return rows, dict(stats)


def score_rows(rows: List[dict], results: Dict[str, str], *, side_key: str = "side"
               ) -> List[dict]:
    """Attach the queue-aware fill outcome and the settlement P&L. `side_key` selects which
    direction to score — 'side' is the REGISTERED leg; 'mirror_side' is the descriptive
    sign-flip."""
    out = []
    for r in rows:
        side = r[side_key]
        if side is None:
            continue
        # each leg rests on ITS OWN ladder, so the mirror needs its own touch/queue
        bid = r["_touch"].get(side)
        qa = r["_queue"].get(side)
        if bid is None or qa is None:
            continue
        sim = simulate_fill(side, float(bid), float(qa), r["_window_prints"])
        res = results[r["ticker"]]
        pnl = leg_pnl(side, float(bid), res) if sim["filled"] else 0.0
        row = {k: v for k, v in r.items() if not k.startswith("_")}
        row.update({"scored_side": side, "scored_fill_price": float(bid),
                    "scored_queue_ahead": float(qa),
                    "filled": sim["filled"], "fill_trade_id": sim["fill_trade_id"],
                    "consuming_volume": sim["consuming_volume"],
                    "settlement_result": res, "pnl": pnl,
                    "price_source_tag": "real_bid",
                    "fill_evidence_tag": "broker_truth" if sim["filled"] else None,
                    "settlement_tag": "broker_truth"})
        out.append(row)
    return out


def adverse_selection_decomposition(scored: Sequence[dict],
                                    prints_by_ticker: Dict[str, List[tuple]],
                                    results: Dict[str, str]) -> dict:
    """Why a large STATIC print-VWAP overshoot need not be a maker edge.

    On the FILLED population only, compare three per-contract quantities for the side we
    actually rested on:
      static_gross_at_vwap  = settlement_value(our side) - the ticker's full-sample print VWAP
                              (what the overshoot is worth to a price-taker at the average print)
      realized_gross_at_bid = settlement_value(our side) - our actual `real_bid` fill price
                              (what the SAME side is worth at the strictly BETTER maker price)
      realized_net          = realized_gross_at_bid - the flat maker fee
    A resting bid is strictly cheaper than the average print, so under RANDOM fills
    `realized_gross_at_bid` must EXCEED `static_gross_at_vwap`. Any shortfall is the
    adverse-selection cost of the fills the flow actually gave us."""
    static, realized, net = [], [], []
    for r in scored:
        if not r["filled"]:
            continue
        tk = r["ticker"]
        v = vwap(prints_by_ticker.get(tk) or [])
        if v is None or tk not in results:
            continue
        side = r["scored_side"]
        won = (side == "yes" and results[tk] == "yes") or (side == "no" and results[tk] == "no")
        settle_side = 1.0 if won else 0.0
        entry_vwap = v if side == "yes" else 1.0 - v
        static.append(settle_side - entry_vwap)
        realized.append(settle_side - float(r["scored_fill_price"]))
        net.append(float(r["pnl"]))
    if not static:
        return {"n_fills": 0}
    m_static = statistics.mean(static)
    m_real = statistics.mean(realized)
    return {"n_fills": len(static),
            "static_gross_at_vwap": m_static,
            "realized_gross_at_bid": m_real,
            "realized_net_after_maker_fee": statistics.mean(net),
            "adverse_selection_cost": m_static - m_real,
            "note": ("negative adverse_selection_cost means the fills we got were BETTER than "
                     "the average print; positive means the flow selected against us"),
            "price_source_tags": {"entry_vwap": "broker_truth", "fill_price": "real_bid",
                                  "settlement": "broker_truth"}}


def _unit_values(scored: Sequence[dict], *, only_filled: bool) -> Dict[str, List[float]]:
    units: Dict[str, List[float]] = collections.defaultdict(list)
    for r in scored:
        if only_filled and not r["filled"]:
            continue
        units[r["game"]].append(float(r["pnl"]))
    return dict(units)


def bootstrap_branch(scored: Sequence[dict], *, only_filled: bool,
                     n_boot: int = N_BOOT, seed: int = SEED,
                     min_units: int = MIN_CI_UNITS) -> dict:
    """One bootstrap branch, with every adequacy number the house rules require beside it:
    L41 admissibility, L27 tick magnitude, L322 Kish effective n, L326 informative units."""
    units = _unit_values(scored, only_filled=only_filled)
    n_legs = sum(len(v) for v in units.values())
    if not units or n_legs == 0:
        return {"n_units": 0, "n_legs": 0, "mean": None, "ci95": [None, None],
                "admissible": {"admissible": False, "reasons": ["empty"]},
                "clears_tick_magnitude": False, "kish": None,
                "n_informative_units": 0, "verdict": "EMPTY"}
    boot = block_bootstrap(units, n_boot=n_boot, seed=seed)
    adm = bootstrap_verdict_admissible(units, min_units=min_units)
    kish = kish_effective_n([len(v) for v in units.values()])
    informative = sum(1 for v in units.values() if any(abs(x) > _EPS for x in v))
    ci = list(boot["ci95"])
    tick_ok = clears_tick_magnitude(ci, tick=PRICE_TICK)
    if not adm["admissible"]:
        verdict = "INADMISSIBLE"
    elif ci[0] is not None and ci[0] > 0 and tick_ok:
        verdict = "ALIVE"
    elif ci[1] is not None and ci[1] < 0:
        verdict = "DEAD-negative-CI"
    else:
        verdict = "DEAD-straddles-zero"
    return {"n_units": len(units), "n_legs": n_legs,
            "n_fills": sum(1 for r in scored if r["filled"]),
            "mean": boot["mean"], "ci95": ci,
            "admissible": adm, "clears_tick_magnitude": tick_ok,
            "kish_effective_n": kish, "n_informative_units": informative,
            "verdict": verdict,
            "price_source_tags": dict(PRICE_SOURCE_TAGS)}


def sensitivity_grid(prints_by_ticker, books_by_ticker, results, *,
                     thetas: Sequence[float] = THETA_GRID,
                     windows: Sequence[int] = WINDOW_GRID_MIN) -> List[dict]:
    """Every (theta, window) cell of the author-chosen free parameters, so a reader can see
    that the verdict is not an artifact of the defaults."""
    cells = []
    for w in windows:
        for th in thetas:
            rows, _ = build_candidates(prints_by_ticker, books_by_ticker, results,
                                       window_min=w, theta=th)
            scored = score_rows(rows, results)
            filled = [r for r in scored if r["filled"]]
            cond = bootstrap_branch(scored, only_filled=True)
            allb = bootstrap_branch(scored, only_filled=False)
            cells.append({
                "window_min": w, "theta": th,
                "n_candidates": len(scored), "n_fills": len(filled),
                "fill_rate": (len(filled) / len(scored)) if scored else None,
                "n_games_all": allb["n_units"], "n_games_filled": cond["n_units"],
                "mean_all": allb["mean"], "ci95_all": allb["ci95"],
                "verdict_all": allb["verdict"],
                "mean_conditional_on_fill": cond["mean"], "ci95_conditional_on_fill": cond["ci95"],
                "verdict_conditional_on_fill": cond["verdict"],
            })
    return cells


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def run(*, trades_glob: str = TRADES_GLOB, depth_glob: str = DEPTH_GLOB,
        window_min: int = RECENT_WINDOW_MIN, theta: float = OVERSHOOT_MIN,
        n_boot: int = N_BOOT, seed: int = SEED, with_grid: bool = True) -> dict:
    prints_by_ticker = load_prints(trades_glob)
    books_by_ticker = load_books(depth_glob, wanted=prints_by_ticker.keys())
    results, coverage = settlement_map(prints_by_ticker.keys())

    cadence = cadence_report(load_books(depth_glob), prints_by_ticker.keys())

    fee = fee_per_contract(0.5, MAKER_FEE_RATE)
    osr = overshoot_rows(prints_by_ticker, results)
    k1 = overshoot_gate(osr, fee=fee, n_boot=n_boot, seed=seed)

    rows, popstats = build_candidates(prints_by_ticker, books_by_ticker, results,
                                      window_min=window_min, theta=theta)
    scored = score_rows(rows, results)
    filled = [r for r in scored if r["filled"]]

    branch_all = bootstrap_branch(scored, only_filled=False, n_boot=n_boot, seed=seed)
    branch_fill = bootstrap_branch(scored, only_filled=True, n_boot=n_boot, seed=seed)

    n_games_filled = branch_fill["n_units"]
    kills = []
    if not k1["passes"]:
        kills.append("K1_overshoot_within_maker_fee")
    if n_games_filled < MIN_CI_UNITS:
        kills.append("K2_fill_population_below_game_floor")
    if branch_all["verdict"] not in ("ALIVE",):
        kills.append("K3_headline_ci_not_positive")

    verdict = "DEAD" if kills else "ALIVE"

    # ---- mirror leg: the exact sign-flip of the registered direction. DESCRIPTIVE ONLY.
    # A post-hoc direction chosen after seeing the headline is not a verdict (L41 family);
    # it is reported so the finding can say WHY the registered sign failed, never as an edge.
    mirror_scored = score_rows(rows, results, side_key="mirror_side")
    mirror = {
        "WARNING": ("post-hoc sign-flip of the pre-registered direction; DESCRIPTIVE ONLY, "
                    "never a verdict and never grounds for a registry flip"),
        "n_candidates": len(mirror_scored),
        "n_fills": sum(1 for r in mirror_scored if r["filled"]),
        "branch_all_candidates": bootstrap_branch(mirror_scored, only_filled=False,
                                                  n_boot=n_boot, seed=seed),
        "branch_conditional_on_fill": bootstrap_branch(mirror_scored, only_filled=True,
                                                       n_boot=n_boot, seed=seed),
        "adverse_selection": adverse_selection_decomposition(mirror_scored, prints_by_ticker,
                                                             results),
    }

    payload = {
        "probe": DEFAULT_REPORT_STEM,
        "strategy": "S80",
        "queue_item": "Q56",
        "read_only": True,
        "network_calls": 0,
        "params": {"recent_window_min": window_min, "theta": theta,
                   "min_anchor_prints": MIN_ANCHOR_PRINTS,
                   "min_recent_prints": MIN_RECENT_PRINTS,
                   "n_boot": n_boot, "seed": seed,
                   "maker_fee_per_contract_at_0_50": fee,
                   "bootstrap_unit": "game (event_ticker)"},
        "price_source_tags": dict(PRICE_SOURCE_TAGS),
        "tape": {
            "n_trade_day_files": len(sorted(glob.glob(trades_glob))),
            "n_depth_day_files": len(sorted(glob.glob(depth_glob))),
            "n_traded_sports_tickers": len(prints_by_ticker),
            "n_traded_sports_games": len({event_ticker_of(t) for t in prints_by_ticker}),
            "n_prints": sum(len(v) for v in prints_by_ticker.values()),
            "n_tickers_with_depth": len(books_by_ticker),
        },
        "settlement_coverage": coverage,
        "cadence_reconciliation": cadence,
        "gate_K1_overshoot_vs_maker_fee": k1,
        "population": popstats,
        "fill": {
            "n_candidates": len(scored), "n_fills": len(filled),
            "fill_rate": (len(filled) / len(scored)) if scored else None,
            "n_games_with_candidate": branch_all["n_units"],
            "n_games_with_fill": n_games_filled,
            "fills_traceable_to_broker_truth_print": sum(
                1 for r in filled if r["fill_trade_id"]),
            "median_queue_ahead": (statistics.median([r["scored_queue_ahead"] for r in scored])
                                   if scored else None),
            "median_fill_price_real_bid": (statistics.median([r["scored_fill_price"]
                                                              for r in filled])
                                           if filled else None),
        },
        "branch_all_candidates": branch_all,
        "branch_conditional_on_fill": branch_fill,
        "adverse_selection_registered_leg": adverse_selection_decomposition(
            scored, prints_by_ticker, results),
        "kill_conditions_fired": kills,
        "verdict": verdict,
        "mirror_leg_DESCRIPTIVE_ONLY": mirror,
    }
    if with_grid:
        payload["sensitivity_grid"] = sensitivity_grid(prints_by_ticker, books_by_ticker,
                                                       results)
    return payload


def _summarize(p: dict) -> str:
    b = p["branch_all_candidates"]
    c = p["branch_conditional_on_fill"]
    k1 = p["gate_K1_overshoot_vs_maker_fee"]
    lines = [
        f"S80 print-VWAP-overshoot contrarian maker fade — VERDICT {p['verdict']}",
        f"  kills fired: {p['kill_conditions_fired'] or 'none'}",
        f"  tape: {p['tape']['n_prints']} prints / {p['tape']['n_traded_sports_tickers']} tickers"
        f" / {p['tape']['n_traded_sports_games']} games",
        f"  K1 fade-aligned gross overshoot (broker_truth): mean {k1['mean']:.5f}"
        f" CI {k1['ci95']} vs maker fee ${k1['maker_fee']:.2f} -> passes={k1['passes']}",
        f"  fill: {p['fill']['n_fills']}/{p['fill']['n_candidates']}"
        f" = {p['fill']['fill_rate']} over {p['fill']['n_games_with_fill']} games",
        f"  all_candidates    mean {b['mean']} CI {b['ci95']} n_units {b['n_units']}"
        f" informative {b['n_informative_units']} -> {b['verdict']}",
        f"  conditional_on_fill mean {c['mean']} CI {c['ci95']} n_units {c['n_units']}"
        f" -> {c['verdict']}",
    ]
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--theta", type=float, default=OVERSHOOT_MIN)
    ap.add_argument("--window-min", type=int, default=RECENT_WINDOW_MIN)
    ap.add_argument("--n-boot", type=int, default=N_BOOT)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--no-grid", action="store_true")
    ap.add_argument("--json-out", default=None,
                    help="explicit output path; default writes reports/<stem>.json")
    args = ap.parse_args(argv)

    payload = run(window_min=args.window_min, theta=args.theta, n_boot=args.n_boot,
                  seed=args.seed, with_grid=not args.no_grid)
    summary = _summarize(payload)
    print(summary)
    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps(payload, indent=2, sort_keys=True))
        print(f"wrote {args.json_out}")
    else:
        path = write_report(DEFAULT_REPORT_STEM, payload, md_summary=summary)
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
