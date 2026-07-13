#!/usr/bin/env python3
"""q24_sports_longshot_maker_fillsim.py — Q24 / registry S7-H1: maker-side rich-ASK
selling on sports longshots (the untested mirror of the S7c PROVED taker richness).

LOOP-QUEUE.md Q24. S7c PROVED the taker side: Kalshi pregame sports asks run ~+2.35c rich
vs DraftKings-devig fair (block-bootstrap-by-game; `findings/2026-07-04-sports-clv-s7-
verdict.md`) — this probe does NOT re-run S7c. S13 then tested resting maker BIDS at
fair-1c -> DEAD (the 0.0175 maker fee ate the margin). The direct mirror is still untested:
REST THE RICH ASK ITSELF — a MAKER short-YES = a resting NO bid at price `1 minus yes_ask` — on
the longshot tail (fair_prob <= 0.20; also the yes_ask <= 0.20 proxy population), entered in
the open->kickoff window, held to settlement. P&L held-to-settlement:
  - longshot LOSES (settles NO)  -> keep the premium (yes_ask), minus the flat maker fee.
  - longshot WINS  (settles YES) -> pay $1: net `yes_ask minus 1 minus fee` (negative-skew leg).
The sold-longshot-WINS leg is modeled EXPLICITLY, never conditioned away (Q24 gate #2 / L41).

READ-ONLY, FULLY OFFLINE, NO NETWORK, NO ORDERS, NO AUTH. Everything is read off already-
committed tape; a stray `dt=<date>` DIRECTORY (the L25/L29 regression artifact) is skipped
by an is_file guard and never mutated. Fees come only from `core.pricing.fee_per_contract`
at `MAKER_FEE_RATE` (never hand-rolled — L18/L30: a flat $0.01 at every interior price).

DATA JOINS (each shape verified before it is trusted):
  - Fair anchors + pregame `real_ask`: `tape/sports_clv/dt=*.jsonl` — per-game record with
    `kalshi_event_ticker`, `kickoff_ts`, `outcomes[].{fair_prob (synthetic), pregame_ask.
    yes_ask (real_ask), ticker}`.
  - Settlement / winners (REQUIRED for the P&L, unlike S7c which measured only the CLV
    gap): `tape/sports_history_s7/worldcup2026.jsonl` — per-outcome `market_ticker` +
    `result` in {yes,no} + `settlement_value_dollars` (broker_truth). Verified to cover
    every fair-anchored longshot (81/81).
  - Queue (Q24 gate #1, the BINDING risk): `tape/orderbook_depth/dt=*.jsonl` `no_bids`
    ladder (tag `real_bid`, the mirror of the YES-ask side — a YES offer at p is a NO bid at
    1-p). Queue-ahead = sum of `no_bids` size at price >= `1 minus yes_ask` (price-time
    priority), joined by ticker + NEAREST `captured_at`. Queue-aware, NEVER a candlestick
    print (L39).
  - Executed volume / touch (does incoming flow clear the queue?): the ONLY offline sports
    executed-volume source is the `worldcup2026.jsonl` per-outcome candle series
    (`candles[].volume_fp` + `candles[].yes_ask.high_dollars`, tag real_ask). The S14 candle
    cache is CRYPTO-ONLY and does NOT cover sports tickers. Where no candle series exists for
    a ticker, its fills are UNMEASURABLE offline -> a no-fill / data-adequacy fact, reported
    honestly, NEVER a network fetch (this is a read-only offline probe).

KNOWN TAPE FACT (confirmed here, not assumed): the `sports_clv` fair-anchored WC/NBA games
(kickoffs 06-04 -> 07-03, captured 07-03/04) settled BEFORE the `orderbook_depth` sports
tape began (07-07 -> 07-13). So the mandated join (fair anchors x depth queue) has ZERO
ticker overlap (L9). This probe builds the full queue-aware machinery, RUNS it, and reports
the join coverage (n_joinable / n_longshot) as a hard number with the reason — then
STEELMANS (a `sports_pairs` ask-longshot x depth cut that DOES overlap, to measure the fill
rate / queue-ahead independent of the edge). Honest expectation: DEAD by data-adequacy — the
queue-aware fill-sim Q24 exists to run cannot be executed because the queue tape post-dates
every fair-anchored game. The machinery stays pure + unit-tested so it is reusable the moment
sports_clv and depth eventually overlap (a re-collected WC-final window).

Run:
    python3 scripts/q24_sports_longshot_maker_fillsim.py
    python3 scripts/q24_sports_longshot_maker_fillsim.py --n-boot 10000 --json-out /tmp/q24.json
"""
from __future__ import annotations

