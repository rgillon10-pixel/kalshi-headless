#!/usr/bin/env python3
"""s19_wing_fade_fillsim.py — S19 / Q23: elevated-wing stale-ask MAKER fade fill-sim.

LOOP-QUEUE.md Q23, registry S19. The maker-side closer of S10 (which died as a TAKER
"fade the rich tail" trade — L26: on a genuinely-far / floor-pinned bracket `yes_bid=0`
mirrors into a `no_ask = $1.00`, so a taker short has NO fillable positive-EV price). L26
explicitly left the MAKER side untested: a resting short-YES *offer* at an elevated far-OTM
ask (0.40) is a real price whose fill rate + toxicity is empirical, not structurally
pre-dead. This probe tests that maker side and is EXPECTED TO DIE — a near-0%-fill null or a
CI that fails the L27 magnitude gate is the complete, successful outcome (it converts
S10-maker / L26 from "untested" to "tested-dead").

READ-ONLY, FULLY OFFLINE, NO NETWORK, NO ORDERS, NO AUTH. Everything is read off already-
committed tape; a stray `dt=<date>` DIRECTORY (the L25/L29 regression artifact) is skipped
by an is_file guard and never mutated.

The trade simulated (maker short-YES on each qualifying wing, held to settlement):
  - WING SELECTION (matches Q20 / `findings/2026-07-13-btc-ladder-overround-anatomy-q20.md`
    EXACTLY). A `wing_elevated` member is one that ALL of:
      * lies OUTSIDE the active band, i.e. its strike coordinate is more than +/-3 strike-
        spacings from spot. Spot = the top-level `spot.price` leg (tag `synthetic`, Coinbase)
        — a BINNING COORDINATE ONLY, never a fill price. Strike-spacing per ladder via
        `core.pricing.infer_strike_spacing` off the ladder's OWN between-band floor strikes
        (L36 — never a hardcoded $100/$20).
      * `yes_ask` above the 1c floor and inside the S19 registered band [0.20, 0.67].
      * `yes_bid == 0` (the stale one-sided condition).
    All asks are `real_ask` (`crypto_hourly` `current.outcomes[].yes_ask`).
  - ENTRY = the EARLIEST capture of each settled event-hour (maximizes the hold to close),
    the same entry S14 used — which also aligns the executed-volume window with the S14
    candle cache (see below).
  - POSITION: rest a MAKER short-YES = a resting NO bid at price `1 minus yes_ask`. Win (+premium
    = yes_ask) if the strike settles NO; lose (pay $1) if it settles YES. Fee is the flat 1c
    maker fee (L30: `fee_per_contract(P, MAKER_FEE_RATE) == 0.01` at every interior price),
    charged on fill.
  - FILL RULE — QUEUE-AWARE, NOT a candlestick print (L39). A candle `high>=ask AND vol>0`
    check is FORBIDDEN as the fill rule because Q20 measured 166-503 contracts already resting
    at these wing `no_bids`; our new offer joins the BACK of that queue. So the fill rule is:
      filled iff (the ask was touched: max realized YES trade high >= yes_ask)
                 AND (executed volume over the hold >= the queue ahead of us).
    QUEUE AHEAD = the `orderbook_depth` `no_bids` size resting at price >= `1 minus yes_ask` for
    that ticker (tag `real_bid` — the mirror of the YES-ask side per Q20: a YES offer at p is
    a NO bid at 1-p), joined by ticker + NEAREST `captured_at` (the depth sub-pass runs ~20s
    after the crypto sub-pass with a DIFFERENT capture_id). Bids at a price >= ours have
    price-or-time priority, so incoming YES-buy volume must clear all of them before reaching
    us — a correct, conservative price-time-priority queue.
    EXECUTED VOLUME + max trade high come from the S14 candlestick cache (`tape/
    s14_ladder_fillsim/`, committed tape — read OFFLINE here, never re-fetched). That cache's
    [start_ts, end_ts] window is S14's earliest-capture -> close; we re-use the same earliest
    entry and guard that the cached window matches our entry (else the wing is unmeasurable ->
    no-fill). Using the whole-window total_volume at ALL prices (not just >= our ask) is
    GENEROUS toward filling — the honest offline limitation is that we cannot price-decompose
    the candle; a near-0%-fill result under the generous rule is therefore robust.
    If EITHER the queue (no depth match) OR the executed volume (no cache / window mismatch)
    is not measurable offline, the wing is a NO-FILL, not a free assumption.
  - Depth tape starts 2026-07-07 vs crypto 2026-07-03 (L9), so only the overlapping window is
    join-eligible; join coverage is reported honestly.

Adverse selection (gate #2): the mechanism predicts the rare fills are TOXIC — a far-OTM YES
is lifted mainly when spot rushes the strike, so a fill should correlate with settling YES
against the short. We report P&L SPLIT by settle-YES-given-filled vs settle-NO-given-filled,
the fill rate, and the settle-YES rate among fills vs among all wings, so that correlation is
surfaced explicitly (and, if the sample carries zero settle-YES fills, that is reported as a
sparsity fact — the toxic loss leg UNOBSERVED, not disproven).

Gate (verdict): block-bootstrap E[P&L per event-hour] BY EVENT-HOUR (L6 — one settlement
fixes all wings within an hour; wings within an hour are correlated) via
`core.bootstrap.block_bootstrap`, with the L27 magnitude gate (`clears_tick_magnitude`). A
tiny filled population is data-adequacy (n_units too small for a testable CI), NOT a CI.

Run:
    python scripts/s19_wing_fade_fillsim.py
    python scripts/s19_wing_fade_fillsim.py --n-boot 10000 --json-out /tmp/s19.json
"""
from __future__ import annotations

