"""Q49 / S68 — two-sided BOTH-BID overround-capture MAKER fill-sim on wide-spread game books.

Falsifiable milestone (LOOP-QUEUE.md Q49; kb/strategies/00-index.md S68). S68's idea-stage
claim: on a 2-outcome game moneyline book whose two-sided spread is at least 2x the flat maker
fee, rest BOTH a YES bid and a NO bid; if BOTH fill you own both sides for `yes_bid + no_bid`
(< $1 for 100% of the idea-stage population) and exactly one side settles $1 -> a deterministic
overround capture of `1 - yes_bid - no_bid` gross, less one flat maker fee PER FILLED LEG.

THE IDEA-STAGE NUMBER IS A BOTH-SIDES-FILL NUMBER, AND THAT IS THE WHOLE QUESTION. If both legs
fill, the P&L is arithmetically deterministic and adverse selection CANNOT touch it (you hold
both sides; exactly one pays $1). Adverse selection therefore enters in exactly one place: the
attempts where only ONE leg fills. A single-leg fill is a naked directional position, not the
capture (Q49 binding gate 2). So the deployable unit of account is the PER-ATTEMPT P&L:

    both legs fill : 1 - yes_bid - no_bid - fee(yes_bid) - fee(no_bid)       (deterministic)
    YES leg only   : [1 if result == yes else 0] - yes_bid - fee(yes_bid)    (directional)
    NO  leg only   : [1 if result == no  else 0] - no_bid  - fee(no_bid)     (directional)
    neither fills  : 0

Conditioning the verdict on "both filled" and quoting +5.31c would reproduce the idea-stage
arithmetic and prove nothing (Q49 gate 3 / L5). Both cuts are reported; the PER-ATTEMPT cut is
the binding one, and the both-fill-conditioned cut is reported as the item's literal secondary.

Queue-aware fill model (L39 - never a candlestick print). Both resting bids live on the SAME
binary market's book: the YES bid on the `yes_bids` ladder, the NO bid on the `no_bids` ladder
(mirror identity on a binary book: yes_ask == 1 - best_no_bid, so yes-spread == the both-bid
overround by construction, not by luck). At ENTRY we rest at each side's touch; `queue_ahead`
is the resting size at price >= our price on that ladder (price-time priority). Fills are then
measured from the tape's OWN observed queue departures across later snapshots (the L48 turnover
proxy: size reductions at levels >= our price). Cancels ahead of us count as advancing us and
new bids jumping ahead are ignored - deliberately GENEROUS, so a below-floor fill rate under
this rule is a robust dead-thin OUT, never a fill guarantee (L48: a turnover proxy rules a cell
OUT, never IN).

TWO EXPLICIT FILL MODELS (Q49 gate 3 - adverse selection modeled, not assumed away):
  A `queue_only`         - departures alone clear the queue. Optimistic upper bound on fills.
  B `queue_price_through`- A, AND the touch on that side is later observed at a price strictly
                           below our resting price (the book actually repriced DOWN THROUGH our
                           level). This is the adverse-selection mechanism named in the S68 row:
                           a resting bid is lifted by flow moving against the side we bought.
Model B is the BINDING model for the verdict; Model A is reported so the gap between them is
visible rather than asserted. On top of both, the realized adverse selection is MEASURED, not
assumed: P(the side we own settles against us | that side filled alone) vs the population base
rate is printed for every cut.

GATES (do NOT weaken):
  G1 the fillable object is `real_bid` (a resting bid at the observed touch); settlement is
     `broker_truth` from `tape/settlement_ledger/` and GATES THE PAYOUT, never a fill (L50).
  G2 BOTH bids must fill before the overround is booked; single-leg fills stay in the
     per-attempt P&L as directional positions and are never dropped or conditioned away (L41).
  G3 adverse selection is modeled (model B) AND measured (conditional settle rates).
  G4 the maker fee is charged PER FILLED LEG via core.pricing.fee_per_contract at
     MAKER_FEE_RATE - flat $0.01 at every interior price, never hand-rolled (L18/L30).
  G5 block-bootstrap by GAME-SERIES (L6/L41 - strikes/games inside one series are correlated
     draws), routed through bootstrap_verdict_admissible AND clears_tick_magnitude. A CI
     failing EITHER gate is not-a-verdict.

KILL CONDITIONS (any => DEAD): both-fill rate at or below the S19 0.45% queue-aware floor ·
the realized both-fill population's net overround <= 0 · per-attempt block-boot CI <= 0 ·
fewer than 10 game series after the queue gate (then it is DEAD-by-adequacy, not a
falsification).

READ-ONLY over committed tape (a probe never mutates tape). NO NETWORK: both legs
(`tape/settlement_ledger/`, `tape/orderbook_depth/`) are committed, so a verifier re-runs this
offline with no credentials and no cache refresh. Sizes are FLOATS and may be fractional (L47).
An empty ladder is VALID data (L23).

Run:
    python scripts/q49_two_sided_maker_fillsim.py
    python scripts/q49_two_sided_maker_fillsim.py --entry-policy late --json-out /tmp/q49.json
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.bootstrap import (block_bootstrap, bootstrap_verdict_admissible,  # noqa: E402
                            clears_tick_magnitude)
from core.io import REPO_ROOT  # noqa: E402
from core.pricing import MAKER_FEE_RATE, fee_per_contract  # noqa: E402
from core.settlement import is_binary_result, normalize_result  # noqa: E402
from core.timeutil import parse_iso_utc  # noqa: E402

DEPTH_GLOB = str(REPO_ROOT / "tape" / "orderbook_depth" / "dt=*.jsonl")
SETTLE_GLOB = str(REPO_ROOT / "tape" / "settlement_ledger" / "dt=*.jsonl")

PRICE_TICK = 0.01           # Kalshi price tick (L27 magnitude gate)
MIN_SPREAD = 0.02           # S68's own gate: two-sided spread >= 2x the flat maker fee
S19_FILL_FLOOR = 0.0045     # the S19-class queue-aware fill-rate kill floor
MIN_CI_UNITS = 10           # fewer bootstrap units than this = data-adequacy, not a CI
MIN_PRE_SNAPSHOTS = 2       # a fill-sim needs at least one post-entry observation
_EPS = 1e-9

FILL_MODELS = ("queue_only", "queue_price_through")
ENTRY_POLICIES = ("first", "late")

# The two ladder sides of ONE binary market's book, with their touch fields.
SIDE_LADDER = {"yes": "yes_bids", "no": "no_bids"}
SIDE_TOUCH = {"yes": "best_yes_bid", "no": "best_no_bid"}


# --------------------------------------------------------------------------- #
# Pure ticker / time helpers (offline-testable; no clock, no network)
# --------------------------------------------------------------------------- #
def series_of(market_ticker: str) -> str:
    """Series prefix and the BOOTSTRAP UNIT (L6/L41), e.g.
    'KXNPBGAME-26JUL12ABC-XYZ' -> 'KXNPBGAME'."""
    return market_ticker.split("-", 1)[0]


def event_ticker_of(market_ticker: str) -> str:
    """The GAME key (secondary bootstrap unit): strip the trailing outcome-code segment.
    A ticker with no trailing '-<code>' returns itself unchanged."""
    return market_ticker.rsplit("-", 1)[0]


def parse_iso(ts: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp to a tz-aware UTC datetime via the SANCTIONED
    `core.timeutil.parse_iso_utc` (L136/L150 — never a raw `datetime.fromisoformat`, which on
    the declared Python 3.9 floor rejects the bare-`Z` / short-fractional-second timestamps
    that are 38% of committed tape). None on a missing/blank/unparseable input, never raises."""
    if not ts:
        return None
    try:
        dt = parse_iso_utc(str(ts))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def is_game_series(series: str) -> bool:
    """S68's population is GENUINE 2-outcome game moneylines, i.e. series ending in 'GAME'
    (KXNPBGAME, KXUECLGAME, ...). Excludes by construction the KXMVE* multi-game /
    cross-category nominal-wing artifacts L31 warns about, and every non-game family."""
    return series.endswith("GAME") and not series.startswith("KXMVE")