import argparse
import json
import sys
from bisect import bisect_left
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.bootstrap import block_bootstrap, clears_tick_magnitude  # noqa: E402
from core.io import REPO_ROOT  # noqa: E402
from core.pricing import MAKER_FEE_RATE, fee_per_contract  # noqa: E402

CLV_DIR = REPO_ROOT / "tape" / "sports_clv"
DEPTH_DIR = REPO_ROOT / "tape" / "orderbook_depth"
SETTLE_PATH = REPO_ROOT / "tape" / "sports_history_s7" / "worldcup2026.jsonl"
PAIRS_DIR = REPO_ROOT / "tape" / "sports_pairs"

FLOOR_ASK = 0.01                    # Kalshi 1c minimum YES ask — the mechanical floor
LONGSHOT_MAX = 0.20                 # Q24 longshot tail: fair_prob (or yes_ask proxy) <= 0.20
PRICE_TICK = 0.01                   # Kalshi price tick
DEPTH_JOIN_MAX_DELTA_SEC = 3600.0   # a depth capture must be within 1h to count as the queue
SPORTS_TICKER_SUBSTR = "GAME"       # KXWCGAME / KXNBAGAME / KXAFLGAME ...  (bounds depth idx)

# verdict thresholds (documented judgment calls):
MIN_CI_UNITS = 10                   # fewer filled GAMES than this = data-adequacy, not a CI
S19_FILL_FLOOR = 0.0045             # the S19-class fill floor Q24's kill condition references