import argparse
import json
import sys
from bisect import bisect_left
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.bootstrap import block_bootstrap, clears_tick_magnitude  # noqa: E402
from core.io import REPO_ROOT  # noqa: E402
from core.pricing import (  # noqa: E402
    MAKER_FEE_RATE,
    fee_per_contract,
    infer_strike_spacing,
)

CRYPTO_DIR = REPO_ROOT / "tape" / "crypto_hourly"
DEPTH_DIR = REPO_ROOT / "tape" / "orderbook_depth"
CANDLE_CACHE_DIR = REPO_ROOT / "tape" / "s14_ladder_fillsim"  # OFFLINE executed-volume source

FLOOR_ASK = 0.01              # Kalshi 1c minimum YES ask — the mechanical floor
BAND_STEPS = 3                # active band = within +/-3 strike-spacings of spot (Q20)
WING_ASK_LO = 0.20            # S19 registered band lower bound
WING_ASK_HI = 0.67            # S19 registered band upper bound
DEPTH_JOIN_MAX_DELTA_SEC = 600.0   # a depth capture must be within 10 min to count (Q20)
CANDLE_WINDOW_TOL_SEC = 120.0      # cached vol window must start within 2 min of our entry
PRICE_TICK = 0.01             # Kalshi price tick

# verdict thresholds (judgment calls, documented — see gate #4 / kill conditions):
NEAR_ZERO_FILL_RATE = 0.05    # S14's incidental wing fill rate was 2.5%; below this = fill null
MIN_CI_UNITS = 10             # fewer filled EVENT-HOURS than this = data-adequacy, not a CI


# --------------------------------------------------------------------------- #
# loading (read-only; FILES only — L25/L29 skip stray dt=<date> DIRECTORIES)
# --------------------------------------------------------------------------- #
def load_crypto_records(tape_dir: Path = CRYPTO_DIR) -> List[Dict[str, Any]]:
    """Every crypto_hourly record from the canonical *.jsonl day-files. A stray `dt=<date>`
    DIRECTORY (the L25/L29 regression) is skipped by the is_file guard. Never mutates tape."""
    records: List[Dict[str, Any]] = []
    for path in sorted(tape_dir.glob("dt=*.jsonl")):
        if not path.is_file():
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    return records