# --------------------------------------------------------------------------- #
# Pure ladder helpers (sizes are FLOATS, L47; an empty ladder is VALID, L23)
# --------------------------------------------------------------------------- #
def bid_price_map(ladder: Optional[Sequence[Sequence[float]]], price: float,
                  tick: float = PRICE_TICK) -> Dict[float, float]:
    """price -> size map of the ladder levels at price >= `price` (the levels ahead of or at
    our resting bid under price priority). Floats throughout (L47); malformed levels are
    skipped; an empty/None ladder yields an empty map (L23)."""
    out: Dict[float, float] = {}
    if not ladder:
        return out
    for level in ladder:
        if level is None or len(level) < 2 or level[0] is None or level[1] is None:
            continue
        p = float(level[0])
        if p >= price - tick / 2.0:
            out[p] = out.get(p, 0.0) + float(level[1])
    return out


def queue_ahead_at(ladder: Optional[Sequence[Sequence[float]]], price: float,
                   tick: float = PRICE_TICK) -> float:
    """Contracts resting AHEAD of a newly-placed bid at `price`: the total size at price
    >= `price` (everyone at or above our price fills before us). Floats, never int-coerced."""
    return sum(bid_price_map(ladder, price, tick).values())


def departures_between(prev_ladder: Optional[Sequence[Sequence[float]]],
                       now_ladder: Optional[Sequence[Sequence[float]]], price: float,
                       tick: float = PRICE_TICK) -> float:
    """Observed queue DEPARTURES at levels >= our price between two consecutive snapshots
    (the L48 turnover measure): per price level present in `prev`, the size reduction
    max(0, size_prev - size_now) (fills plus cancels ahead of us). Levels that GROW or that
    newly appear are ignored, which makes the model GENEROUS - a new bid jumping ahead of us
    is never charged. A below-floor fill rate under this rule is a robust OUT (L48)."""
    pm = bid_price_map(prev_ladder, price, tick)
    nm = bid_price_map(now_ladder, price, tick)
    dep = 0.0
    for p, size_prev in pm.items():
        size_now = nm.get(p, 0.0)
        if size_prev > size_now:
            dep += size_prev - size_now
    return dep