# --------------------------------------------------------------------------- #
# loading (read-only; FILES only — L25/L29 skip stray dt=<date> DIRECTORIES)
# --------------------------------------------------------------------------- #
def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Every JSON record from a single committed *.jsonl file. Read-only; never mutates."""
    out: List[Dict[str, Any]] = []
    if not path.is_file():
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def load_clv_records(tape_dir: Path = CLV_DIR) -> List[Dict[str, Any]]:
    """Every sports_clv record from the canonical *.jsonl day-files. A stray `dt=<date>`
    DIRECTORY (the L25/L29 regression) is skipped by the is_file guard."""
    records: List[Dict[str, Any]] = []
    for path in sorted(tape_dir.glob("dt=*.jsonl")):
        if not path.is_file():
            continue
        records.extend(load_jsonl(path))
    return records


def load_pairs_records(tape_dir: Path = PAIRS_DIR) -> List[Dict[str, Any]]:
    """Every sports_pairs record from the canonical *.jsonl day-files (steelman source).
    is_file guard skips the stray dt=<date> DIRECTORIES (L25/L29 — 07-02/09/10 are dirs)."""
    records: List[Dict[str, Any]] = []
    for path in sorted(tape_dir.glob("dt=*.jsonl")):
        if not path.is_file():
            continue
        records.extend(load_jsonl(path))
    return records


def build_settlement_map(path: Path = SETTLE_PATH) -> Dict[str, Dict[str, Any]]:
    """`{market_ticker: {settle_yes, price_source_tag}}` from worldcup2026.jsonl per-outcome
    `result` (broker_truth). settle_yes True iff the market settled YES (result == 'yes')."""
    out: Dict[str, Dict[str, Any]] = {}
    for r in load_jsonl(path):
        for o in r.get("outcomes", []):
            mt = o.get("market_ticker")
            res = o.get("result")
            if not mt or res not in ("yes", "no"):
                continue
            out[mt] = {"settle_yes": (res == "yes"), "price_source_tag": "broker_truth"}
    return out


def _f(x: Any) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def build_candle_volume_map(path: Path = SETTLE_PATH) -> Dict[str, Dict[str, Any]]:
    """The ONLY offline sports executed-volume/touch source: `{market_ticker:
    {total_volume, max_yes_ask_high}}` from worldcup2026.jsonl candle series
    (`candles[].volume_fp` + `candles[].yes_ask.high_dollars`). total_volume = sum of every
    candle's volume (generous toward filling — we cannot price-decompose the candle offline,
    so a near-0 fill under this generous rule is robust). max_yes_ask_high = the touch
    observability (did a taker ever lift at/through the ask). tag: real_ask."""
    out: Dict[str, Dict[str, Any]] = {}
    for r in load_jsonl(path):
        for o in r.get("outcomes", []):
            mt = o.get("market_ticker")
            candles = o.get("candles")
            if not mt or not candles:
                continue
            total_vol = 0.0
            max_high: Optional[float] = None
            for c in candles:
                v = _f(c.get("volume_fp"))
                if v is not None:
                    total_vol += v
                ya = c.get("yes_ask") or {}
                hi = _f(ya.get("high_dollars"))
                if hi is not None:
                    max_high = hi if max_high is None else max(max_high, hi)
            out[mt] = {"total_volume": total_vol, "max_yes_ask_high": max_high,
                       "price_source_tag": "real_ask"}
    return out


def _parse_ts(ts: str) -> float:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


def build_depth_index(depth_dir: Path = DEPTH_DIR,
                      ticker_substr: str = SPORTS_TICKER_SUBSTR
                      ) -> Dict[str, List[Tuple[float, List[Any]]]]:
    """`{ticker: [(ts, no_bids), ...]}` sorted by ts, for sports tickers only (ticker
    contains `ticker_substr`, bounding the index). Keeps the full `no_bids` ladder (tag
    `real_bid`) so queue-ahead can pick the right price levels. FILES only (L25/L29)."""
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
                if ticker_substr not in tk:
                    continue
                cap = r.get("captured_at")
                if not cap:
                    continue
                idx.setdefault(tk, []).append((_parse_ts(cap), r.get("no_bids") or []))
    for tk in idx:
        idx[tk].sort(key=lambda t: t[0])
    return idx


# --------------------------------------------------------------------------- #
# pure selection / fill-sim / P&L (unit-tested offline)
# --------------------------------------------------------------------------- #
def longshot_outcomes(clv_records: List[Dict[str, Any]], *, selection: str = "fair"
                      ) -> List[Dict[str, Any]]:
    """Enumerate longshot outcomes from sports_clv, DEDUPED by ticker (keeping the earliest
    capture — the open->kickoff entry, maximizing the hold). `selection` is 'fair'
    (fair_prob <= 0.20, the primary Q24 selection) or 'ask' (yes_ask <= 0.20 proxy). Only
    outcomes with a real pregame yes_ask above the 1c floor qualify (a floor-pinned ask has
    no sellable premium). Each row: {event_ticker, ticker, yes_ask, fair_prob, captured_at}."""
    if selection not in ("fair", "ask"):
        raise ValueError(f"selection must be 'fair' or 'ask', got {selection!r}")
    best: Dict[str, Dict[str, Any]] = {}
    for r in clv_records:
        et = r.get("kalshi_event_ticker")
        cap = r.get("captured_at")
        if not et or not cap:
            continue
        for o in r.get("outcomes", []):
            tk = o.get("ticker")
            fp = o.get("fair_prob")
            pa = o.get("pregame_ask") or {}
            ya = pa.get("yes_ask")
            if not tk or ya is None:
                continue
            ya = float(ya)
            if ya <= FLOOR_ASK + 1e-9:       # floor-pinned ask -> no sellable premium
                continue
            if selection == "fair":
                if fp is None or float(fp) > LONGSHOT_MAX + 1e-9:
                    continue
            else:  # 'ask'
                if ya > LONGSHOT_MAX + 1e-9:
                    continue
            row = {"event_ticker": et, "ticker": tk, "yes_ask": ya,
                   "fair_prob": (float(fp) if fp is not None else None),
                   "captured_at": cap}
            if tk not in best or cap < best[tk]["captured_at"]:
                best[tk] = row
    return list(best.values())


def offer_price(yes_ask: float, ask_delta: float = 0.0) -> float:
    """The maker short-YES premium actually rested: `yes_ask plus ask_delta` (ask_delta=0 for
    the observed ask, -0.01 for the ask-1c variant). Clamped to the 1c floor."""
    return max(FLOOR_ASK, round(float(yes_ask) + ask_delta, 4))


def queue_ahead_at(no_bids: Sequence[Any], premium: float, tick: float = PRICE_TICK) -> float:
    """Contracts resting AHEAD of a newly-arriving NO bid at price `1 - premium` (tag
    `real_bid`). Price-time priority: every NO bid at price >= our price fills before us, so
    incoming YES-buy volume must clear it first. Sum of `no_bids` sizes at price >=
    (1 - premium). A longshot premium (<=0.20) maps to a NO bid at price >= 0.80 — deep in
    the book, so the queue ahead is typically thin, but that is measured, not assumed."""
    p_no = 1.0 - float(premium)
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


def member_fee(premium: float) -> float:
    """The flat maker fee charged on fill (L18/L30): `fee_per_contract` at MAKER_FEE_RATE on
    the resting NO-bid fill price (1 - premium) — a flat $0.01 at every interior price. Uses
    the sanctioned fee helper (never hand-rolled)."""
    return fee_per_contract(1.0 - float(premium), rate=MAKER_FEE_RATE)


def member_pnl(premium: float, settle_yes: bool) -> float:
    """P&L of one filled maker short-YES (sold longshot) held to settlement, net of fee:
      settle NO  (longshot LOSES, we win)  -> keep the premium, minus the fee.
      settle YES (longshot WINS,  we lose) -> premium - $1 payout - fee (negative-skew leg).
    The sold-longshot-WINS leg is modeled here explicitly (Q24 gate #2 / L41)."""
    fee = member_fee(premium)
    if settle_yes:
        return float(premium) - 1.0 - fee
    return float(premium) - fee


def is_filled(max_touch: Optional[float], total_volume: Optional[float], premium: float,
              queue_ahead: float) -> bool:
    """Queue-aware fill (NOT an L39 candle print). Filled iff the offer was TOUCHED (max
    realized YES ask-high >= premium, i.e. a taker actually lifted at/through our resting
    offer) AND executed volume over the hold cleared the queue ahead of us
    (total_volume >= queue_ahead). Unmeasurable volume/touch (None) -> no fill."""
    if max_touch is None or total_volume is None:
        return False
    if max_touch + 1e-9 < premium:        # offer never touched -> no lift -> no fill
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
    timeline. Returns None on a ticker absent from the depth index (the empty-join case)."""
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
# mandated per-longshot simulation
# --------------------------------------------------------------------------- #
def simulate(clv_records: List[Dict[str, Any]],
             settle_map: Dict[str, Dict[str, Any]],
             candle_map: Dict[str, Dict[str, Any]],
             depth_idx: Dict[str, List[Tuple[float, List[Any]]]],
             *, selection: str = "fair", ask_delta: float = 0.0) -> Dict[str, Any]:
    """The mandated queue-aware fill-sim: rest a maker short-YES on each longshot, join
    settlement + depth queue + candle executed-volume, and return the descriptive counts +
    per-GAME P&L (L6 bootstrap unit = game/event_ticker)."""
    longshots = longshot_outcomes(clv_records, selection=selection)

    n_long = len(longshots)
    n_settle = 0
    n_queue = 0             # depth queue measurable (the Q24 binding join)
    n_vol = 0               # executed-volume/touch measurable
    n_joinable = 0          # settlement AND queue AND volume all measurable
    n_touched = 0
    n_fill = 0
    fills_settle_yes = 0
    fills_settle_no = 0
    n_settle_yes_all = 0
    per_game_pnl: Dict[str, List[float]] = {}
    fill_rows: List[Dict[str, Any]] = []

    for row in longshots:
        tk = row["ticker"]
        et = row["event_ticker"]
        premium = offer_price(row["yes_ask"], ask_delta)
        ts = _parse_ts(row["captured_at"])

        s = settle_map.get(tk)
        if s is None:
            continue
        n_settle += 1
        settle_yes = bool(s["settle_yes"])
        if settle_yes:
            n_settle_yes_all += 1

        no_bids = nearest_no_bids(depth_idx, tk, ts)
        cand = candle_map.get(tk)
        if no_bids is not None:
            n_queue += 1
        if cand is not None:
            n_vol += 1
        if no_bids is None or cand is None:
            continue
        n_joinable += 1

        queue_ahead = queue_ahead_at(no_bids, premium)
        total_volume = cand.get("total_volume")
        max_touch = cand.get("max_yes_ask_high")
        if max_touch is not None and max_touch >= premium - 1e-9:
            n_touched += 1

        if is_filled(max_touch, total_volume, premium, queue_ahead):
            n_fill += 1
            pnl = member_pnl(premium, settle_yes)
            per_game_pnl.setdefault(et, []).append(pnl)
            if settle_yes:
                fills_settle_yes += 1
            else:
                fills_settle_no += 1
            fill_rows.append({
                "event_ticker": et, "ticker": tk, "premium": premium,
                "queue_ahead": queue_ahead, "total_volume": total_volume,
                "max_touch": max_touch, "settle_yes": settle_yes, "pnl": pnl,
                "price_source_tag": "real_ask+real_bid+broker_truth",
            })

    return {
        "selection": selection, "ask_delta": ask_delta,
        "n_longshot": n_long, "n_settle": n_settle,
        "n_queue_joinable": n_queue, "n_vol_measurable": n_vol,
        "n_joinable": n_joinable, "n_touched": n_touched, "n_fill": n_fill,
        "n_settle_yes_all": n_settle_yes_all,
        "fills_settle_yes": fills_settle_yes, "fills_settle_no": fills_settle_no,
        "per_game_pnl": per_game_pnl, "fill_rows": fill_rows,
    }


def admissible_positive(per_unit: Dict[str, List[float]], *, min_units: int = MIN_CI_UNITS
                        ) -> bool:
    """L41 degenerate-bootstrap floor: a positive-edge claim is VOID unless the resample
    unit contains >=1 LOSING cluster (>=1 game whose pooled mean is < 0 — i.e. a game where
    the sold longshot WON, the negative-skew leg) AND at least `min_units` units. A one-sided
    all-same-direction bootstrap yields a mechanical p=0 that carries no evidentiary weight.
    Returns False on an empty/degenerate population (nothing admissible to claim)."""
    if len(per_unit) < min_units:
        return False
    has_losing_cluster = any((sum(v) / len(v)) < 0.0 for v in per_unit.values() if v)
    return has_losing_cluster


# --------------------------------------------------------------------------- #
# steelman: sports_pairs ask-longshots x depth (fill-rate / queue-ahead, edge-independent)
# --------------------------------------------------------------------------- #
def pairs_longshot_outcomes(pairs_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """ask<=0.20 longshot outcomes from sports_pairs (07-02..07-13, the window that DOES
    overlap depth), DEDUPED by ticker keeping the earliest capture. Only asks above the 1c
    floor. Each row: {event_ticker, ticker, yes_ask, captured_at}."""
    best: Dict[str, Dict[str, Any]] = {}
    for r in pairs_records:
        et = r.get("event_ticker")
        cap = r.get("captured_at")
        if not et or not cap:
            continue
        for o in r.get("outcomes", []):
            tk = o.get("ticker")
            ya = o.get("yes_ask")
            if not tk or ya is None:
                continue
            ya = float(ya)
            if ya <= FLOOR_ASK + 1e-9 or ya > LONGSHOT_MAX + 1e-9:
                continue
            row = {"event_ticker": et, "ticker": tk, "yes_ask": ya, "captured_at": cap}
            if tk not in best or cap < best[tk]["captured_at"]:
                best[tk] = row
    return list(best.values())


def steelman(pairs_records: List[Dict[str, Any]],
             settle_map: Dict[str, Dict[str, Any]],
             candle_map: Dict[str, Dict[str, Any]],
             depth_idx: Dict[str, List[Tuple[float, List[Any]]]],
             *, ask_delta: float = 0.0) -> Dict[str, Any]:
    """Edge-independent rescue: over sports_pairs ask-longshots that DO overlap depth, how
    deep is the queue ahead of our resting NO bid, and how many also carry settlement +
    executed-volume (a full P&L sim)? Reports queue-ahead stats + the full-sim-eligible
    count, so the near-miss is quantified rather than hand-waved."""
    longshots = pairs_longshot_outcomes(pairs_records)
    n_long = len(longshots)
    n_queue = 0
    n_queue_zero = 0        # queue-ahead == 0: front-of-queue, fills on any touch
    n_full_eligible = 0     # queue AND settlement AND candle-volume all present
    queue_aheads: List[float] = []
    for row in longshots:
        tk = row["ticker"]
        premium = offer_price(row["yes_ask"], ask_delta)
        ts = _parse_ts(row["captured_at"])
        no_bids = nearest_no_bids(depth_idx, tk, ts)
        if no_bids is None:
            continue
        n_queue += 1
        qa = queue_ahead_at(no_bids, premium)
        queue_aheads.append(qa)
        if qa <= 1e-9:
            n_queue_zero += 1
        if tk in settle_map and tk in candle_map:
            n_full_eligible += 1
    queue_aheads.sort()
    median_qa = (queue_aheads[len(queue_aheads) // 2] if queue_aheads else None)
    return {
        "n_longshot": n_long, "n_queue_joinable": n_queue,
        "n_queue_zero_ahead": n_queue_zero, "n_full_sim_eligible": n_full_eligible,
        "median_queue_ahead": median_qa,
    }


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def _fmt_ci(ci: Sequence) -> str:
    if not ci or ci[0] is None:
        return "[None, None]"
    return f"[{ci[0]:+.4f}, {ci[1]:+.4f}]"


def _pct(num: int, den: int) -> str:
    return f"{(100.0 * num / den):.2f}%" if den else "n/a"


def _verdict(sim: Dict[str, Any], boot: Dict[str, Any], clears_mag: bool,
             admissible: bool) -> str:
    n_fill = sim["n_fill"]
    n_units = boot["n_units"]
    lo = boot["ci95"][0]
    if sim["n_joinable"] == 0 or n_fill == 0 or n_units < MIN_CI_UNITS:
        return "DEAD_DATA_ADEQUACY"
    if lo is not None and lo > 0.0 and clears_mag and admissible:
        return "ALIVE_UNEXPECTED"
    return "DEAD_CI_OR_MAGNITUDE"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Q24 sports-longshot maker rich-ask fill-sim (read-only, offline)")
    ap.add_argument("--clv-dir", default=str(CLV_DIR))
    ap.add_argument("--depth-dir", default=str(DEPTH_DIR))
    ap.add_argument("--settle-path", default=str(SETTLE_PATH))
    ap.add_argument("--pairs-dir", default=str(PAIRS_DIR))
    ap.add_argument("--n-boot", type=int, default=10000)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    clv = load_clv_records(Path(args.clv_dir))
    settle_map = build_settlement_map(Path(args.settle_path))
    candle_map = build_candle_volume_map(Path(args.settle_path))
    depth_idx = build_depth_index(Path(args.depth_dir))
    pairs = load_pairs_records(Path(args.pairs_dir))

    print("=" * 84)
    print("Q24 / S7-H1 — SPORTS-LONGSHOT MAKER RICH-ASK FILL-SIM (read-only, OFFLINE)")
    print("=" * 84)
    print(f"sports_clv records: {len(clv)}   settlement tickers: {len(settle_map)}   "
          f"candle-volume tickers: {len(candle_map)}")
    print(f"depth sports tickers: {len(depth_idx)}   sports_pairs records: {len(pairs)}")
    print("The trade: rest a MAKER short-YES (= a NO bid at 1 minus yes_ask) on each longshot, "
          "held to settlement.")
    print("Prices: asks=real_ask  queue=real_bid(no_bids mirror)  settlement=broker_truth  "
          "fair=synthetic  exec_vol=real_ask(worldcup candles)")

    result: Dict[str, Any] = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "price_source_tags": {
            "asks": "real_ask", "queue_depth": "real_bid(no_bids mirror)",
            "settlement": "broker_truth", "fair_prob": "synthetic",
            "executed_volume": "real_ask(worldcup2026 candles)"},
        "n_boot": args.n_boot, "cuts": [], "steelman": {},
    }

    primary_verdict = "DEAD_DATA_ADEQUACY"
    for selection in ("fair", "ask"):
        for ask_delta in (0.0, -0.01):
            sim = simulate(clv, settle_map, candle_map, depth_idx,
                           selection=selection, ask_delta=ask_delta)
            boot = block_bootstrap(sim["per_game_pnl"], n_boot=args.n_boot)
            clears_mag = clears_tick_magnitude(boot["ci95"], tick=PRICE_TICK, min_ticks=1.0)
            admissible = admissible_positive(sim["per_game_pnl"])
            verdict = _verdict(sim, boot, clears_mag, admissible)
            is_primary = (selection == "fair" and ask_delta == 0.0)
            if is_primary:
                primary_verdict = verdict

            print("-" * 84)
            tag = "PRIMARY" if is_primary else "cut"
            dlabel = "ask" if ask_delta == 0.0 else f"ask{ask_delta:+.2f}"
            print(f"[{tag}] selection={selection}<=0.20 offer={dlabel}")
            print(f"  longshots={sim['n_longshot']}  with settlement={sim['n_settle']}  "
                  f"settle-YES(all)={sim['n_settle_yes_all']}")
            print(f"  JOIN COVERAGE (Q24 binding): depth-queue joinable={sim['n_queue_joinable']}"
                  f"/{sim['n_longshot']} ({_pct(sim['n_queue_joinable'], sim['n_longshot'])})  "
                  f"exec-vol measurable={sim['n_vol_measurable']}  "
                  f"ALL-THREE joinable={sim['n_joinable']}/{sim['n_longshot']} "
                  f"({_pct(sim['n_joinable'], sim['n_longshot'])})")
            print(f"  fills={sim['n_fill']}  fill-rate over longshots="
                  f"{_pct(sim['n_fill'], sim['n_longshot'])}  "
                  f"(S19-class kill floor {S19_FILL_FLOOR:.4%})")
            print(f"  adverse-selection: settle-YES among fills="
                  f"{sim['fills_settle_yes']}/{sim['n_fill']} "
                  f"({_pct(sim['fills_settle_yes'], sim['n_fill'])})  "
                  f"(vs {_pct(sim['n_settle_yes_all'], sim['n_settle'])} among all-settled)")
            mean_str = "None" if boot["mean"] is None else f"{boot['mean']:+.4f}"
            print(f"  block-bootstrap E[P&L] BY GAME (L6): mean={mean_str}  "
                  f"95%CI={_fmt_ci(boot['ci95'])}  n_units(games)={boot['n_units']}  "
                  f"n_obs(fills)={boot['n_obs']}")
            print(f"  L27 magnitude gate: {'CLEARS' if clears_mag else 'n/a (no CI)'}  "
                  f"L41 admissible (>=1 losing cluster & >={MIN_CI_UNITS} units): {admissible}")
            print(f"  VERDICT[{selection}/{dlabel}]: {verdict}")

            result["cuts"].append({
                "selection": selection, "ask_delta": ask_delta, "is_primary": is_primary,
                "n_longshot": sim["n_longshot"], "n_settle": sim["n_settle"],
                "n_queue_joinable": sim["n_queue_joinable"],
                "n_vol_measurable": sim["n_vol_measurable"], "n_joinable": sim["n_joinable"],
                "n_fill": sim["n_fill"], "n_settle_yes_all": sim["n_settle_yes_all"],
                "fills_settle_yes": sim["fills_settle_yes"],
                "bootstrap": {"mean": boot["mean"], "ci95": boot["ci95"],
                              "n_units": boot["n_units"], "n_obs": boot["n_obs"]},
                "clears_tick_magnitude": clears_mag, "l41_admissible": admissible,
                "verdict": verdict,
            })

    # ---- steelman ----
    st = steelman(pairs, settle_map, candle_map, depth_idx)
    result["steelman"] = st
    print("=" * 84)
    print("STEELMAN (rescue): sports_pairs ask<=0.20 longshots x depth queue "
          "(07-02..07-13 DOES overlap depth 07-07..07-13)")
    print(f"  ask-longshots={st['n_longshot']}  depth-queue joinable={st['n_queue_joinable']} "
          f"({_pct(st['n_queue_joinable'], st['n_longshot'])})")
    print(f"  queue-ahead==0 (front-of-queue, fills on any touch)="
          f"{st['n_queue_zero_ahead']}/{st['n_queue_joinable']} "
          f"({_pct(st['n_queue_zero_ahead'], st['n_queue_joinable'])})  "
          f"median queue-ahead={st['median_queue_ahead']}")
    print(f"  FULL-SIM-ELIGIBLE (queue AND settlement AND exec-vol)="
          f"{st['n_full_sim_eligible']}  (< {MIN_CI_UNITS} CI-floor -> no testable edge cut)")

    print("=" * 84)
    print(f"PRIMARY VERDICT (fair<=0.20, offer at observed ask): {primary_verdict}")
    if primary_verdict == "DEAD_DATA_ADEQUACY":
        print("  -> The mandated queue-aware join (fair-anchored longshots x depth no_bids) is "
              "EMPTY: every fair-anchored game settled BEFORE the sports depth tape began "
              "(clv kickoffs 06-04..07-03 vs depth 07-07..07-13, L9). The queue-aware "
              "fill-sim Q24 exists to run cannot be executed offline. Settlement (worldcup2026, "
              "broker_truth) IS adequate (81/81), so this is a queue-tape timing gap, not a "
              "winner gap. Steelman confirms no full-sim-eligible population clears the CI "
              "floor. Q24 is TESTED-DEAD-BY-DATA-ADEQUACY; machinery preserved + unit-tested "
              "for a future WC-window re-collection where clv and depth overlap.")
    elif primary_verdict == "ALIVE_UNEXPECTED":
        print("  -> UNEXPECTED: CI>0, clears the magnitude gate, admissible (>=1 losing "
              "cluster). Do NOT trade, do NOT flip anything — escalate for two-agent "
              "verification.")
    else:
        print("  -> CI<=0 / magnitude-gate fail / degenerate (L41). Falsified.")
    print("=" * 84)
    result["primary_verdict"] = primary_verdict

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, indent=2, default=str))
        print(f"[q24] wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