def build_settlement_map(records: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """`{settled_event_ticker: {winner_ticker, ...}}` from every record's
    `previous_settlement` (broker_truth). Exactly one member has result "yes"."""
    out: Dict[str, Dict[str, Any]] = {}
    for r in records:
        ps = r.get("previous_settlement")
        if not ps:
            continue
        et = ps.get("event_ticker")
        results = ps.get("results")
        if not et or not results:
            continue
        winners = [k for k, v in results.items() if v == "yes"]
        if len(winners) != 1:
            continue  # a valid MECE settlement has exactly one YES
        out[et] = {
            "winner_ticker": winners[0],
            "price_source_tag": ps.get("price_source_tag", "broker_truth"),
        }
    return out


def build_earliest_captures(records: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """`{event_ticker: {captured_at, series, current, spot}}` keeping the EARLIEST
    captured_at per event-hour (maximizes the hold; aligns with the S14 candle-cache
    window). Skips null/incomplete current blocks and missing spot."""
    out: Dict[str, Dict[str, Any]] = {}
    for r in records:
        cur = r.get("current")
        if not cur or not cur.get("event_ticker") or not cur.get("outcomes"):
            continue
        if not cur.get("close_time"):
            continue
        et = cur["event_ticker"]
        cap = r.get("captured_at")
        spot = (r.get("spot") or {}).get("price")
        if not cap or spot is None:
            continue
        if et not in out or cap < out[et]["captured_at"]:
            out[et] = {"captured_at": cap, "series": r.get("series"),
                       "current": cur, "spot": float(spot)}
    return out


def _parse_ts(ts: str) -> float:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


def build_depth_index(depth_dir: Path = DEPTH_DIR,
                      ticker_prefixes: Tuple[str, ...] = ("KXBTC", "KXETH")
                      ) -> Dict[str, List[Tuple[float, List[Any]]]]:
    """`{ticker: [(ts, no_bids), ...]}` sorted by ts. Keeps the full `no_bids` ladder (the
    mirror of the YES-ask side) so the queue-ahead sum can pick the right price levels.
    FILES only (L25/L29). Read-only."""
    idx: Dict[str, List[Tuple[float, List[Any]]]] = {}
    for path in sorted(depth_dir.glob("dt=*.jsonl")):
        if not path.is_file():
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                tk = r.get("ticker", "")
                if not tk.startswith(ticker_prefixes):
                    continue
                cap = r.get("captured_at")
                if not cap:
                    continue
                idx.setdefault(tk, []).append((_parse_ts(cap), r.get("no_bids") or []))
    for tk in idx:
        idx[tk].sort(key=lambda t: t[0])
    return idx


def load_candle_cache(cache_dir: Path = CANDLE_CACHE_DIR) -> Dict[str, Dict[str, Any]]:
    """The S14 candlestick summary cache, keyed by member ticker — the OFFLINE executed-
    volume source (never re-fetched here). Each record carries `total_volume`,
    `max_high_dollars`, and the [start_ts, end_ts] hold window S14 measured over. FILES
    only. Read-only."""
    cache: Dict[str, Dict[str, Any]] = {}
    if not cache_dir.exists():
        return cache
    for path in sorted(cache_dir.glob("dt=*.jsonl")):
        if not path.is_file():
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rec = json.loads(line)
                    cache[rec["ticker"]] = rec
    return cache


# --------------------------------------------------------------------------- #
# pure geometry / selection / fill-sim (unit-tested offline)
# --------------------------------------------------------------------------- #
def member_coord(o: Dict[str, Any]) -> Optional[float]:
    """A single strike coordinate for distance-from-spot binning: the midpoint of a
    `between` band, else whichever boundary strike exists for an edge member. None if
    neither is present."""
    st = o.get("strike_type")
    fs = o.get("floor_strike")
    cs = o.get("cap_strike")
    if st == "between" and fs is not None and cs is not None:
        return (float(fs) + float(cs)) / 2.0
    if fs is not None:
        return float(fs)
    if cs is not None:
        return float(cs)
    return None


def ladder_spacing(outcomes: List[Dict[str, Any]]) -> Optional[float]:
    """Strike spacing read off the ladder's own between-band floor strikes (L36 — never a
    hardcoded per-symbol width). Median consecutive gap."""
    return infer_strike_spacing(
        [o["floor_strike"] for o in outcomes
         if o.get("strike_type") == "between" and o.get("floor_strike") is not None])


def is_wing_elevated(o: Dict[str, Any], spot: float, spacing: Optional[float],
                     band_steps: int = BAND_STEPS, floor: float = FLOOR_ASK,
                     ask_lo: float = WING_ASK_LO, ask_hi: float = WING_ASK_HI) -> bool:
    """Q20's `wing_elevated` definition EXACTLY: OUTSIDE the +/-band_steps active band AND
    yes_ask above the 1c floor and inside the S19 band [ask_lo, ask_hi] AND yes_bid == 0
    (stale one-sided). Returns False when spacing/coord is underivable (cannot place it
    outside the band with confidence)."""
    if spacing is None or spacing <= 0:
        return False
    coord = member_coord(o)
    if coord is None:
        return False
    outside_band = abs(coord - spot) > band_steps * spacing
    ask = float(o["yes_ask"])
    bid = float(o.get("yes_bid") or 0.0)
    in_ask_band = (ask > floor + 1e-9) and (ask_lo - 1e-9 <= ask <= ask_hi + 1e-9)
    return outside_band and in_ask_band and (bid == 0.0)


def queue_ahead_at(no_bids: List[Any], yes_ask: float, tick: float = PRICE_TICK) -> float:
    """Contracts resting AHEAD of a newly-arriving NO bid at price `1 minus yes_ask` (tag
    `real_bid`). Price-time priority: every NO bid at price >= our price (all currently
    resting size at our level, plus anything better-priced) fills before us, so incoming
    YES-buy volume must clear it first. Sum of `no_bids` sizes at price >= (1 minus yes_ask)."""
    p_no = 1.0 - float(yes_ask)
    total = 0.0
    for level in no_bids:
        try:
            price = float(level[0])
            size = float(level[1])
        except (IndexError, TypeError, ValueError):
            continue
        if price >= p_no - tick / 2.0:
            total += size
    return total


def member_fee(yes_ask: float) -> float:
    """The flat maker fee charged on fill (L30): `fee_per_contract` at MAKER_FEE_RATE on the
    resting NO-bid fill price (1 minus yes_ask) — a flat $0.01 at every interior price. Uses the
    sanctioned fee helper (never hand-rolled)."""
    return fee_per_contract(1.0 - float(yes_ask), rate=MAKER_FEE_RATE)


def member_pnl(yes_ask: float, settle_yes: bool) -> float:
    """P&L of one filled maker short-YES held to settlement, net of the flat maker fee:
      settle NO  (win)  -> keep the premium (the yes_ask), minus the fee
      settle YES (lose) -> the yes_ask premium minus the $1 payout, minus the fee
    `yes_ask` is a plain local float here (the collectible premium), not the raw dict field."""
    fee = member_fee(yes_ask)
    if settle_yes:
        return float(yes_ask) - 1.0 - fee
    return float(yes_ask) - fee


def is_filled(max_high: Optional[float], total_volume: Optional[float], yes_ask: float,
              queue_ahead: float) -> bool:
    """Queue-aware fill (NOT an L39 candle print). Filled iff the ask was TOUCHED (max
    realized YES trade high >= yes_ask, i.e. a taker actually lifted at/through our ask)
    AND the executed volume over the hold cleared the queue ahead of us
    (total_volume >= queue_ahead). Unmeasurable volume/high (None) -> no fill."""
    if max_high is None or total_volume is None:
        return False
    if max_high + 1e-9 < yes_ask:   # ask never touched -> no lift -> no fill
        return False
    return total_volume >= queue_ahead - 1e-9


# --------------------------------------------------------------------------- #
# depth join
# --------------------------------------------------------------------------- #
def nearest_no_bids(idx: Dict[str, List[Tuple[float, List[Any]]]], ticker: str, ts: float,
                    max_delta_sec: float = DEPTH_JOIN_MAX_DELTA_SEC
                    ) -> Optional[List[Any]]:
    """The `no_bids` ladder from the depth capture of `ticker` NEAREST in time to `ts`, or
    None if no capture is within `max_delta_sec`. Binary-searches the ticker's own sorted
    timeline (crypto + depth sub-passes share tickers but not capture_id; ~20s apart)."""
    series = idx.get(ticker)
    if not series:
        return None
    times = [t[0] for t in series]
    i = bisect_left(times, ts)
    best: Optional[Tuple[float, List[Any]]] = None
    for j in (i - 1, i):
        if 0 <= j < len(series):
            cand = series[j]
            if best is None or abs(cand[0] - ts) < abs(best[0] - ts):
                best = cand
    if best is None or abs(best[0] - ts) > max_delta_sec:
        return None
    return best[1]


# --------------------------------------------------------------------------- #
# per-wing simulation
# --------------------------------------------------------------------------- #
def simulate(records: List[Dict[str, Any]],
             depth_idx: Dict[str, List[Tuple[float, List[Any]]]],
             candle_cache: Dict[str, Dict[str, Any]],
             band_steps: int = BAND_STEPS) -> Dict[str, Any]:
    """Enumerate every qualifying wing over all settled event-hours, run the queue-aware
    fill-sim, and return the descriptive counts + per-filled-wing P&L grouped by event-hour."""
    settle = build_settlement_map(records)
    earliest = build_earliest_captures(records)

    n_wing = 0
    n_joinable = 0          # both queue AND volume measurable offline
    n_depth_only = 0        # queue measurable
    n_settle_yes_all = 0
    n_fill = 0
    fills_settle_yes = 0
    fills_settle_no = 0
    n_touched = 0           # ask ever touched (max_high >= ask), the observability precheck
    per_event_pnl: Dict[str, List[float]] = {}
    fill_rows: List[Dict[str, Any]] = []

    for et in sorted(earliest):
        if et not in settle:
            continue
        e = earliest[et]
        cur = e["current"]
        outs = cur["outcomes"]
        spot = e["spot"]
        spacing = ladder_spacing(outs)
        if spacing is None:
            continue
        ts = _parse_ts(e["captured_at"])
        winner = settle[et]["winner_ticker"]
        for o in outs:
            if not is_wing_elevated(o, spot, spacing, band_steps):
                continue
            n_wing += 1
            ask = float(o["yes_ask"])
            tk = o["ticker"]
            settle_yes = (tk == winner)
            if settle_yes:
                n_settle_yes_all += 1

            no_bids = nearest_no_bids(depth_idx, tk, ts)
            rec = candle_cache.get(tk)
            # measurability: need BOTH the queue (depth) AND the executed volume (candle)
            if no_bids is None or rec is None:
                continue
            # guard the cached volume window aligns with our entry (else unmeasurable)
            start_ts = rec.get("start_ts")
            if start_ts is None or abs(float(start_ts) - ts) > CANDLE_WINDOW_TOL_SEC:
                continue
            n_depth_only += 1
            n_joinable += 1

            queue_ahead = queue_ahead_at(no_bids, ask)
            total_volume = rec.get("total_volume")
            max_high = rec.get("max_high_dollars")
            if max_high is not None and max_high >= ask - 1e-9:
                n_touched += 1

            if is_filled(max_high, total_volume, ask, queue_ahead):
                n_fill += 1
                pnl = member_pnl(ask, settle_yes)
                per_event_pnl.setdefault(et, []).append(pnl)
                if settle_yes:
                    fills_settle_yes += 1
                else:
                    fills_settle_no += 1
                fill_rows.append({
                    "event_ticker": et, "ticker": tk, "yes_ask": ask,
                    "queue_ahead": queue_ahead, "total_volume": total_volume,
                    "max_high": max_high, "settle_yes": settle_yes, "pnl": pnl,
                    "price_source_tag": "real_ask+real_bid+broker_truth",
                })

    return {
        "n_wing": n_wing,
        "n_wing_event_hours": len({r for r in earliest if r in settle}),
        "n_joinable": n_joinable,
        "n_touched": n_touched,
        "n_settle_yes_all": n_settle_yes_all,
        "n_fill": n_fill,
        "fills_settle_yes": fills_settle_yes,
        "fills_settle_no": fills_settle_no,
        "per_event_pnl": per_event_pnl,
        "fill_rows": fill_rows,
    }


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def _fmt_ci(ci: List[Optional[float]]) -> str:
    if not ci or ci[0] is None:
        return "[None, None]"
    return f"[{ci[0]:+.4f}, {ci[1]:+.4f}]"


def _pct(num: int, den: int) -> str:
    return f"{(100.0 * num / den):.2f}%" if den else "n/a"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="S19/Q23 elevated-wing stale-ask maker fade fill-sim (read-only, offline)")
    ap.add_argument("--crypto-dir", default=str(CRYPTO_DIR))
    ap.add_argument("--depth-dir", default=str(DEPTH_DIR))
    ap.add_argument("--candle-cache-dir", default=str(CANDLE_CACHE_DIR))
    ap.add_argument("--band-steps", type=int, default=BAND_STEPS)
    ap.add_argument("--n-boot", type=int, default=10000)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    records = load_crypto_records(Path(args.crypto_dir))
    depth_idx = build_depth_index(Path(args.depth_dir))
    candle_cache = load_candle_cache(Path(args.candle_cache_dir))

    sim = simulate(records, depth_idx, candle_cache, band_steps=args.band_steps)

    n_wing = sim["n_wing"]
    n_join = sim["n_joinable"]
    n_fill = sim["n_fill"]
    n_touched = sim["n_touched"]

    # bootstrap E[P&L per event-hour] by event-hour (L6), over the FILLED population only
    boot = block_bootstrap(sim["per_event_pnl"], n_boot=args.n_boot)
    ci = boot["ci95"]
    lo = ci[0]
    n_units = boot["n_units"]
    clears_mag = clears_tick_magnitude(ci, tick=PRICE_TICK, min_ticks=1.0)

    fill_rate_overall = n_fill / n_wing if n_wing else 0.0

    # verdict (three explicit outcomes; kill conditions per the task)
    if n_fill == 0:
        verdict = "DEAD_ZERO_FILL"
    elif fill_rate_overall < NEAR_ZERO_FILL_RATE or n_units < MIN_CI_UNITS:
        verdict = "DEAD_NEAR_ZERO_FILL_DATA_ADEQUACY"
    elif lo is not None and lo > 0.0 and clears_mag:
        verdict = "ALIVE_UNEXPECTED"
    else:
        verdict = "DEAD_CI_OR_MAGNITUDE"

    print("=" * 80)
    print("S19 / Q23 — ELEVATED-WING STALE-ASK MAKER FADE FILL-SIM (read-only, OFFLINE)")
    print("=" * 80)
    print(f"crypto records: {len(records)}  depth tickers: {len(depth_idx)}  "
          f"candle-cache tickers: {len(candle_cache)}")
    print(f"maker short-YES rested at each wing's yes_ask (= a NO bid at the mirror price), "
          f"held to settlement; entry=earliest capture per event-hour")
    print("-" * 80)
    print("WING POPULATION (Q20 wing_elevated: outside +/-3 spacings, yes_ask in "
          f"[{WING_ASK_LO},{WING_ASK_HI}], yes_bid==0; asks real_ask):")
    print(f"  wing_elevated members = {n_wing}")
    print(f"  join coverage (queue+volume both measurable offline) = {n_join}/{n_wing} "
          f"({_pct(n_join, n_wing)})  [depth starts 07-07 vs crypto 07-03, L9]")
    print("-" * 80)
    print("OBSERVABILITY PRECHECK (was the wing ask ever even touched? max_high >= ask):")
    print(f"  touched = {n_touched}/{n_join} joinable ({_pct(n_touched, n_join)}) "
          f"-> the wings are stale precisely because almost nobody lifts them")
    print("-" * 80)
    print("QUEUE-AWARE FILL SIM (fill iff touched AND executed_vol >= queue_ahead; NOT an "
          "L39 candle print):")
    print(f"  fills = {n_fill}   fill rate overall = {_pct(n_fill, n_wing)}   "
          f"fill rate among joinable = {_pct(n_fill, n_join)}")
    print("-" * 80)
    print("ADVERSE SELECTION (gate #2 — the fill<->settlement correlation):")
    print(f"  settle-YES rate among ALL wings  = {sim['n_settle_yes_all']}/{n_wing} "
          f"({_pct(sim['n_settle_yes_all'], n_wing)})")
    print(f"  settle-YES rate among FILLS      = {sim['fills_settle_yes']}/{n_fill} "
          f"({_pct(sim['fills_settle_yes'], n_fill)})")
    fills_yes = [r["pnl"] for r in sim["fill_rows"] if r["settle_yes"]]
    fills_no = [r["pnl"] for r in sim["fill_rows"] if not r["settle_yes"]]
    mean_yes = (sum(fills_yes) / len(fills_yes)) if fills_yes else float("nan")
    mean_no = (sum(fills_no) / len(fills_no)) if fills_no else float("nan")
    print(f"  P&L | filled & settle-YES (TOXIC leg) : mean={mean_yes:+.4f}  n={len(fills_yes)}")
    print(f"  P&L | filled & settle-NO  (win leg)   : mean={mean_no:+.4f}  n={len(fills_no)}")
    if sim["fills_settle_yes"] == 0 and n_fill > 0:
        print("  NOTE: zero settle-YES fills in this tape -> the toxic loss leg the mechanism "
              "predicts is UNOBSERVED (sparsity), not disproven.")
    print("-" * 80)
    print("GATE (block-bootstrap E[P&L] BY EVENT-HOUR, net of flat 1c maker fee, L6/L27):")
    mean_str = "None" if boot["mean"] is None else f"{boot['mean']:+.4f}"
    print(f"  mean={mean_str}  "
          f"95% CI={_fmt_ci(ci)}  n_units(event-hours)={n_units}  n_obs(fills)={boot['n_obs']}  "
          f"n_boot={args.n_boot}")
    print(f"  L27 magnitude gate (lower bound >= 1 tick $0.01): "
          f"{'CLEARS' if clears_mag else 'does NOT clear'}")
    print(f"  (data-adequacy floor for a testable CI: MIN_CI_UNITS={MIN_CI_UNITS} event-hours)")
    print("-" * 80)
    print(f"VERDICT: {verdict}")
    if verdict == "DEAD_ZERO_FILL":
        print("  -> 0%-fill null: no qualifying wing ever fills. S10-maker / L26 TESTED-DEAD.")
    elif verdict == "DEAD_NEAR_ZERO_FILL_DATA_ADEQUACY":
        print(f"  -> near-0%-fill null ({_pct(n_fill, n_wing)} overall) across only {n_units} "
              f"filled event-hour(s) < {MIN_CI_UNITS}: the bootstrap is data-adequacy, NOT a "
              f"testable CI. The wings are stale precisely because almost nobody lifts them "
              f"(S14's incidental wing fill rate was 2.5%). Any positive-looking CI here rests "
              f"on a settle-YES-given-filled sample the mechanism says would be toxic but which "
              f"is UNOBSERVED. S10-maker / L26 TESTED-DEAD.")
    elif verdict == "DEAD_CI_OR_MAGNITUDE":
        print("  -> CI <= 0 or fails the L27 magnitude gate. Falsified.")
    else:
        print("  -> UNEXPECTED: CI > 0 and clears the magnitude gate over a testable population. "
              "Escalate — do not trade; verify before any status change.")
    print("=" * 80)

    result = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "band_steps": args.band_steps,
        "wing_ask_band": [WING_ASK_LO, WING_ASK_HI],
        "price_source_tags": {"asks": "real_ask", "queue_depth": "real_bid(mirror no_bids)",
                              "settlement": "broker_truth", "spot_binning": "synthetic",
                              "executed_volume": "real_ask(s14 candle cache)"},
        "n_wing": n_wing, "n_joinable": n_join, "join_coverage": (n_join / n_wing) if n_wing else None,
        "n_touched": n_touched, "n_fill": n_fill,
        "fill_rate_overall": fill_rate_overall,
        "fill_rate_joinable": (n_fill / n_join) if n_join else None,
        "settle_yes_all": sim["n_settle_yes_all"],
        "fills_settle_yes": sim["fills_settle_yes"],
        "fills_settle_no": sim["fills_settle_no"],
        "bootstrap": {"mean": boot["mean"], "ci95": ci, "n_units": n_units,
                      "n_obs": boot["n_obs"], "clears_tick_magnitude": clears_mag,
                      "n_boot": args.n_boot},
        "verdict": verdict,
        "fill_rows": sim["fill_rows"],
    }
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, indent=2, default=str))
        print(f"[s19] wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
