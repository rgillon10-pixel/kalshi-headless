#!/usr/bin/env python3
"""Q52 / S78 — Toxicity-filtered selective maker (the measurable-adverse-selection S11 lane).

PRE-REGISTERED, GATE-SEALED PROBE. Built 2026-08-13, BEFORE its data gate opened, under
LOOP-QUEUE.md's idle-run policy (b) ("write + offline-test the probe script for the next
gated queue item so it fires the day its gate opens") — the same discipline, and the same
seal design, that `scripts/q54_s79_flow_continuation_probe.py` was built under on 2026-08-08.

WHY THIS FILE HAD TO BE WRITTEN BEFORE THE TAPE ARRIVED
--------------------------------------------------------
S78's registration (kb/strategies/00-index.md, 2026-08-05, producer + independent
`verifier`) carries THREE MANDATED TIGHTENINGS, and the first of them is a statement about
WHEN the design may be chosen, not about what it is:

  (1) pre-register a COLLAPSED cell design (continuous toxicity score, or <=4 pre-declared
      cells e.g. favorite/dog x wide/tight) BEFORE seeing holdout markout — else L41's
      luckiest-cell failure (600 naive cells >> the units that exist);
  (2) disjoint toxicity-TRAINING vs HOLDOUT windows;
  (3) register-as-edge ONLY if the holdout 95% block-bootstrap-by-GAME (L6) CI > 0 net of
      the maker fee 0.0175 (`core.pricing`, L5), n_units >= 10 (L41), clearing the L27 tick
      gate.

A design chosen after the tape is adequate cannot satisfy (1) by assertion, only by trust.
Choosing it now — while the committed population is knowably short — and sealing it behind
a hash is the only way that mandate can still be MET rather than merely claimed.

MECHANISM (kb/strategies/00-index.md S78; LOOP-QUEUE.md Q52)
------------------------------------------------------------
A maker on Kalshi collects the spread from whoever crosses it, and pays for it in adverse
selection: the crossing taker is sometimes informed, and the price then moves through the
maker. S11's lane has sat `data-collecting` for months because that cost was UNMEASURABLE
from `tape/orderbook_depth/` alone (the L68/L106 "no trade/volume field" wall). The
`tape/kalshi_trades/` executed-print surface (Q51 m1) removes exactly that wall: every print
carries `taker_book_side`, so for each print we can name which side the MAKER was on, and a
later print on the same ticker prices that maker's position. The realized post-fill MARKOUT
is therefore directly observable, and S78 is the strategy that only rests where the measured
markout is positive NET OF THE MAKER FEE.

Counterparty: uninformed retail crossing the spread in cells where informed flow is
demonstrably absent. This is not a new signal — it is a FILTER on an old one, which is why
it lives or dies on whether the filter estimated in one window still works out of sample.

THE SEAL — why a probe built before its gate must be unable to peek
------------------------------------------------------------------
  * `population_report()` is OUTCOME-BLIND BY CONSTRUCTION. It never receives, reads or
    returns a settlement `result`. Settlement membership comes from `settled_ticker_set()`,
    which collapses each result to `is_binary_result(...) -> bool` — the LABEL CLASS, never
    the direction.
  * `outcome_map()` (the only function here that reads a result's VALUE) and `score_rows()`
    (the only one that computes a return) are unreachable from `run()` unless
    `population_report()["admissible"]` is True.
  * The TRAIN-window markout table IS computed in the sealed report, and that is deliberate,
    not a leak: markout is a PRICE quantity (print vs later print), the training window is
    disjoint from the holdout by mandate (2), and the cell-admission rule is the thing being
    pre-registered. What the seal forbids is a SETTLEMENT-derived value, and no such value
    can reach a sealed report — `sealed_report_key_violations()` asserts it key-by-key.
  * `PREREGISTRATION` is hashed into `PREREG_SHA256` and pinned by a test. Tuning a spec
    constant after seeing an answer cannot be a quiet diff; re-pinning it is a declaration.

The probe therefore self-activates: the day the committed tape carries an adequate holdout
population, this file computes and reports the verdict with the spec it was sealed with
today.

PRE-REGISTERED SPEC (locked 2026-08-13; every value chosen from mechanism, not from an answer)
----------------------------------------------------------------------------------------------
  unit                    GAME (`event_ticker_of`, the ticker's own event prefix) — L6.
                          Never the outcome leg: the two sides of one game are one unit.
  universe                sports moneyline `*GAME` markets (KXMVE* excluded by the series
                          suffix test, L31) carrying >=1 `broker_truth` print AND >=2
                          `orderbook_depth` snapshots AND a binary settlement from any
                          declared `core.settlement_sources` family (L300 — nine sources,
                          not just `settlement_ledger`).
  maker leg of a print    `taker_book_side` names the side the TAKER'S OWN order sat on
                          (L279's orientation correction, imported not restated). A taker on
                          the BID is a BUYER of YES, so the MAKER sold YES and holds NO at
                          `1 - yes_price`. A taker on the ASK is a SELLER, so the maker holds
                          YES at `yes_price`.
  markout horizon         30 minutes. The horizon S78's own registration measured its
                          feasibility at (99.1% of prints have a later same-ticker print
                          within 30 min, 97.6% within 5) — chosen so the measurement is
                          defined on essentially the whole print population rather than on a
                          sub-sample selected by liquidity.
  mark price              the LAST `broker_truth` print on the same ticker in `(t, t+30min]`.
                          A print with no later print inside the horizon is UNSCORED for
                          toxicity (it is not scored as zero — L23/L296: absent is absent).
  markout (per contract)  maker holding NO at `1-p`:  `p - P_H`   (the maker gains when the
                          YES price falls); maker holding YES at `p`: `P_H - p`.
  cells (4, collapsed)    (maker price bucket) x (quoted spread bucket), both observable EX
                          ANTE at rest time — a cell a maker cannot see before resting is
                          not a filter, it is hindsight:
                            price   `rich`  if the maker's own resting price >= $0.50 else
                                    `cheap`. Favourite-longshot bias is the strongest
                                    documented price-level effect on this venue (S80's own
                                    K1 leg measured it at -0.169 / +0.153 by side).
                            spread  `wide`  if the snapshot's quoted spread >= $0.03 else
                                    `tight`. Mechanism, not a fitted threshold: the maker fee
                                    at mid-price rounds up to $0.01 per contract, so a
                                    two-tick spread is the bare break-even and $0.03 is the
                                    first spread that leaves a full tick of gross capture.
  book join               a print's cell uses the LAST `orderbook_depth` snapshot at or
                          before it, at most 240 minutes stale. L328 measured the depth
                          revisit interval on traded sports tickers as BIMODAL (p25 28.7 min
                          / median 31.3 / p75 179.5 / p90 360.4); 240 min admits the upper
                          mode without admitting the p90 tail.
  train/holdout split     the committed trade days, sorted ascending: TRAIN = the first
                          floor(N/2) days, HOLDOUT = the rest. Stated as a RULE, not as
                          dates, so it stays disjoint and stays declared as tape arrives. A
                          GAME is assigned to the side of its earliest print day, and a game
                          whose prints STRADDLE the boundary is DROPPED from both — mandate
                          (2) is disjointness of populations, not merely of calendars.
  cell admission          a cell is admitted for resting iff it carries >= 30 TRAIN prints
                          AND its mean TRAIN markout exceeds `fee_per_contract(mean train
                          maker price, MAKER_FEE_RATE)`. Strictly greater: a cell that only
                          matches the fee is not an edge.
  candidate               for each consecutive snapshot pair `(t_i, t_{i+1})` at most 240 min
                          apart on a HOLDOUT ticker, and each side in {yes, no}: rest at that
                          snapshot's own touch bid on our side (`real_bid`, read off the
                          committed ladder — never a midpoint, never a synthetic, the pt1
                          wall), provided the resting price is inside [0.02, 0.98] (outside
                          it one tick is a >50% relative move and the fee model degenerates,
                          L27/L249) and its cell is ADMITTED.
  fill model              QUEUE-AWARE, imported wholesale from the S80 probe so a second copy
                          cannot drift (L100): everyone resting at or better than our price
                          is ahead of us, and we fill only once the cumulative volume of
                          `broker_truth` prints that CONSUME our side inside the interval
                          strictly exceeds that queue. Never `OPTIMISTIC_FILL`, never a
                          queue-departure proxy (L39/L48/L250). Every fill returns the
                          crossing print's `trade_id`.
  exit                    hold to the venue's own settlement (`broker_truth`), $1 or $0.
  cost                    ONE maker fee at the fill, `core.pricing.fee_per_contract` at
                          `MAKER_FEE_RATE`. No hand-rolled rate (L5 — the 4x overcharge).
  headline branch         `all_candidates`: an UNFILLED candidate scores an honest $0.00.
                          `conditional_on_fill` is reported beside it as secondary (the S80
                          convention) because conditioning on having been filled is
                          conditioning on the taker's decision to cross.
  verdict rule            block bootstrap BY GAME (L6), n_boot=10000, seed=42, on the
                          HOLDOUT only; admissible via `bootstrap_verdict_admissible`
                          (min_units=10, L41) and `sign_variation_admissible`
                          (min_exclusive_minority_units=2, L321 — the EXCLUSIVE count, not
                          the touching one); ALIVE only if the CI is strictly > 0 AND clears
                          one tick (L27). Kish effective n reported beside n_units (L322).
  kill                    holdout CI <= 0 / no cell admitted on TRAIN / holdout units below
                          the 10-game floor / no disjoint train-holdout split achievable /
                          zero fills.

WHAT THIS PROBE DELIBERATELY DOES NOT DO
-----------------------------------------
It does not tune the markout horizon, the spread threshold or the price bucket against the
holdout, and it exposes no grid to do so. S80's sensitivity grid was legitimate there because
that verdict was DEAD and the grid could only strengthen a kill; here a grid would be the
luckiest-cell failure mandate (1) exists to forbid. If a future run wants a sensitivity
sweep, it must re-pre-register and re-pin `PREREG_SHA256` in the open.

Read-only. No network anywhere: settlement comes from committed tape through
`core.settlement_sources`. No credentials, no `execution/` import, no order path.
"""
from __future__ import annotations