def traded_through(touch_prices: Sequence[Optional[float]], price: float,
                   tick: float = PRICE_TICK) -> bool:
    """ADVERSE-SELECTION confirmation for fill model B: did the touch on this side later
    print strictly BELOW our resting price - i.e. did the book reprice DOWN THROUGH the level
    we were resting at? That is the mechanism the S68 row names: a resting bid is lifted by
    flow moving against the side we bought. A missing/None touch is not evidence either way
    and is skipped (L23: an empty side is valid data, not a fill signal)."""
    for t in touch_prices:
        if t is None:
            continue
        if float(t) <= price - tick + _EPS and float(t) < price - _EPS:
            return True
    return False


# --------------------------------------------------------------------------- #
# Fee + P&L (fees ONLY from core.pricing, L18/L30 - flat $0.01 at interior prices)
# --------------------------------------------------------------------------- #
def maker_fee(fill_price: float) -> float:
    """The flat maker fee on ONE filled leg: fee_per_contract at MAKER_FEE_RATE. Sanctioned
    helper only - never a hand-rolled coefficient (L18)."""
    return fee_per_contract(float(fill_price), rate=MAKER_FEE_RATE)


def both_fill_pnl(yes_bid: float, no_bid: float) -> float:
    """P&L when BOTH legs fill: you own one YES and one NO on the same binary market, so
    exactly one settles $1 REGARDLESS of the outcome. Deterministic, outcome-free:
        1 - yes_bid - no_bid - fee(yes_bid) - fee(no_bid)
    One maker fee per FILLED LEG (G4) - two legs, two fees."""
    return (1.0 - float(yes_bid) - float(no_bid)
            - maker_fee(yes_bid) - maker_fee(no_bid))


def single_fill_pnl(side: str, fill_price: float, result: str) -> float:
    """P&L when only ONE leg fills - a naked DIRECTIONAL position (Q49 gate 2), held to
    settlement: payout $1 iff the settled result matches the side we bought, less the fill
    price and one maker fee. This leg is where adverse selection is charged; it is never
    dropped or conditioned away (L41/G2)."""
    payoff = 1.0 if normalize_result(result) == side else 0.0
    return payoff - float(fill_price) - maker_fee(fill_price)