import argparse
import bisect
import collections
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Sequence, Tuple

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from core.bootstrap import (block_bootstrap, bootstrap_verdict_admissible,  # noqa: E402
                            clears_tick_magnitude, kish_effective_n,
                            sign_variation_admissible)
from core.io import REPO_ROOT, write_report  # noqa: E402
from core.pricing import MAKER_FEE_RATE, fee_per_contract  # noqa: E402
from core.settlement import binary_outcome, is_binary_result  # noqa: E402
from core.settlement_sources import DEFAULT_TAPE_ROOT, resolve_market_results  # noqa: E402
from core.timeutil import parse_iso_utc  # noqa: E402
# The fill model, the ticker grammar and the loaders are IMPORTED from the S80 probe rather
# than re-declared (L100): a second copy of `print_consumes` is exactly how the L279
# orientation bug survived its first repair.
from scripts.q56_s80_print_vwap_overshoot_maker_fade import (  # noqa: E402
    TRADES_GLOB, DEPTH_GLOB, event_ticker_of, is_game_series, leg_pnl, load_books,
    load_prints, print_consumes, queue_ahead_at, series_of, simulate_fill)
from scripts.q51_maker_fillsim import TAKER_BUYS, TAKER_SELLS  # noqa: E402

DEFAULT_REPORT_STEM = "q52_s78_toxicity_filtered_maker"