def attempt_pnl(yes_filled: bool, no_filled: bool, yes_bid: float, no_bid: float,
                result: str) -> float:
    """The DEPLOYABLE per-attempt P&L of resting BOTH bids on one wide book and holding to
    settlement. Four exhaustive cases; the no-fill case earns exactly 0 (and costs nothing,
    since an unfilled resting order pays no fee)."""
    if yes_filled and no_filled:
        return both_fill_pnl(yes_bid, no_bid)
    if yes_filled:
        return single_fill_pnl("yes", yes_bid, result)
    if no_filled:
        return single_fill_pnl("no", no_bid, result)
    return 0.0


# --------------------------------------------------------------------------- #
# Queue-aware per-side fill simulation
# --------------------------------------------------------------------------- #
def simulate_side_fill(snapshots: Sequence[dict], side: str, bid_price: float,
                       fill_model: str = "queue_price_through") -> dict:
    """Queue-aware fill decision for ONE resting bid (L39, never a candle print) over a
    market's ordered pre-close snapshots, `snapshots[0]` being ENTRY.

    We rest at `bid_price` on `SIDE_LADDER[side]`; `queue_ahead` is the size at price >= ours
    in the ENTRY snapshot. Cumulative observed departures are accumulated across consecutive
    snapshot pairs; the queue leg is CLEARED once cumulative departures reach `queue_ahead`
    AND at least one departure was observed (a frozen queue that never moves is a NO-FILL,
    L32/L48). Under `queue_price_through` a cleared queue is not enough: the touch must also
    have printed strictly below our price at some snapshot AFTER entry (`traded_through`) -
    the explicit adverse-selection requirement (G3).

    Returns a dict so the caller can report WHY a leg did or did not fill.
    """
    if fill_model not in FILL_MODELS:
        raise ValueError(f"unknown fill_model {fill_model!r}; expected one of {FILL_MODELS}")
    ladder_key = SIDE_LADDER[side]
    touch_key = SIDE_TOUCH[side]
    entry = snapshots[0] if snapshots else {}
    q_ahead = queue_ahead_at(entry.get(ladder_key), bid_price)

    cumulative = 0.0
    cleared_at: Optional[int] = None
    for i in range(1, len(snapshots)):
        cumulative += departures_between(snapshots[i - 1].get(ladder_key),
                                         snapshots[i].get(ladder_key), bid_price)
        if cleared_at is None and cumulative > 0.0 and cumulative >= q_ahead - _EPS:
            cleared_at = i
    queue_cleared = cleared_at is not None
    through = traded_through([s.get(touch_key) for s in snapshots[1:]], bid_price)
    filled = queue_cleared and (through if fill_model == "queue_price_through" else True)
    return {
        "side": side, "bid_price": float(bid_price), "queue_ahead": q_ahead,
        "departures": cumulative, "queue_cleared": queue_cleared,
        "cleared_at_index": cleared_at, "traded_through": through,
        "filled": filled, "fill_model": fill_model,
        "price_source_tag": "real_bid",
    }


# --------------------------------------------------------------------------- #
# Tape loading (read-only, offline)
# --------------------------------------------------------------------------- #
def load_settlements(settle_glob: str = SETTLE_GLOB) -> Dict[str, dict]:
    """market_ticker -> settlement record from the committed `tape/settlement_ledger/`
    (`broker_truth`). Only binary yes/no results are kept - L52: a `scalar` result is not a
    two-outcome settlement and must not be coerced into one."""
    out: Dict[str, dict] = {}
    for fp in sorted(glob.glob(settle_glob)):
        with open(fp, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                # L52: Kalshi settlement is NOT always binary (a `scalar` result exists);
                # the sanctioned guard decides, never a hand-rolled string comparison.
                if not is_binary_result(r.get("result")):
                    continue
                t = r.get("ticker")
                if t:
                    out[t] = r
    return out


def load_depth_by_ticker(wanted: set, depth_glob: str = DEPTH_GLOB) -> Dict[str, List[dict]]:
    """ticker -> time-ordered depth snapshots, restricted to `wanted` tickers. Read-only."""
    by_ticker: Dict[str, List[dict]] = defaultdict(list)
    for fp in sorted(glob.glob(depth_glob)):
        with open(fp, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                t = r.get("ticker")
                if t in wanted:
                    by_ticker[t].append(r)
    for t in by_ticker:
        by_ticker[t].sort(key=lambda r: str(r.get("captured_at") or ""))
    return dict(by_ticker)


# --------------------------------------------------------------------------- #
# Population construction
# --------------------------------------------------------------------------- #
def two_sided_wide(snapshot: dict, min_spread: float = MIN_SPREAD) -> bool:
    """Is this snapshot a GENUINELY two-sided book (both bids present) whose yes-spread
    clears S68's >= 2x-maker-fee gate? On a binary book yes_ask == 1 - best_no_bid, so the
    yes-spread IS the both-bid overround - the gate and the payoff are the same quantity."""
    yb = snapshot.get("best_yes_bid")
    nb = snapshot.get("best_no_bid")
    ya = snapshot.get("best_yes_ask")
    if yb is None or nb is None or ya is None:
        return False
    if float(yb) <= 0 or float(nb) <= 0:
        return False
    return float(ya) - float(yb) >= min_spread - _EPS


def select_entry(pre_close: Sequence[dict], entry_policy: str = "first",
                 min_spread: float = MIN_SPREAD) -> Optional[int]:
    """Index of the ENTRY snapshot among a market's ordered pre-close snapshots, or None.

    `first` - the EARLIEST two-sided wide snapshot that still has a later pre-close snapshot.
              Maximises the observation window, so it is the GENEROUS entry for fills.
    `late`  - the LATEST such snapshot (spreads here match the idea-stage 7.31c headline but
              leave the shortest fill window). Reported as a sensitivity, never as the
              headline: an entry with no post-entry observation cannot be simulated at all.
    """
    if entry_policy not in ENTRY_POLICIES:
        raise ValueError(f"unknown entry_policy {entry_policy!r}; expected {ENTRY_POLICIES}")
    idxs = [i for i in range(len(pre_close) - 1) if two_sided_wide(pre_close[i], min_spread)]
    if not idxs:
        return None
    return idxs[0] if entry_policy == "first" else idxs[-1]


def build_attempts(settlements: Dict[str, dict], depth: Dict[str, List[dict]], *,
                   entry_policy: str = "first", min_spread: float = MIN_SPREAD,
                   min_pre_snapshots: int = MIN_PRE_SNAPSHOTS) -> List[dict]:
    """One ATTEMPT per settled game-moneyline market that has an entry snapshot plus at least
    one later pre-close snapshot. Settlement gates the PAYOUT only (G1) - it never enters the
    fill decision, which is outcome-blind by construction."""
    attempts: List[dict] = []
    for ticker, snaps in depth.items():
        s = settlements.get(ticker)
        if s is None:
            continue
        series = series_of(ticker)
        if not is_game_series(series):
            continue
        close = parse_iso(s.get("close_time"))
        pre = [r for r in snaps
               if close is None or (parse_iso(r.get("captured_at")) or close) < close]
        if len(pre) < min_pre_snapshots:
            continue
        ei = select_entry(pre, entry_policy, min_spread)
        if ei is None:
            continue
        entry = pre[ei]
        attempts.append({
            "ticker": ticker,
            "series": series,
            "event_ticker": event_ticker_of(ticker),
            "result": normalize_result(s.get("result")),
            "yes_bid": float(entry["best_yes_bid"]),
            "no_bid": float(entry["best_no_bid"]),
            "yes_spread": float(entry["best_yes_ask"]) - float(entry["best_yes_bid"]),
            "entry_captured_at": entry.get("captured_at"),
            "n_post_entry_snapshots": len(pre) - ei - 1,
            "window": pre[ei:],
            "price_source_tag": "real_bid",
            "settlement_price_source_tag": "broker_truth",
        })
    attempts.sort(key=lambda a: a["ticker"])
    return attempts


# --------------------------------------------------------------------------- #
# Simulation + verdict
# --------------------------------------------------------------------------- #
def _mean(xs: Sequence[float]) -> Optional[float]:
    return sum(xs) / len(xs) if xs else None


def _boot_block(unit_values: Dict[str, List[float]], label: str) -> dict:
    boot = block_bootstrap(unit_values, n_boot=10000, seed=42)
    adm = bootstrap_verdict_admissible(unit_values, min_units=MIN_CI_UNITS)
    return {
        "label": label, "mean": boot["mean"], "ci95": boot["ci95"],
        "n_units": boot["n_units"], "n_obs": boot["n_obs"],
        "admissible": adm["admissible"], "n_opposing_units": adm["n_opposing_units"],
        "admissibility_reasons": adm["reasons"],
        "clears_tick_magnitude": clears_tick_magnitude(boot["ci95"], tick=PRICE_TICK),
        "seed": boot["seed"], "n_boot": boot["n_boot"],
    }


def run_model(attempts: Sequence[dict], fill_model: str) -> dict:
    """Simulate BOTH resting bids on every attempt under one fill model and assemble the
    per-attempt P&L, the both-fill-conditioned cut, the MEASURED adverse-selection statistics
    and both block-bootstraps (by GAME-SERIES primary, by GAME secondary)."""
    rows: List[dict] = []
    for a in attempts:
        w = a["window"]
        yl = simulate_side_fill(w, "yes", a["yes_bid"], fill_model)
        nl = simulate_side_fill(w, "no", a["no_bid"], fill_model)
        pnl = attempt_pnl(yl["filled"], nl["filled"], a["yes_bid"], a["no_bid"], a["result"])
        rows.append({
            "ticker": a["ticker"], "series": a["series"], "event_ticker": a["event_ticker"],
            "result": a["result"], "raw_yes_bid": a["yes_bid"], "raw_no_bid": a["no_bid"],
            "yes_spread": a["yes_spread"], "bid_sum": a["yes_bid"] + a["no_bid"],
            "overround_absorbed": 1.0 - a["yes_bid"] - a["no_bid"],
            "yes_filled": yl["filled"], "no_filled": nl["filled"],
            "both_filled": yl["filled"] and nl["filled"],
            "yes_queue_ahead": yl["queue_ahead"], "no_queue_ahead": nl["queue_ahead"],
            "yes_queue_cleared": yl["queue_cleared"], "no_queue_cleared": nl["queue_cleared"],
            "yes_traded_through": yl["traded_through"],
            "no_traded_through": nl["traded_through"],
            "n_post_entry_snapshots": a["n_post_entry_snapshots"],
            "pnl": pnl, "fill_model": fill_model,
            "price_source_tag": "real_bid",
            "settlement_price_source_tag": "broker_truth",
        })

    n = len(rows)
    both = [r for r in rows if r["both_filled"]]
    yes_only = [r for r in rows if r["yes_filled"] and not r["no_filled"]]
    no_only = [r for r in rows if r["no_filled"] and not r["yes_filled"]]
    none_f = [r for r in rows if not r["yes_filled"] and not r["no_filled"]]

    per_attempt_units: Dict[str, List[float]] = defaultdict(list)
    per_attempt_games: Dict[str, List[float]] = defaultdict(list)
    for r in rows:
        per_attempt_units[r["series"]].append(r["pnl"])
        per_attempt_games[r["event_ticker"]].append(r["pnl"])
    both_units: Dict[str, List[float]] = defaultdict(list)
    for r in both:
        both_units[r["series"]].append(r["pnl"])

    base_yes_rate = _mean([1.0 if r["result"] == "yes" else 0.0 for r in rows])
    return {
        "fill_model": fill_model,
        "n_attempts": n,
        "n_series": len({r["series"] for r in rows}),
        "n_games": len({r["event_ticker"] for r in rows}),
        "counts": {"both": len(both), "yes_only": len(yes_only),
                   "no_only": len(no_only), "none": len(none_f)},
        "both_fill_rate": (len(both) / n) if n else None,
        "any_fill_rate": ((n - len(none_f)) / n) if n else None,
        "yes_leg_fill_rate": _mean([1.0 if r["yes_filled"] else 0.0 for r in rows]),
        "no_leg_fill_rate": _mean([1.0 if r["no_filled"] else 0.0 for r in rows]),
        "mean_yes_spread": _mean([r["yes_spread"] for r in rows]),
        "mean_bid_sum": _mean([r["bid_sum"] for r in rows]),
        "frac_bid_sum_below_1": _mean([1.0 if r["bid_sum"] < 1.0 else 0.0 for r in rows]),
        "mean_gross_overround_both_fill": _mean([r["overround_absorbed"] for r in both]),
        "mean_net_pnl_both_fill": _mean([r["pnl"] for r in both]),
        "mean_pnl_per_attempt": _mean([r["pnl"] for r in rows]),
        "mean_pnl_yes_only": _mean([r["pnl"] for r in yes_only]),
        "mean_pnl_no_only": _mean([r["pnl"] for r in no_only]),
        # MEASURED adverse selection (G3): does the leg that fills alone settle against us
        # more often than the population base rate?
        "adverse_selection": {
            "base_settle_yes_rate": base_yes_rate,
            "yes_only_settle_yes_rate":
                _mean([1.0 if r["result"] == "yes" else 0.0 for r in yes_only]),
            "no_only_settle_no_rate":
                _mean([1.0 if r["result"] == "no" else 0.0 for r in no_only]),
            "n_yes_only": len(yes_only), "n_no_only": len(no_only),
        },
        "bootstrap_per_attempt_by_series": _boot_block(per_attempt_units,
                                                       "per_attempt_by_game_series"),
        "bootstrap_per_attempt_by_game": _boot_block(per_attempt_games,
                                                     "per_attempt_by_game_secondary"),
        "bootstrap_both_fill_by_series": _boot_block(both_units,
                                                     "both_fill_only_by_game_series"),
        "rows": rows,
    }


def verdict_for(model_result: dict) -> dict:
    """Apply Q49's own kill conditions to one model's numbers. Returns the verdict plus the
    list of kill reasons that fired - a DEAD verdict recorded cleanly is a success."""
    reasons: List[str] = []
    n = model_result["n_attempts"]
    bfr = model_result["both_fill_rate"]
    boot = model_result["bootstrap_per_attempt_by_series"]
    if n == 0:
        return {"verdict": "DEAD-by-adequacy", "reasons": ["empty_population"]}
    if boot["n_units"] < MIN_CI_UNITS:
        reasons.append(f"below_series_floor({boot['n_units']}<{MIN_CI_UNITS})")
    if bfr is not None and bfr <= S19_FILL_FLOOR + _EPS:
        reasons.append(f"both_fill_rate_at_or_below_S19_floor({bfr:.4%})")
    nbf = model_result["mean_net_pnl_both_fill"]
    if nbf is not None and nbf <= 0:
        reasons.append(f"both_fill_net_overround_non_positive({nbf:+.4f})")
    lo = boot["ci95"][0]
    if lo is None or lo <= 0:
        reasons.append("per_attempt_ci_not_above_zero")
    if not boot["admissible"]:
        reasons.append("bootstrap_inadmissible:" + ",".join(boot["admissibility_reasons"]))
    if not boot["clears_tick_magnitude"]:
        reasons.append("fails_clears_tick_magnitude")
    return {"verdict": "DEAD" if reasons else "SURVIVES", "reasons": reasons}


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
def _fmt(x: Optional[float], nd: int = 4) -> str:
    return "n/a" if x is None else f"{x:+.{nd}f}"


def print_report(report: dict) -> None:
    print("=" * 78)
    print("Q49 / S68 - two-sided BOTH-BID overround-capture maker fill-sim")
    print(f"entry_policy={report['entry_policy']}  min_spread={report['min_spread']:.2f}  "
          f"prices=real_bid  settlement=broker_truth")
    print("=" * 78)
    print(f"population: {report['n_attempts']} attempts / {report['n_series']} game series "
          f"/ {report['n_games']} games  (min {MIN_PRE_SNAPSHOTS} pre-close snapshots)")
    for m in report["models"]:
        c = m["counts"]
        a = m["adverse_selection"]
        b = m["bootstrap_per_attempt_by_series"]
        bb = m["bootstrap_both_fill_by_series"]
        print("-" * 78)
        print(f"FILL MODEL: {m['fill_model']}")
        print(f"  fills: both={c['both']} yes_only={c['yes_only']} no_only={c['no_only']} "
              f"none={c['none']}   both_fill_rate={m['both_fill_rate']:.4%} "
              f"(S19 floor {S19_FILL_FLOOR:.2%})")
        print(f"  leg fill rates: yes={m['yes_leg_fill_rate']:.4%} "
              f"no={m['no_leg_fill_rate']:.4%}")
        print(f"  entry book: mean yes-spread {_fmt(m['mean_yes_spread'])}  "
              f"mean yes_bid+no_bid {_fmt(m['mean_bid_sum'])}  "
              f"frac<$1 {m['frac_bid_sum_below_1']:.3f}")
        print(f"  both-fill cut: gross overround {_fmt(m['mean_gross_overround_both_fill'])} "
              f"-> net of 2 maker fees {_fmt(m['mean_net_pnl_both_fill'])}")
        print(f"  PER-ATTEMPT (deployable) mean P&L {_fmt(m['mean_pnl_per_attempt'])}  "
              f"[yes_only {_fmt(m['mean_pnl_yes_only'])} / no_only "
              f"{_fmt(m['mean_pnl_no_only'])}]")
        print(f"  ADVERSE SELECTION (measured): base settle-YES "
              f"{_fmt(a['base_settle_yes_rate'], 3)} | P(settles YES | YES-leg-only fill, "
              f"n={a['n_yes_only']}) {_fmt(a['yes_only_settle_yes_rate'], 3)} | "
              f"P(settles NO | NO-leg-only fill, n={a['n_no_only']}) "
              f"{_fmt(a['no_only_settle_no_rate'], 3)}")
        print(f"  BLOCK-BOOT by GAME-SERIES (primary, per-attempt): mean {_fmt(b['mean'])} "
              f"95% CI [{_fmt(b['ci95'][0])}, {_fmt(b['ci95'][1])}] "
              f"n_units={b['n_units']} n_obs={b['n_obs']} "
              f"admissible={b['admissible']}{'' if b['admissible'] else ' ' + str(b['admissibility_reasons'])} "
              f"clears_tick={b['clears_tick_magnitude']}")
        print(f"  BLOCK-BOOT by GAME-SERIES (both-fill-only cut): mean {_fmt(bb['mean'])} "
              f"95% CI [{_fmt(bb['ci95'][0])}, {_fmt(bb['ci95'][1])}] "
              f"n_units={bb['n_units']} n_obs={bb['n_obs']} "
              f"admissible={bb['admissible']}")
        print(f"  VERDICT ({m['fill_model']}): {m['verdict']['verdict']}")
        for r in m["verdict"]["reasons"]:
            print(f"     - {r}")
    print("=" * 78)
    print(f"BINDING VERDICT (model {report['binding_model']}): {report['verdict']['verdict']}")
    for r in report["verdict"]["reasons"]:
        print(f"   - {r}")
    print("=" * 78)


def analyze(*, entry_policy: str = "first", min_spread: float = MIN_SPREAD,
            depth_glob: str = DEPTH_GLOB, settle_glob: str = SETTLE_GLOB) -> dict:
    settlements = load_settlements(settle_glob)
    wanted = {t for t in settlements if is_game_series(series_of(t))}
    depth = load_depth_by_ticker(wanted, depth_glob)
    attempts = build_attempts(settlements, depth, entry_policy=entry_policy,
                              min_spread=min_spread)
    models = []
    for fm in FILL_MODELS:
        m = run_model(attempts, fm)
        m["verdict"] = verdict_for(m)
        models.append(m)
    binding = next(m for m in models if m["fill_model"] == "queue_price_through")
    return {
        "schema_version": "q49_two_sided_maker_fillsim.v1",
        "entry_policy": entry_policy, "min_spread": min_spread,
        "n_settled_binary": len(settlements),
        "n_attempts": len(attempts),
        "n_series": len({a["series"] for a in attempts}),
        "n_games": len({a["event_ticker"] for a in attempts}),
        "models": models,
        "binding_model": binding["fill_model"],
        "verdict": binding["verdict"],
        "price_source_tags": {"fills": "real_bid", "settlement": "broker_truth"},
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--entry-policy", choices=ENTRY_POLICIES, default="first")
    ap.add_argument("--min-spread", type=float, default=MIN_SPREAD)
    ap.add_argument("--json-out", default=None,
                    help="write the full report (without per-row windows) to this path")
    args = ap.parse_args(argv)

    report = analyze(entry_policy=args.entry_policy, min_spread=args.min_spread)
    print_report(report)
    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=1, sort_keys=True, default=str)
        print(f"[q49] wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