PREREGISTRATION: Dict[str, object] = {
    "candidate": "S78",
    "queue_item": "Q52",
    "locked_utc_date": "2026-08-13",
    "unit": "game (event_ticker_of(market_ticker))",
    "universe": ("sports *GAME moneyline markets with >=1 broker_truth print, >=2 "
                 "orderbook_depth snapshots, and a binary settlement from a declared "
                 "core.settlement_sources family"),
    "markout_horizon_minutes": 30,
    "markout_mark": "last same-ticker broker_truth print in (t, t+horizon]; else UNSCORED",
    "cell_axes": ["maker_price_bucket", "quoted_spread_bucket"],
    "maker_price_bucket_threshold": 0.50,
    "wide_spread_min": 0.03,
    "n_cells": 4,
    "max_book_staleness_minutes": 240,
    "max_interval_minutes": 240,
    "split_rule": ("distinct committed trade days sorted ascending; TRAIN = first floor(N/2) "
                   "days, HOLDOUT = the rest; a game is assigned by its earliest print day "
                   "and a game straddling the boundary is dropped from both"),
    "min_train_prints_per_cell": 30,
    "cell_admission": ("mean TRAIN markout > fee_per_contract(mean TRAIN maker price, "
                       "MAKER_FEE_RATE) and n_train_prints >= min_train_prints_per_cell"),
    "rest_price": "the snapshot's own touch bid on our side (real_bid)",
    "price_band": [0.02, 0.98],
    "fill_model": "queue-aware; cumulative consuming print volume must strictly exceed the queue",
    "exit": "hold to venue settlement (broker_truth)",
    "fee_side": "maker",
    "headline_branch": "all_candidates",
    "min_units": 10,
    "min_exclusive_minority_units": 2,
    "n_boot": 10000,
    "seed": 42,
    "tick": 0.01,
    "min_ticks": 1.0,
    "verdict_rule": ("ALIVE only if the HOLDOUT all_candidates block-bootstrap-by-game 95% CI "
                     "is strictly > 0 AND clears one tick; otherwise DEAD or INADMISSIBLE"),
}

HORIZON = timedelta(minutes=float(PREREGISTRATION["markout_horizon_minutes"]))
PRICE_BUCKET_THRESHOLD = float(PREREGISTRATION["maker_price_bucket_threshold"])
WIDE_SPREAD_MIN = float(PREREGISTRATION["wide_spread_min"])
MAX_BOOK_STALENESS = timedelta(minutes=float(PREREGISTRATION["max_book_staleness_minutes"]))
MAX_INTERVAL = timedelta(minutes=float(PREREGISTRATION["max_interval_minutes"]))
MIN_TRAIN_PRINTS_PER_CELL = int(PREREGISTRATION["min_train_prints_per_cell"])
PRICE_BAND = (float(PREREGISTRATION["price_band"][0]), float(PREREGISTRATION["price_band"][1]))
MIN_UNITS = int(PREREGISTRATION["min_units"])
MIN_EXCLUSIVE_MINORITY_UNITS = int(PREREGISTRATION["min_exclusive_minority_units"])
N_BOOT = int(PREREGISTRATION["n_boot"])
SEED = int(PREREGISTRATION["seed"])
TICK = float(PREREGISTRATION["tick"])
MIN_TICKS = float(PREREGISTRATION["min_ticks"])

SIDE_YES = "yes"
SIDE_NO = "no"
_EPS = 1e-9

PRICE_SOURCE_TAGS = {
    "rest_price": "real_bid",         # the resting maker price, read off the committed ladder
    "fill_evidence": "broker_truth",  # the executed print that crosses our queue
    "toxicity_signal": "broker_truth",  # markout is print-vs-print, an executed-trade fact
    "settlement": "broker_truth",     # core.settlement_sources
}

# KEY tokens a SEALED (pre-gate) report is forbidden to carry. Deliberately NARROWER than
# the Q54 probe's list, and the difference is the whole design: Q54 banned "mean" because
# every mean it could compute was a mean of RETURNS. Here the sealed report's means are
# TRAIN-WINDOW MARKOUTS — a price-minus-price quantity on a window that mandate (2) makes
# disjoint from the scored one, and the very quantity mandate (1) requires be pre-registered.
# Banning it would not make the seal stronger, it would make the pre-registration
# unverifiable. What must never appear is a SETTLEMENT-derived field.
FORBIDDEN_SEALED_KEY_TOKENS = ("pnl", "ci95", "won", "bootstrap", "profit", "outcome",
                               "settle_result", "verdict")


def _walk_keys(obj: object) -> List[str]:
    """Every key name appearing anywhere in a nested report structure."""
    out: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.append(str(k))
            out.extend(_walk_keys(v))
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out.extend(_walk_keys(v))
    return out


def sealed_report_key_violations(report: Dict[str, object]) -> List[str]:
    """Keys in a SEALED report that would betray a settlement-derived value. Empty is the
    only acceptable answer while the gate is shut.

    The `preregistration` subtree is EXCLUDED from the scan on purpose: it is a frozen
    constant hashed into `PREREG_SHA256`, so it cannot carry a value derived from anything,
    and its own field `verdict_rule` would otherwise be reported forever — a guard that
    always fires is a guard that gets ignored (L155)."""
    scanned = {k: v for k, v in report.items() if k != "preregistration"} \
        if isinstance(report, dict) else report
    return sorted({k for k in _walk_keys(scanned)
                   for tok in FORBIDDEN_SEALED_KEY_TOKENS if tok in k.lower()})


def preregistration_sha256(spec: Optional[Dict[str, object]] = None) -> str:
    """Stable digest of the sealed spec: canonical JSON, so the hash tracks VALUES."""
    payload = json.dumps(spec if spec is not None else PREREGISTRATION,
                         sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


PREREG_SHA256 = "SEALED"  # replaced at import time below; literal kept for grep-ability
PREREG_SHA256 = preregistration_sha256()


# --------------------------------------------------------------------------- #
# Pure helpers — no clock, no I/O, offline-testable
# --------------------------------------------------------------------------- #
def quoted_spread(snap: Dict[str, object]) -> Optional[float]:
    """The snapshot's own quoted spread in dollars, from the committed touch fields.

    None (not 0.0) when either side of the touch is absent — an empty book is missing data,
    never a zero spread (L23)."""
    hi = snap.get("best_yes_ask")
    lo = snap.get("best_yes_bid")
    if hi is None or lo is None:
        return None
    return float(hi) - float(lo)


def touch_bid(snap: Dict[str, object], side: str) -> Optional[float]:
    """Our own resting price if we join the touch on `side` — `real_bid`, read off the
    committed snapshot, never derived from a midpoint."""
    key = "best_yes_bid" if side == SIDE_YES else "best_no_bid"
    v = snap.get(key)
    return None if v is None else float(v)


def ladder_of(snap: Dict[str, object], side: str) -> Optional[Sequence[Sequence[float]]]:
    """The resting ladder on `side` — the queue we would join."""
    return snap.get("yes_bids") if side == SIDE_YES else snap.get("no_bids")


def maker_leg_of_print(yes_price: float, taker_book_side: str) -> Optional[Tuple[str, float]]:
    """(side the MAKER ends up holding, the maker's own price) for one executed print.

    `taker_book_side` names the side the TAKER'S OWN order sat on (L279): a taker resting on
    the BID is a BUYER of YES, so the maker SOLD YES and is long NO at `1 - yes_price`.
    Returns None on an unrecognised/absent side rather than guessing a direction."""
    if taker_book_side == TAKER_BUYS:
        return (SIDE_NO, 1.0 - float(yes_price))
    if taker_book_side == TAKER_SELLS:
        return (SIDE_YES, float(yes_price))
    return None


def maker_markout(side: str, yes_price: float, mark_yes_price: float) -> float:
    """Realized post-fill markout per contract for the maker's own leg, in dollars.

    Long NO at `1-p`, later worth `1-P_H`  ->  markout `p - P_H`.
    Long YES at `p`,  later worth `P_H`    ->  markout `P_H - p`."""
    if side == SIDE_NO:
        return float(yes_price) - float(mark_yes_price)
    return float(mark_yes_price) - float(yes_price)


def cell_of(maker_price: float, spread: float) -> Tuple[str, str]:
    """The pre-registered 2x2 cell: (price bucket, spread bucket)."""
    return ("rich" if float(maker_price) >= PRICE_BUCKET_THRESHOLD - _EPS else "cheap",
            "wide" if float(spread) >= WIDE_SPREAD_MIN - _EPS else "tight")


def cell_key(cell: Tuple[str, str]) -> str:
    return f"{cell[0]}/{cell[1]}"


ALL_CELL_KEYS: Tuple[str, ...] = tuple(
    cell_key((p, s)) for p in ("cheap", "rich") for s in ("tight", "wide"))


def mark_price_after(prints: Sequence[tuple], i: int,
                     horizon: timedelta = HORIZON) -> Optional[float]:
    """The LAST print's `yes_price` strictly after `prints[i]` and within `horizon`.

    `prints` is the S80 loader's per-ticker tuple list, sorted on `(created_time, trade_id)`
    — a DECLARED tie-break (L323), inherited rather than re-implemented."""
    if i < 0 or i >= len(prints):
        return None
    t0 = prints[i][0]
    deadline = t0 + horizon
    j = i + 1
    last = None
    while j < len(prints) and prints[j][0] <= deadline:
        if prints[j][0] > t0:
            last = float(prints[j][1])
        j += 1
    return last


def snapshot_at_or_before(snaps: Sequence[dict], ts_list: Sequence[datetime],
                          when: datetime,
                          max_staleness: timedelta = MAX_BOOK_STALENESS) -> Optional[dict]:
    """The last book snapshot at or before `when`, if it is not staler than the declared
    ceiling. `ts_list` is the pre-parsed, sorted `captured_at` series for `snaps`."""
    if not snaps:
        return None
    k = bisect.bisect_right(ts_list, when) - 1
    if k < 0:
        return None
    if when - ts_list[k] > max_staleness:
        return None
    return snaps[k]


def split_days(days: Sequence[str]) -> Tuple[List[str], List[str]]:
    """The pre-registered split RULE applied to the committed trade days."""
    ordered = sorted(set(days))
    cut = len(ordered) // 2
    return ordered[:cut], ordered[cut:]


def game_day_map(prints_by_ticker: Dict[str, List[tuple]]) -> Dict[str, set]:
    """game -> the set of UTC dates on which it printed. The straddle test's input."""
    out: Dict[str, set] = collections.defaultdict(set)
    for tk, rows in prints_by_ticker.items():
        g = event_ticker_of(tk)
        for r in rows:
            out[g].add(r[0].date().isoformat())
    return dict(out)


def assign_games(game_days: Dict[str, set], train_days: Sequence[str],
                 holdout_days: Sequence[str]) -> Dict[str, object]:
    """Assign each game to TRAIN or HOLDOUT, dropping straddlers.

    Disjointness is enforced on the POPULATION, not merely on the calendar: a game that
    printed on both sides of the boundary would leak its own toxicity estimate into its own
    holdout score, which is the failure mandate (2) exists to prevent."""
    tr, ho = set(train_days), set(holdout_days)
    train, holdout, straddling = set(), set(), set()
    for g, days in game_days.items():
        in_tr = bool(days & tr)
        in_ho = bool(days & ho)
        if in_tr and in_ho:
            straddling.add(g)
        elif in_tr:
            train.add(g)
        elif in_ho:
            holdout.add(g)
    return {"train_games": train, "holdout_games": holdout, "straddling_games": straddling}


def admit_cell(n_prints: int, mean_markout: Optional[float],
               mean_maker_price: Optional[float]) -> dict:
    """The pre-registered admission test for one cell, reported as a dict so a refusal
    always says WHY (the `bootstrap_verdict_admissible` shape)."""
    if mean_markout is None or mean_maker_price is None or n_prints <= 0:
        return {"n_train_prints": int(n_prints), "mean_markout": None,
                "mean_maker_price": None, "fee": None, "net_of_fee": None,
                "admitted": False, "reasons": ["no_train_prints"]}
    fee = fee_per_contract(float(mean_maker_price), MAKER_FEE_RATE)
    net = float(mean_markout) - fee
    reasons: List[str] = []
    if n_prints < MIN_TRAIN_PRINTS_PER_CELL:
        reasons.append("below_min_train_prints")
    if not net > 0:
        reasons.append("markout_within_maker_fee")
    return {"n_train_prints": int(n_prints), "mean_markout": float(mean_markout),
            "mean_maker_price": float(mean_maker_price), "fee": fee, "net_of_fee": net,
            "admitted": not reasons, "reasons": reasons}


# --------------------------------------------------------------------------- #
# Settlement — the outcome-blind half and the outcome-reading half, kept apart
# --------------------------------------------------------------------------- #
def settled_ticker_set(tickers: Sequence[str], root: str = DEFAULT_TAPE_ROOT
                       ) -> Tuple[FrozenSet[str], Dict[str, object]]:
    """OUTCOME-BLIND settlement membership: which tickers carry a BINARY result.

    Returns no result VALUE — `is_binary_result` collapses the label to its class, so the
    caller learns THAT a market settled and never HOW. This is the function
    `population_report()` may call; `outcome_map()` is not."""
    rep = resolve_market_results(sorted(set(tickers)), root=root)
    settled = frozenset(t for t, m in rep.resolved.items() if is_binary_result(m.result))
    coverage = {
        "n_requested": rep.requested,
        "n_settled_binary": len(settled),
        "n_non_binary": len(rep.non_binary),
        "n_listed_unsettled": len(rep.listed_unsettled),
        "n_unresolved": len(rep.unresolved),
        "per_source_hits": dict(sorted(rep.per_source_hits.items())),
        "sources_scanned": list(rep.sources_scanned),
        "sources_absent_on_disk": list(rep.sources_absent_on_disk),
    }
    return settled, coverage


def outcome_map(tickers: Sequence[str], root: str = DEFAULT_TAPE_ROOT) -> Dict[str, str]:
    """ticker -> 'yes'/'no'. THE ONLY function here that reads an outcome's VALUE, and it is
    unreachable from `run()` until the adequacy gate has opened. Non-binary results are
    DROPPED, never scored as a loss (L52)."""
    rep = resolve_market_results(sorted(set(tickers)), root=root)
    out: Dict[str, str] = {}
    for t, m in rep.resolved.items():
        o = binary_outcome(m.result)
        if o is not None:
            out[t] = "yes" if o == 1 else "no"
    return out


# --------------------------------------------------------------------------- #
# TRAIN: the toxicity table (price-only, no settlement anywhere in scope)
# --------------------------------------------------------------------------- #
def train_cell_table(prints_by_ticker: Dict[str, List[tuple]],
                     books_by_ticker: Dict[str, List[dict]],
                     train_games: Sequence[str]) -> Dict[str, dict]:
    """Per-cell TRAIN markout statistics and the pre-registered admission decision.

    Every cell in `ALL_CELL_KEYS` appears in the output even when empty: an absent key reads
    as 'not measured' and that ambiguity is exactly what L296 was written about."""
    want = set(train_games)
    sums: Dict[str, float] = collections.defaultdict(float)
    price_sums: Dict[str, float] = collections.defaultdict(float)
    counts: Dict[str, int] = collections.defaultdict(int)
    for tk, prints in prints_by_ticker.items():
        if event_ticker_of(tk) not in want:
            continue
        snaps = books_by_ticker.get(tk) or []
        ts_list = [parse_iso_utc(s["captured_at"]) for s in snaps if s.get("captured_at")]
        snaps = [s for s in snaps if s.get("captured_at")]
        for i, p in enumerate(prints):
            leg = maker_leg_of_print(float(p[1]), str(p[3]))
            if leg is None:
                continue
            side, maker_price = leg
            mark = mark_price_after(prints, i)
            if mark is None:
                continue
            snap = snapshot_at_or_before(snaps, ts_list, p[0])
            if snap is None:
                continue
            spread = quoted_spread(snap)
            if spread is None:
                continue
            k = cell_key(cell_of(maker_price, spread))
            sums[k] += maker_markout(side, float(p[1]), mark)
            price_sums[k] += maker_price
            counts[k] += 1
    table: Dict[str, dict] = {}
    for k in ALL_CELL_KEYS:
        n = counts.get(k, 0)
        mm = (sums[k] / n) if n else None
        mp = (price_sums[k] / n) if n else None
        table[k] = admit_cell(n, mm, mp)
    return table


def admitted_cells(table: Dict[str, dict]) -> FrozenSet[str]:
    return frozenset(k for k, v in table.items() if v.get("admitted"))


# --------------------------------------------------------------------------- #
# HOLDOUT: candidate enumeration + queue-aware fills (still outcome-blind)
# --------------------------------------------------------------------------- #
def holdout_candidates(prints_by_ticker: Dict[str, List[tuple]],
                       books_by_ticker: Dict[str, List[dict]],
                       holdout_games: Sequence[str],
                       admitted: FrozenSet[str]) -> List[dict]:
    """Every resting candidate the sealed spec generates on the holdout, with its fill
    resolved. Contains no settlement value — fills are decided by executed prints alone, so
    this whole function stays inside the seal."""
    want = set(holdout_games)
    rows: List[dict] = []
    for tk in sorted(prints_by_ticker):
        if event_ticker_of(tk) not in want:
            continue
        snaps = [s for s in (books_by_ticker.get(tk) or []) if s.get("captured_at")]
        if len(snaps) < 2:
            continue
        prints = prints_by_ticker.get(tk) or []
        ts_list = [parse_iso_utc(s["captured_at"]) for s in snaps]
        p_ts = [p[0] for p in prints]
        for i in range(len(snaps) - 1):
            t_i, t_next = ts_list[i], ts_list[i + 1]
            if t_next - t_i > MAX_INTERVAL:
                continue
            spread = quoted_spread(snaps[i])
            if spread is None:
                continue
            lo = bisect.bisect_right(p_ts, t_i)
            hi = bisect.bisect_right(p_ts, t_next)
            window = prints[lo:hi]
            for side in (SIDE_YES, SIDE_NO):
                bid = touch_bid(snaps[i], side)
                if bid is None or not (PRICE_BAND[0] - _EPS <= bid <= PRICE_BAND[1] + _EPS):
                    continue
                ck = cell_key(cell_of(bid, spread))
                if ck not in admitted:
                    continue
                qa = queue_ahead_at(ladder_of(snaps[i], side), bid)
                fill = simulate_fill(side, bid, qa, window)
                rows.append({
                    "ticker": tk,
                    "unit": event_ticker_of(tk),
                    "series": series_of(tk),
                    "side": side,
                    "cell": ck,
                    "rest_price": bid,
                    "rest_price_source_tag": PRICE_SOURCE_TAGS["rest_price"],
                    "quoted_spread": spread,
                    "queue_ahead": fill["queue_ahead"],
                    "consuming_volume": fill["consuming_volume"],
                    "filled": bool(fill["filled"]),
                    "fill_trade_id": fill["fill_trade_id"],
                    "t_rest": t_i.isoformat(),
                    "t_interval_end": t_next.isoformat(),
                })
    return rows


# --------------------------------------------------------------------------- #
# Adequacy — the sealed verdict
# --------------------------------------------------------------------------- #
def population_report(table: Dict[str, dict], rows: Sequence[dict],
                      settled: FrozenSet[str], coverage: Dict[str, object],
                      split: Dict[str, object]) -> Dict[str, object]:
    """The ADEQUACY verdict, computed with no settlement VALUE anywhere in scope."""
    adm = sorted(admitted_cells(table))
    scoreable = [r for r in rows if r["ticker"] in settled]
    units = sorted({r["unit"] for r in scoreable})
    per_unit: Dict[str, int] = collections.defaultdict(int)
    for r in scoreable:
        per_unit[r["unit"]] += 1
    n_fills = sum(1 for r in scoreable if r["filled"])

    unit_sides: Dict[str, List[str]] = collections.defaultdict(list)
    for r in scoreable:
        unit_sides[r["unit"]].append(r["side"])
    sv = sign_variation_admissible(
        dict(unit_sides), min_exclusive_minority_units=MIN_EXCLUSIVE_MINORITY_UNITS,
        sides=(SIDE_YES, SIDE_NO))

    reasons: List[str] = []
    if not adm:
        reasons.append("no_admitted_cell")
    if not scoreable:
        reasons.append("no_scoreable_candidates")
    if len(units) < MIN_UNITS:
        reasons.append("below_min_units")
    if n_fills == 0:
        reasons.append("zero_fills")
    # `sign_variation_admissible` returns the `bootstrap_verdict_admissible` SHAPE, whose
    # boolean key is `admissible` — reading a non-existent `ok` here would have made the
    # gate fail closed forever on a population that clears it (caught on first live run).
    if not sv.get("admissible"):
        reasons.append("no_sign_variation")
    if not split.get("train_days") or not split.get("holdout_days"):
        reasons.append("no_train_holdout_split")

    return {
        "split": split,
        "train_cell_table": table,
        "admitted_cells": adm,
        "n_admitted_cells": len(adm),
        "n_candidates_all": len(rows),
        "n_candidates_scoreable": len(scoreable),
        "n_fills_scoreable": n_fills,
        "fill_rate_scoreable": (n_fills / len(scoreable)) if scoreable else None,
        "n_units": len(units),
        "min_units": MIN_UNITS,
        "units_short_of_floor": max(0, MIN_UNITS - len(units)),
        "candidates_per_unit": dict(sorted(per_unit.items())),
        "sign_variation": sv,
        "settlement_coverage": coverage,
        "gate_reasons": reasons,
        "admissible": not reasons,
    }


# --------------------------------------------------------------------------- #
# Scoring — reachable ONLY once the adequacy gate has opened
# --------------------------------------------------------------------------- #
def score_rows(rows: Sequence[dict], outcomes: Dict[str, str]) -> List[dict]:
    """Per-candidate realized P&L per contract. An UNFILLED candidate scores an honest
    $0.00; a filled one is priced by the imported `leg_pnl` (payout - rest price - ONE maker
    fee). Every input is `broker_truth` or `real_bid`; nothing here is synthetic."""
    out: List[dict] = []
    for r in rows:
        res = outcomes.get(r["ticker"])
        if res not in ("yes", "no"):
            continue
        row = dict(r)
        if r["filled"]:
            row["pnl"] = leg_pnl(r["side"], float(r["rest_price"]), res)
            row["won"] = bool((r["side"] == SIDE_YES and res == "yes")
                              or (r["side"] == SIDE_NO and res == "no"))
        else:
            row["pnl"] = 0.0
            row["won"] = None
        out.append(row)
    return out


def unit_values(scored: Sequence[dict], *, only_filled: bool = False) -> Dict[str, List[float]]:
    uv: Dict[str, List[float]] = collections.defaultdict(list)
    for r in scored:
        if only_filled and not r["filled"]:
            continue
        uv[r["unit"]].append(float(r["pnl"]))
    return dict(uv)


def bootstrap_branch(scored: Sequence[dict], *, only_filled: bool) -> dict:
    uv = unit_values(scored, only_filled=only_filled)
    boot = block_bootstrap(uv, n_boot=N_BOOT, seed=SEED)
    adm = bootstrap_verdict_admissible(uv, min_units=MIN_UNITS)
    kish = kish_effective_n([len(v) for v in uv.values()])
    tick_ok = clears_tick_magnitude(boot.get("ci95") or [None, None],
                                    tick=TICK, min_ticks=MIN_TICKS)
    return {"branch": "conditional_on_fill" if only_filled else "all_candidates",
            "n_units": boot.get("n_units"), "n_obs": boot.get("n_obs"),
            "mean": boot.get("mean"), "ci95": boot.get("ci95"),
            "n_boot": N_BOOT, "seed": SEED,
            "admissibility": adm, "kish_effective_n": kish,
            "clears_tick_magnitude": tick_ok}


def verdict_label(headline: dict) -> str:
    ci = headline.get("ci95") or [None, None]
    if not (headline.get("admissibility") or {}).get("admissible"):
        return "INADMISSIBLE"
    if ci[0] is not None and ci[0] > 0 and headline.get("clears_tick_magnitude"):
        return "ALIVE"
    return "DEAD"


# --------------------------------------------------------------------------- #
# run
# --------------------------------------------------------------------------- #
def run(*, trades_glob: str = TRADES_GLOB, depth_glob: str = DEPTH_GLOB,
        settlement_root: str = DEFAULT_TAPE_ROOT,
        population_only: bool = False) -> Dict[str, object]:
    prints_by_ticker = load_prints(trades_glob, sports_only=True)
    tickers = sorted(t for t in prints_by_ticker if is_game_series(t))
    prints_by_ticker = {t: prints_by_ticker[t] for t in tickers}
    books_by_ticker = load_books(depth_glob, wanted=tickers)

    days = sorted({p[0].date().isoformat() for rows in prints_by_ticker.values() for p in rows})
    train_days, holdout_days = split_days(days)
    gdm = game_day_map(prints_by_ticker)
    assign = assign_games(gdm, train_days, holdout_days)
    split = {
        "trade_days": days,
        "train_days": train_days,
        "holdout_days": holdout_days,
        "n_games_total": len(gdm),
        "n_train_games": len(assign["train_games"]),
        "n_holdout_games": len(assign["holdout_games"]),
        "n_straddling_games_dropped": len(assign["straddling_games"]),
    }

    table = train_cell_table(prints_by_ticker, books_by_ticker, sorted(assign["train_games"]))
    rows = holdout_candidates(prints_by_ticker, books_by_ticker,
                              sorted(assign["holdout_games"]), admitted_cells(table))
    settled, coverage = settled_ticker_set(sorted({r["ticker"] for r in rows}) or tickers,
                                           root=settlement_root)
    pop = population_report(table, rows, settled, coverage, split)

    report: Dict[str, object] = {
        "schema_version": "q52_s78_toxicity_filtered_maker.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "queue_item": "Q52",
        "strategy": "S78",
        "preregistration": dict(PREREGISTRATION),
        "preregistration_sha256": PREREG_SHA256,
        "n_sports_game_tickers": len(tickers),
        "n_tickers_with_books": sum(1 for t in tickers if books_by_ticker.get(t)),
        "population": pop,
        "price_source_tags": dict(PRICE_SOURCE_TAGS),
        "fee_side": "maker",
        "network_calls": 0,
    }

    if population_only or not pop["admissible"]:
        report["sealed"] = True
        report["gate_note"] = (
            "SEALED — the adequacy gate is shut (or scoring was explicitly withheld). No "
            "settlement value was read and no return was computed; `outcome_map()` and "
            "`score_rows()` were never called. Re-running this file unchanged after more "
            "tape lands is what fires the pre-registered test.")
        report["sealed_key_violations"] = sealed_report_key_violations(report)
        return report

    outcomes = outcome_map(sorted({r["ticker"] for r in rows}), root=settlement_root)
    scored = score_rows(rows, outcomes)
    headline = bootstrap_branch(scored, only_filled=False)
    conditional = bootstrap_branch(scored, only_filled=True)
    report["sealed"] = False
    report["scoring"] = {
        "n_scored": len(scored),
        "n_filled": sum(1 for r in scored if r["filled"]),
        "headline": headline,
        "conditional_on_fill": conditional,
        "verdict": verdict_label(headline),
    }
    return report


def _summarize(rep: Dict[str, object]) -> str:
    pop = rep["population"]
    head = (f"S78/Q52 sealed={rep['sealed']} cells_admitted={pop['n_admitted_cells']}"
            f"/{len(ALL_CELL_KEYS)} train_games={pop['split']['n_train_games']}"
            f" holdout_games={pop['split']['n_holdout_games']}"
            f" candidates={pop['n_candidates_scoreable']} fills={pop['n_fills_scoreable']}"
            f" units={pop['n_units']}/{pop['min_units']}"
            f" gate_reasons={pop['gate_reasons'] or '[]'}")
    sc = rep.get("scoring")
    if sc:
        h = sc["headline"]
        head += (f" | {sc['verdict']} mean={h['mean']} ci95={h['ci95']}"
                 f" n_units={h['n_units']}")
    return head


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true", help="print the full report as JSON")
    ap.add_argument("--population-only", action="store_true",
                    help="stop at the outcome-blind adequacy report even if the gate is open")
    ap.add_argument("--report-stem", default=DEFAULT_REPORT_STEM)
    ap.add_argument("--no-write", action="store_true", help="do not write reports/<stem>.json")
    args = ap.parse_args(argv)
    rep = run(population_only=args.population_only)
    if not args.no_write:
        write_report(args.report_stem, rep)
    print(json.dumps(rep, indent=2) if args.json else _summarize(rep))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
