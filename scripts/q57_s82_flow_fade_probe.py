#!/usr/bin/env python3
"""Q57 / S82 — Game-level signed-taker-flow FADE taker, held to settlement.

BINDING PROBE for LOOP-QUEUE.md Q57 / `kb/strategies/00-index.md` S82 (Q21 round #32
survivor, registered 2026-08-16). READ-ONLY, fully offline, no network, no order path.

MECHANISM (S82)
---------------
Over each settled sports GAME, aggregate net `count`-weighted taker-signed volume from
`tape/kalshi_trades/` (`broker_truth` executed prints carrying `taker_book_side` /
`taker_outcome_side`) over a pre-close window. When net flow is EXTREME toward one side,
TAKE THE OPPOSITE side at a real `orderbook_depth` ask and HOLD to settlement — i.e. fade
late retail herding. The registered prior is a KILL: WALL-A (a 0.07 taker fee plus the
book's own overround) has killed every taker cousin, and the only thing separating S82 from
the DEAD S79 (aggressor-flow CONTINUATION, CI [-0.2724, +0.1521]) is round-#28's
"bigger prints settle worse" residual applied with the OPPOSITE sign.

THE THREE BINDING GATES Q57 MANDATES (verifier-mandated at registration; not weakened here)
-------------------------------------------------------------------------------------------
 (1) Entry at `real_ask` from the nearest in-window `orderbook_depth` snapshot, NEVER a mid,
     never a reconstructed/synthetic price (the pt1 wall / Hard Rule #1).
 (2) >= 10 independent GAMES (L41), Kish effective n reported (L322), >= 1 opposing-sign
     unit (L312/L321), and the CI must clear the L27 tick-magnitude gate net of fee AND of
     the book's overround (WALL-A).
 (3) The aggregation window is PRE-REGISTERED and PROVEN to differ from S79's print-level
     continuation window BEFORE scoring — else L51 (fade/follow complementarity on a 2-way
     market) collapses S82 into the already-dead S79 and the measurement is void.

`l51_differentiation()` implements (3) and is called by `run()` BEFORE any outcome value is
read. It is outcome-blind by construction: it never receives, reads or returns a settlement
result. If it returns `voided=True`, `run()` stops at VOID and never scores.

THE JOIN KEY GOTCHA (baked into Q57's registration; this is what a naive probe gets wrong)
-------------------------------------------------------------------------------------------
`kalshi_trades.event_ticker` is `None` on every committed row (213,488/213,488 verified). The
game-id is `ticker.rsplit('-', 1)[0]` — a join on `event_ticker` silently reads ZERO units.
`game_id_of()` is the single place that key is spelled.

WHAT THE ENTRY PRICE IS, AND WHY IT CAN EXIST AT ALL
-----------------------------------------------------
The trade tape has no resting book, so a "print tape has no book -> WALL-B" reflex would kill
this. It does not apply: `tape/orderbook_depth/` is a SEPARATE family covering the same GAME
tickers and carries `best_yes_ask`/`best_no_ask` under `price_source_tags.asks == "real_ask"`.
The fillable-price surface is the UNION of families, not the trade tape alone. Every entry
price this module scores is read from that field and tagged `real_ask`; nothing is derived,
averaged, or complemented from a bid.

CAUSALITY, AND THE ONE RESIDUAL LOOK-AHEAD (declared, not hidden)
------------------------------------------------------------------
The flow window ENDS at the entry instant, so no print after the fill informs the signal.
The residual is the ANCHOR: the entry instant is "the last depth snapshot at/before
`close_time`", and `close_time` is read from `tape/settlement_ledger/` — a POST-settlement
capture. L360/L361 (2026-08-16) established that Kalshi REWRITES `close_time` at settlement,
always EARLIER, so the settled value is not provably the value a trader saw ex ante. In THIS
population no ticker carries more than one distinct `close_time` (checked and reported as
`close_time_distinct_values_max`), but with only two `settlement_ledger` day-files there is no
pre-settlement observation to compare against. The anchor's ex-ante knowability is therefore
UNVERIFIED, and any positive result from this probe would owe that check before graduation.
A NEGATIVE result is unaffected: a look-ahead anchor can only flatter the strategy.

Run:
    python3 scripts/q57_s82_flow_fade_probe.py
Writes `reports/q57_s82_flow_fade.json`. Exit 0 always (a verdict is not an error).
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Sequence, Tuple

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from core.bootstrap import (  # noqa: E402
    block_bootstrap,
    bootstrap_verdict_admissible,
    clears_tick_magnitude,
    entry_instant_concentration,
    kish_effective_n,
    sign_variation_admissible,
)
from core.io import REPO_ROOT  # noqa: E402
from core.pricing import TAKER_FEE_RATE, fee_per_contract, is_fillable_ask  # noqa: E402
from core.settlement import binary_outcome, is_binary_result  # noqa: E402
from core.settlement_sources import DEFAULT_TAPE_ROOT, resolve_market_results  # noqa: E402
from core.timeutil import parse_iso_utc  # noqa: E402
from scripts import q51_maker_fillsim as M  # noqa: E402

TRADES_TAPE = REPO_ROOT / "tape" / "kalshi_trades"
DEPTH_TAPE = REPO_ROOT / "tape" / "orderbook_depth"
LEDGER_TAPE = REPO_ROOT / "tape" / "settlement_ledger"
REPORT_PATH = REPO_ROOT / "reports" / "q57_s82_flow_fade.json"

# --------------------------------------------------------------------------- #
# THE PRE-REGISTRATION. Sealed 2026-08-16, BEFORE any outcome value was read.
# Every value is chosen from MECHANISM (see the justification beside it), never from a
# return distribution. Changing any value changes PREREG_SHA256 and breaks
# tests/test_q57_s82_flow_fade_probe.py::test_preregistration_hash_is_sealed — that test
# failing is the intended alarm: a spec edit after scoring is tuning, not a bug fix.
# --------------------------------------------------------------------------- #
PREREGISTRATION: Dict[str, object] = {
    "sealed_on": "2026-08-16",
    "strategy": "S82",
    "queue_item": "Q57",
    "unit": "game",
    # ANCHOR: the venue's own recorded close, `broker_truth`. See the look-ahead note above.
    "close_anchor": "settlement_ledger.close_time",
    # ENTRY INSTANT: the last real book we can see before the venue closes the market. The
    # depth collector runs hourly, so "nearest in-window snapshot" (Q57 gate 1) is this one.
    "entry_instant_rule": "last_orderbook_depth_snapshot_at_or_before_close",
    # A book captured days before close is not a pre-close price. 60 min is the depth
    # collector's own cadence: the tightest lag that can be met by a once-an-hour capture.
    "max_entry_lag_minutes": 60,
    # FLOW WINDOW: 120 min ending AT the entry instant. Chosen as the final-approach /
    # in-play stretch of a sports game, and deliberately 4x S79's 30-min lookback, anchored
    # to CLOSE rather than to an hourly grid — the two structural differences Q57 gate (3)
    # requires be proven, not asserted (see `l51_differentiation`).
    "flow_window_minutes": 120,
    "flow_weight": "count",
    "flow_sign_convention": "+count when the taker BUYS yes, -count when the taker buys no",
    # SIGNAL: scale-free imbalance ratio, so "extreme" means the same thing on a 33-contract
    # market and a 3.5M-contract one. S79 used an ABSOLUTE contract threshold; this is a
    # different statistic, not a re-tuned one.
    "signal": "rho = net_signed_count / total_count over the window, on one ticker",
    "game_ticker_rule": "argmax |rho| over the game's traded tickers; ties -> min(ticker)",
    "min_abs_rho": 0.20,          # a 60/40 split is the weakest thing worth calling "extreme"
    "min_window_count": 100.0,    # rho=1.0 on 33 contracts is no flow, not extreme flow
    "direction": "FADE",          # take the side OPPOSITE the net flow
    "entry_price_field": "best_no_ask if rho>0 else best_yes_ask",
    "entry_price_source_tag": "real_ask",
    "entry_price_band": [0.02, 0.98],   # L27/L249: a 1-tick move outside this is >50% relative
    "exit": "hold_to_settlement",
    "fee_legs": 1,
    "fee_side": "taker",
    "min_units": 10,                    # L41
    "min_exclusive_minority_units": 1,  # Q57 gate (2): ">= 1 opposing-sign unit"
    "n_boot": 10000,
    "seed": 42,
    "tick": 0.01,
    "min_ticks": 1.0,
}

MAX_ENTRY_LAG_S = float(PREREGISTRATION["max_entry_lag_minutes"]) * 60.0
FLOW_WINDOW_S = float(PREREGISTRATION["flow_window_minutes"]) * 60.0
MIN_ABS_RHO = float(PREREGISTRATION["min_abs_rho"])
MIN_WINDOW_COUNT = float(PREREGISTRATION["min_window_count"])
BAND_LO, BAND_HI = (float(x) for x in PREREGISTRATION["entry_price_band"])  # type: ignore[union-attr]
MIN_UNITS = int(PREREGISTRATION["min_units"])
MIN_MINORITY_UNITS = int(PREREGISTRATION["min_exclusive_minority_units"])
N_BOOT = int(PREREGISTRATION["n_boot"])
SEED = int(PREREGISTRATION["seed"])
TICK = float(PREREGISTRATION["tick"])
MIN_TICKS = float(PREREGISTRATION["min_ticks"])

# The fee side is TAKER: S82 CROSSES the spread to lift a resting ask. Imported from
# core.pricing, never spelled here (L5 — an S13 draft charged maker fills the taker rate,
# a 4x overcharge; the mirror error would UNDERcharge and manufacture an edge).
FEE_RATE = TAKER_FEE_RATE

# L279 orientation, imported rather than restated so this probe cannot drift from the
# corrected reading. On the committed tape `taker_book_side` and `taker_outcome_side` are
# perfectly collinear (only ("bid","yes") and ("ask","no") occur); `flow_orientation_audit`
# measures that rather than assuming it, so a future tape that decouples them is caught.
TAKER_BUYS = M.TAKER_BUYS      # "bid" — a taker whose own order sat on the bid is a BUYER
TAKER_SELLS = M.TAKER_SELLS    # "ask"

SIDE_YES = "yes"
SIDE_NO = "no"

# S79's sealed spec, restated here ONLY as the comparison target for Q57 gate (3). Values
# are read from the S79 module at import time where possible so this cannot drift.
S79_LOOKBACK_MINUTES = 30
S79_DECISION_GRID_MINUTES = 60
S79_ENTRY_PRICE_FAMILY = "kalshi_trades"
S79_ENTRY_PRICE_TAG = "broker_truth"
S82_ENTRY_PRICE_FAMILY = "orderbook_depth"
S82_ENTRY_PRICE_TAG = "real_ask"


def preregistration_sha256(spec: Optional[Dict[str, object]] = None) -> str:
    payload = json.dumps(spec if spec is not None else PREREGISTRATION,
                         sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


PREREG_SHA256 = preregistration_sha256()


# --------------------------------------------------------------------------- #
# loaders
# --------------------------------------------------------------------------- #
def game_id_of(ticker: str) -> str:
    """THE join key. `kalshi_trades.event_ticker` is null on every committed row; the game-id
    is the outcome-suffix-stripped ticker (`...-KIA` -> `...`). Spelled once, on purpose."""
    return ticker.rsplit("-", 1)[0]


def _iter_jsonl(paths: Sequence[Path]):
    for p in paths:
        with open(p, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    yield json.loads(line)


def load_prints(tape_dir: Path = TRADES_TAPE) -> Dict[str, List[dict]]:
    """ticker -> [{ts, side, count}] sorted by ts, sports `*GAME` moneylines only (L31)."""
    paths = sorted(Path(tape_dir).glob("dt=*.jsonl"))
    out: Dict[str, List[dict]] = defaultdict(list)
    for r in _iter_jsonl(paths):
        tk = r.get("ticker")
        if not isinstance(tk, str) or not M.is_sports_game_market(tk):
            continue
        out[tk].append({
            "ts": parse_iso_utc(r["created_time"]).timestamp(),
            "side": r.get("taker_outcome_side"),
            "book_side": r.get("taker_book_side"),
            "count": float(r.get("count") or 0.0),   # L47: fractional counts are valid data
        })
    for tk in out:
        out[tk].sort(key=lambda d: d["ts"])
    return dict(out)


def load_depth(tickers: FrozenSet[str], tape_dir: Path = DEPTH_TAPE
               ) -> Dict[str, List[dict]]:
    """ticker -> [{ts, best_yes_ask, best_no_ask, captured_at}] sorted, for `tickers` only."""
    paths = sorted(Path(tape_dir).glob("dt=*.jsonl"))
    out: Dict[str, List[dict]] = defaultdict(list)
    for r in _iter_jsonl(paths):
        tk = r.get("ticker")
        if tk not in tickers:
            continue
        tags = r.get("price_source_tags") or {}
        if tags.get("asks") != S82_ENTRY_PRICE_TAG:
            continue      # never score a price whose own tape does not call it a real ask
        out[tk].append({
            "ts": parse_iso_utc(r["captured_at"]).timestamp(),
            "captured_at": r["captured_at"],
            "best_yes_ask": r.get("best_yes_ask"),
            "best_no_ask": r.get("best_no_ask"),
        })
    for tk in out:
        out[tk].sort(key=lambda d: d["ts"])
    return dict(out)


def load_close_times(tickers: FrozenSet[str], tape_dir: Path = LEDGER_TAPE
                     ) -> Tuple[Dict[str, float], int]:
    """ticker -> earliest recorded close epoch, plus the max count of DISTINCT close_time
    strings seen for any one ticker (the L360/L361 mutation exposure, reported not assumed)."""
    paths = sorted(Path(tape_dir).glob("dt=*.jsonl"))
    seen: Dict[str, set] = defaultdict(set)
    for r in _iter_jsonl(paths):
        tk = r.get("ticker")
        if tk in tickers and r.get("close_time"):
            seen[tk].add(r["close_time"])
    out = {tk: min(parse_iso_utc(v).timestamp() for v in vals) for tk, vals in seen.items()}
    return out, (max((len(v) for v in seen.values()), default=0))


def close_time_cross_family_audit(tickers: FrozenSet[str],
                                  root: Path = REPO_ROOT) -> dict:
    """L360/L361 anchor-realism check, ACROSS families — `load_close_times` cannot do it.

    `load_close_times` reads only `tape/settlement_ledger/`, whose two committed day-files
    are both POST-settlement, so it can never see the pre-settlement value and its
    `close_time_distinct_values_max` reads 1 (no mutation) for a structural reason, not an
    empirical one. `tape/q51_settlement_cache/` holds the same tickers captured at different
    moments including a pre-settlement one, so the mutation IS observable there. Reported so
    the probe's own mutation check is not over-read as evidence of a stable anchor."""
    per: Dict[str, set] = defaultdict(set)
    for path in sorted(Path(root).glob("tape/q51_settlement_cache/*.json")):
        with open(path, "r", encoding="utf-8") as fh:
            blob = json.load(fh)
        markets = blob.get("markets") or {}
        rows = markets.values() if isinstance(markets, dict) else markets
        keys = list(markets) if isinstance(markets, dict) else [None] * len(rows)
        for tk_key, m in zip(keys, rows):
            if not isinstance(m, dict):
                continue
            tk = tk_key or m.get("ticker")
            ct = m.get("close_time")
            if tk and ct:
                per[tk].add(ct)
    mutated = {k: sorted(v) for k, v in per.items() if len(v) > 1}
    return {
        "family": "q51_settlement_cache",
        "n_tickers_seen": len(per),
        "n_with_multiple_close_times": len(mutated),
        "example": (sorted(mutated.items())[0] if mutated else None),
        "note": ("close_time IS rewritten across captures (L360/L361, always EARLIER). The "
                 "settlement_ledger-only check in `substrate` cannot see this and must not "
                 "be read as evidence that the entry anchor was knowable ex ante."),
    }


# --------------------------------------------------------------------------- #
# signal — outcome-independent by construction
# --------------------------------------------------------------------------- #
def flow_orientation_audit(prints: Dict[str, List[dict]]) -> dict:
    """Measure, never assume, that `taker_book_side` and `taker_outcome_side` agree (L279).

    `("bid","yes")` and `("ask","no")` are the only pairs the committed tape exhibits, so the
    two readings of the sign are identical. If a future tape decouples them this reports the
    off-diagonal counts and the caller must decide which field is authoritative."""
    combos: Dict[str, int] = defaultdict(int)
    for rows in prints.values():
        for pr in rows:
            combos[f"{pr['book_side']}|{pr['side']}"] += 1
    agree = combos.get(f"{TAKER_BUYS}|{SIDE_YES}", 0) + combos.get(f"{TAKER_SELLS}|{SIDE_NO}", 0)
    total = sum(combos.values())
    return {"combos": dict(sorted(combos.items())), "n_prints": total,
            "n_orientation_agreeing": agree,
            "collinear": total > 0 and agree == total}


def window_flow(rows: Sequence[dict], t_end: float, *,
                window_s: float = FLOW_WINDOW_S) -> Tuple[float, float, int]:
    """(net_signed_count, total_count, n_prints) over (t_end - window_s, t_end].

    `+count` when the taker BUYS yes, `-count` when the taker buys no (equivalently sells
    yes). Sizes stay FLOAT (L47). The window ENDS at the entry instant: no print after the
    fill can inform the signal."""
    lo = t_end - window_s
    net = tot = 0.0
    n = 0
    for pr in rows:
        if pr["ts"] <= lo:
            continue
        if pr["ts"] > t_end:
            break
        c = pr["count"]
        if pr["side"] == SIDE_YES:
            net += c
        elif pr["side"] == SIDE_NO:
            net -= c
        else:
            continue
        tot += c
        n += 1
    return net, tot, n


def entry_candidates(prints: Dict[str, List[dict]],
                     depth: Dict[str, List[dict]],
                     closes: Dict[str, float],
                     *,
                     window_s: float = FLOW_WINDOW_S,
                     min_abs_rho: float = MIN_ABS_RHO,
                     min_window_count: float = MIN_WINDOW_COUNT,
                     max_entry_lag_s: float = MAX_ENTRY_LAG_S,
                     ) -> Tuple[List[dict], Dict[str, int]]:
    """One candidate per TICKER (collapsed to one per GAME later). Outcome-blind.

    The four spec constants are THREADED as explicit keyword arguments, never read from
    module globals at call time. `sign_variation_sensitivity` sweeps them, and a global
    that is also spelled as another function's DEFAULT ARGUMENT is bound once at def-time —
    rebinding the module global would then sweep nothing while looking like it swept
    everything (this exact defect was caught by `scripts/q57_s82_rederive.py`, which found
    4 sign-variation-passing cells where the sweep reported 0)."""
    drops: Dict[str, int] = defaultdict(int)
    rows: List[dict] = []
    for tk in sorted(prints):
        close = closes.get(tk)
        if close is None:
            drops["no_close_time"] += 1
            continue
        snaps = [s for s in depth.get(tk, []) if s["ts"] <= close]
        if not snaps:
            drops["no_depth_snapshot_at_or_before_close"] += 1
            continue
        snap = snaps[-1]
        lag_s = close - snap["ts"]
        if lag_s > max_entry_lag_s:
            drops["entry_snapshot_too_stale"] += 1
            continue
        net, tot, n = window_flow(prints[tk], snap["ts"], window_s=window_s)
        if n == 0 or tot <= 0.0:
            drops["no_prints_in_flow_window"] += 1
            continue
        if tot < min_window_count:
            drops["window_count_below_floor"] += 1
            continue
        rho = net / tot
        if abs(rho) < min_abs_rho:
            drops["flow_not_extreme"] += 1
            continue
        fade = SIDE_NO if rho > 0 else SIDE_YES
        ask = snap["best_no_ask"] if fade == SIDE_NO else snap["best_yes_ask"]
        if ask is None or not is_fillable_ask(ask):
            drops["fade_side_ask_absent"] += 1       # one-sided book (L23)
            continue
        ask = float(ask)
        if not (BAND_LO <= ask <= BAND_HI):
            drops["entry_ask_outside_price_band"] += 1
            continue
        other = snap["best_yes_ask"] if fade == SIDE_NO else snap["best_no_ask"]
        rows.append({
            "game": game_id_of(tk),
            "ticker": tk,
            "entry_ts": snap["ts"],
            "entry_captured_at": snap["captured_at"],
            "entry_lag_minutes": round(lag_s / 60.0, 2),
            "rho": rho,
            "net_count": net,
            "total_count": tot,
            "n_prints_in_window": n,
            "fade_side": fade,
            "entry_ask": ask,
            "price_source_tag": S82_ENTRY_PRICE_TAG,
            "opposite_side_ask": (float(other) if other is not None else None),
            "overround": (round(ask + float(other) - 1.0, 6) if other is not None else None),
        })
    return rows, dict(drops)


def collapse_to_games(rows: Sequence[dict]) -> List[dict]:
    """One entry per GAME (L6): the game's ticker with the largest |rho|; ties -> min ticker.

    Without this a 3-way soccer game contributes home/away/tie legs to one bootstrap block
    AND to the pooled mean — the within-game complementary-outcome trap Q57's unit rule
    exists to forbid."""
    best: Dict[str, dict] = {}
    for r in rows:
        cur = best.get(r["game"])
        # sort key: larger |rho| wins; on an exact tie the SMALLER ticker wins (so the
        # comparison puts the incumbent's ticker on the left of the challenger's).
        if cur is None or (abs(r["rho"]), cur["ticker"]) > (abs(cur["rho"]), r["ticker"]):
            best[r["game"]] = r
    return [best[g] for g in sorted(best)]


def minority_arm_fillability(prints: Dict[str, List[dict]],
                             depth: Dict[str, List[dict]],
                             closes: Dict[str, float]) -> dict:
    """WHY the minority (fade-to-YES) arm is empty — outcome-blind, no filters applied.

    Enumerates every ticker that has a close_time and a pre-close depth snapshot, with NO
    rho / count / lag / band gate, and reports the fade-side ask distribution split by the
    sign of rho. Two distinct walls are separated here on purpose:

      * FREQUENCY — how often net flow is negative at all (L279's retail-buy asymmetry), and
      * FILLABILITY — of the negative-flow cases, how many have a fade-side (YES) ask that is
        absent (one-sided book, L23) or pinned at the 1-cent tick floor (L26/L249).

    They are not the same objection, and a reader who sees only the first will wrongly
    conclude that more tape fixes it."""
    buckets: Dict[str, Dict[str, int]] = {
        "negative_flow_fade_to_yes": defaultdict(int),
        "positive_flow_fade_to_no": defaultdict(int),
    }
    for tk in sorted(prints):
        close = closes.get(tk)
        if close is None:
            continue
        snaps = [s for s in depth.get(tk, []) if s["ts"] <= close]
        if not snaps:
            continue
        snap = snaps[-1]
        net, tot, n = window_flow(prints[tk], snap["ts"], window_s=FLOW_WINDOW_S)
        if n == 0 or tot <= 0.0:
            continue
        rho = net / tot
        if rho == 0.0:
            continue
        key = "positive_flow_fade_to_no" if rho > 0 else "negative_flow_fade_to_yes"
        ask = snap["best_no_ask"] if rho > 0 else snap["best_yes_ask"]
        b = buckets[key]
        b["n"] += 1
        if ask is None:
            b["ask_absent_one_sided_book"] += 1
        elif float(ask) <= BAND_LO - 0.005:
            b["ask_pinned_at_tick_floor"] += 1
        elif BAND_LO <= float(ask) <= BAND_HI:
            b["ask_in_price_band"] += 1
        else:
            b["ask_above_band"] += 1
    out = {k: dict(sorted(v.items())) for k, v in buckets.items()}
    neg = out["negative_flow_fade_to_yes"]
    pos = out["positive_flow_fade_to_no"]
    tot_n = neg.get("n", 0) + pos.get("n", 0)
    out["negative_flow_share"] = (round(neg.get("n", 0) / tot_n, 4) if tot_n else None)
    out["minority_arm_fillable_count"] = neg.get("ask_in_price_band", 0)
    return out


# --------------------------------------------------------------------------- #
# OUTCOME-BLIND sensitivity: is the sign-variation hole structural or spec-specific?
# --------------------------------------------------------------------------- #
# A single pre-registered cell that fails the L312/L321 sign-variation gate could be an
# artifact of the four constants above rather than a property of the tape. This grid answers
# that question WITHOUT reading a single outcome value — it reports only population SHAPE
# (unit counts and side counts), never a return, so it costs no multiplicity and cannot
# tune the spec toward a result. The pre-registered cell stays the verdict cell regardless
# of what the grid shows; the grid is evidence about GENERALITY, not a search for a survivor.
SENSITIVITY_GRID: Dict[str, Sequence[float]] = {
    "flow_window_minutes": (30.0, 60.0, 120.0, 240.0, 480.0),
    "min_abs_rho": (0.05, 0.10, 0.20, 0.40),
    "min_window_count": (0.0, 100.0, 1000.0),
    "max_entry_lag_minutes": (30.0, 60.0, 240.0, 4320.0),
}


def sign_variation_sensitivity(prints: Dict[str, List[dict]],
                               depth: Dict[str, List[dict]],
                               closes: Dict[str, float],
                               settled_of) -> dict:
    """Sweep the four pre-registered constants and report, per cell, the GAME-unit count and
    the per-side unit counts. Outcome-blind: `settled_of` is a membership predicate over the
    LABEL CLASS (settled-binary yes/no), never a result value.

    The sweep passes each cell's constants EXPLICITLY into `entry_candidates`; it never
    rebinds a module global (see that function's docstring for the defect this avoids)."""
    cells: List[dict] = []
    for w in SENSITIVITY_GRID["flow_window_minutes"]:
        for rho in SENSITIVITY_GRID["min_abs_rho"]:
            for mc in SENSITIVITY_GRID["min_window_count"]:
                for lag in SENSITIVITY_GRID["max_entry_lag_minutes"]:
                    cand, _ = entry_candidates(
                        prints, depth, closes,
                        window_s=w * 60.0, min_abs_rho=rho,
                        min_window_count=mc, max_entry_lag_s=lag * 60.0)
                    rows = [r for r in collapse_to_games(cand) if settled_of(r["ticker"])]
                    sides: Dict[str, List[str]] = defaultdict(list)
                    for r in rows:
                        sides[r["game"]].append(r["fade_side"])
                    cen = sign_variation_admissible(
                        sides, min_exclusive_minority_units=MIN_MINORITY_UNITS,
                        sides=(SIDE_YES, SIDE_NO))["census"]
                    cells.append({
                        "flow_window_minutes": w, "min_abs_rho": rho,
                        "min_window_count": mc, "max_entry_lag_minutes": lag,
                        "n_game_units": len(rows),
                        "units_per_side": cen["units_per_side"],
                        "minority_exclusive": cen["minority_side_units_exclusive"],
                    })
    adequate = [c for c in cells if c["n_game_units"] >= MIN_UNITS]
    passing = [c for c in adequate if c["minority_exclusive"] >= MIN_MINORITY_UNITS]
    return {
        "n_cells": len(cells),
        "n_cells_meeting_unit_floor": len(adequate),
        "n_cells_meeting_unit_floor_and_sign_variation": len(passing),
        "max_minority_exclusive_over_all_cells": max((c["minority_exclusive"] for c in cells),
                                                     default=0),
        "max_units_over_all_cells": max((c["n_game_units"] for c in cells), default=0),
        "cells_passing_sign_variation": [
            {k: c[k] for k in ("flow_window_minutes", "min_abs_rho", "min_window_count",
                               "max_entry_lag_minutes", "n_game_units", "units_per_side")}
            for c in passing],
        "cells": cells,
    }


# --------------------------------------------------------------------------- #
# Q57 gate (3) — the L51 differentiation proof, run BEFORE any outcome is read
# --------------------------------------------------------------------------- #
def l51_differentiation(rows: Sequence[dict]) -> dict:
    """Prove S82's window/entry surface differs from S79's, outcome-blind (Q57 gate 3).

    L51: on a two-way market a FADE and a FOLLOW are mechanically complementary. If S82's
    entries were S79's entries with the sign flipped — same instants, same price surface —
    then S82's CI would be S79's CI negated and the measurement would carry no independent
    information. Four differences are reported as NUMBERS, not assertions:

      * `window_minutes`      120 vs 30 (a 4x wider aggregation window),
      * `decision_rule`       one close-anchored instant per game vs an hourly grid,
      * `entry_price_family`  `orderbook_depth`/`real_ask` vs `kalshi_trades`/`broker_truth`
                              — DISJOINT tapes, so no entry price can coincide,
      * `signal_statistic`    scale-free `rho` ratio vs an absolute contract threshold.

    VOID condition: the entry price surface is shared AND the decision rule is identical.
    Anything less is a genuinely different population and the probe may proceed."""
    same_price_surface = (S82_ENTRY_PRICE_FAMILY == S79_ENTRY_PRICE_FAMILY)
    same_decision_rule = False   # close-anchored, one per game vs hourly grid: never equal
    voided = bool(same_price_surface and same_decision_rule)
    return {
        "voided": voided,
        "s82_window_minutes": int(PREREGISTRATION["flow_window_minutes"]),
        "s79_window_minutes": S79_LOOKBACK_MINUTES,
        "window_ratio": float(PREREGISTRATION["flow_window_minutes"]) / S79_LOOKBACK_MINUTES,
        "s82_decision_rule": PREREGISTRATION["entry_instant_rule"],
        "s79_decision_rule": f"every_{S79_DECISION_GRID_MINUTES}min_utc_grid_instant",
        "s82_entry_price_family": S82_ENTRY_PRICE_FAMILY,
        "s82_entry_price_tag": S82_ENTRY_PRICE_TAG,
        "s79_entry_price_family": S79_ENTRY_PRICE_FAMILY,
        "s79_entry_price_tag": S79_ENTRY_PRICE_TAG,
        "entry_price_surfaces_disjoint": not same_price_surface,
        "s82_signal_statistic": "scale_free_ratio",
        "s79_signal_statistic": "absolute_contract_threshold",
        "s82_direction": "FADE",
        "s79_direction": "FOLLOW",
        "n_s82_entries": len(rows),
        "n_s82_distinct_entry_instants": len({r["entry_captured_at"] for r in rows}),
        "note": ("S82's entry prices are read from a family S79 never touches, so no entry "
                 "price is shared and the two populations cannot be sign-negations of each "
                 "other. The mechanisms remain complementary in SIGN; the measurements are "
                 "not the same measurement."),
    }


# --------------------------------------------------------------------------- #
# outcome-blind population report
# --------------------------------------------------------------------------- #
def settled_ticker_set(tickers: Sequence[str], root: str = DEFAULT_TAPE_ROOT
                       ) -> Tuple[FrozenSet[str], dict]:
    """OUTCOME-BLIND settlement membership: WHICH tickers settled binary, never HOW.

    Scans every declared source (L300 — nine families, not `settlement_ledger` alone)."""
    rep = resolve_market_results(tickers, root=root)
    settled = frozenset(t for t, m in rep.resolved.items() if is_binary_result(m.result))
    return settled, {
        "n_requested": rep.requested,
        "n_settled_binary": len(settled),
        "n_non_binary": len(rep.non_binary),
        "n_listed_unsettled": len(rep.listed_unsettled),
        "n_unresolved": len(rep.unresolved),
        "per_source_hits": dict(sorted(rep.per_source_hits.items())),
        "sources_scanned": list(rep.sources_scanned),
        "sources_absent_on_disk": list(rep.sources_absent_on_disk),
    }


def population_report(rows: Sequence[dict], settled: FrozenSet[str]) -> dict:
    """Adequacy WITHOUT any outcome value. `scoreable` = entries on a settled ticker."""
    scoreable = [r for r in rows if r["ticker"] in settled]
    sides: Dict[str, List[str]] = defaultdict(list)
    for r in scoreable:
        sides[r["game"]].append(r["fade_side"])
    sv = sign_variation_admissible(sides,
                                   min_exclusive_minority_units=MIN_MINORITY_UNITS,
                                   sides=(SIDE_YES, SIDE_NO))
    conc = entry_instant_concentration([r["entry_captured_at"] for r in scoreable],
                                       unit_labels=[r["game"] for r in scoreable])
    n_units = len({r["game"] for r in scoreable})
    overrounds = [r["overround"] for r in scoreable if r["overround"] is not None]
    return {
        "n_entries_all": len(rows),
        "n_entries_scoreable": len(scoreable),
        "n_game_units": n_units,
        "min_units": MIN_UNITS,
        "meets_unit_floor": n_units >= MIN_UNITS,
        "sign_variation": sv,
        "entry_instant_concentration": conc,
        "n_overround_measurable": len(overrounds),
        "mean_overround": (round(sum(overrounds) / len(overrounds), 6) if overrounds else None),
        "admissible": bool(n_units >= MIN_UNITS and sv["admissible"]),
    }


# --------------------------------------------------------------------------- #
# scoring — reachable only after the adequacy gate
# --------------------------------------------------------------------------- #
def outcome_map(tickers: Sequence[str], root: str = DEFAULT_TAPE_ROOT) -> Dict[str, int]:
    """ticker -> 1 (yes settled) / 0 (no settled). THE ONLY reader of an outcome VALUE.
    Non-binary/unknown results are DROPPED, never scored as a loss (L52)."""
    rep = resolve_market_results(tickers, root=root)
    out: Dict[str, int] = {}
    for t, m in rep.resolved.items():
        o = binary_outcome(m.result)
        if o is not None:
            out[t] = o
    return out


def score_rows(rows: Sequence[dict], outcomes: Dict[str, int]) -> List[dict]:
    """Per-contract net P&L: payout - entry_ask - ONE taker fee. Payout is $1 when the FADED
    side is the side that settled, else $0."""
    scored: List[dict] = []
    for r in rows:
        o = outcomes.get(r["ticker"])
        if o is None:
            continue
        won = (o == 1) if r["fade_side"] == SIDE_YES else (o == 0)
        fee = fee_per_contract(r["entry_ask"], FEE_RATE)
        pnl = (1.0 if won else 0.0) - r["entry_ask"] - fee
        s = dict(r)
        s.update({"settled_yes": o, "fade_won": bool(won), "fee": fee,
                  "pnl": round(pnl, 6), "price_source_tag": S82_ENTRY_PRICE_TAG})
        scored.append(s)
    return scored


def unit_values(scored: Sequence[dict]) -> Dict[str, List[float]]:
    out: Dict[str, List[float]] = defaultdict(list)
    for s in scored:
        out[s["game"]].append(s["pnl"])
    return dict(out)


# --------------------------------------------------------------------------- #
def run(trades_dir: Path = TRADES_TAPE, depth_dir: Path = DEPTH_TAPE,
        ledger_dir: Path = LEDGER_TAPE, settlement_root: str = DEFAULT_TAPE_ROOT) -> dict:
    prints = load_prints(trades_dir)
    tickers = frozenset(prints)
    depth = load_depth(tickers, depth_dir)
    closes, close_distinct_max = load_close_times(tickers, ledger_dir)
    orientation = flow_orientation_audit(prints)
    anchor_audit = close_time_cross_family_audit(tickers)

    cand, drops = entry_candidates(prints, depth, closes)
    rows = collapse_to_games(cand)

    rep: dict = {
        "probe": "q57_s82_flow_fade",
        "strategy": "S82",
        "queue_item": "Q57",
        "preregistration": PREREGISTRATION,
        "preregistration_sha256": PREREG_SHA256,
        "fee_rate": FEE_RATE,
        "substrate": {
            "n_trade_tickers": len(tickers),
            "n_trade_games": len({game_id_of(t) for t in tickers}),
            "n_tickers_with_depth": len(depth),
            "n_tickers_with_close_time": len(closes),
            "close_time_distinct_values_max": close_distinct_max,
            "close_time_mutation_observed": close_distinct_max > 1,
        },
        "flow_orientation_audit": orientation,
        "close_time_cross_family_audit": anchor_audit,
        "entry_drops": drops,
        "n_ticker_candidates": len(cand),
        "n_game_entries": len(rows),
    }

    # ── Q57 gate (3): differentiate from S79 BEFORE any outcome is read ──────────────
    diff = l51_differentiation(rows)
    rep["l51_differentiation"] = diff
    if diff["voided"]:
        rep["verdict"] = "VOID"
        rep["note"] = ("L51: S82's population is S79's with the sign flipped — the "
                       "measurement carries no independent information. Not scored.")
        return rep

    settled_all, coverage = settled_ticker_set(sorted(tickers), root=settlement_root)
    rep["settlement_coverage"] = coverage
    pop = population_report(rows, settled_all)
    rep["population"] = pop
    rep["sign_variation_sensitivity"] = sign_variation_sensitivity(
        prints, depth, closes, lambda t: t in settled_all)
    rep["minority_arm_fillability"] = minority_arm_fillability(prints, depth, closes)

    if not pop["admissible"]:
        rep["verdict"] = "INSUFFICIENT DATA"
        reasons = []
        if not pop["meets_unit_floor"]:
            reasons.append(f"{pop['n_game_units']} game units < L41 floor {MIN_UNITS}")
        if not pop["sign_variation"]["admissible"]:
            reasons.append("sign-variation gate (L312/L321): "
                           + ",".join(pop["sign_variation"]["reasons"]))
        rep["note"] = ("POPULATION-INADEQUATE — no CI computed, no outcome value read. "
                       + "; ".join(reasons))
        return rep

    scoreable = [r for r in rows if r["ticker"] in settled_all]
    outcomes = outcome_map(sorted({r["ticker"] for r in scoreable}), root=settlement_root)
    scored = score_rows(scoreable, outcomes)
    uv = unit_values(scored)
    boot = block_bootstrap(uv, n_boot=N_BOOT, seed=SEED)
    adm = bootstrap_verdict_admissible(uv, min_units=MIN_UNITS)
    kish = kish_effective_n([len(v) for v in uv.values()])
    clears = clears_tick_magnitude(boot["ci95"], tick=TICK, min_ticks=MIN_TICKS)

    rep["scored"] = [
        {k: s[k] for k in ("game", "ticker", "entry_captured_at", "entry_lag_minutes",
                           "rho", "total_count", "fade_side", "entry_ask", "overround",
                           "fee", "settled_yes", "fade_won", "pnl", "price_source_tag")}
        for s in scored
    ]
    rep["bootstrap"] = boot
    rep["admissibility"] = adm
    rep["kish_effective_n"] = kish
    rep["clears_tick_magnitude"] = clears
    rep["n_fade_wins"] = sum(1 for s in scored if s["fade_won"])
    alive = bool(adm["admissible"] and boot["ci95"][0] is not None
                 and boot["ci95"][0] > 0.0 and clears)
    rep["verdict"] = "ALIVE" if alive else "DEAD"
    rep["note"] = ("CI strictly > 0 net of one taker fee AND clears the L27 tick gate."
                   if alive else
                   "CI does not clear the real-ask bar (>0 net of fee AND >= 1 tick, L27/L41).")
    return rep


def _fmt_human(rep: dict) -> str:
    L = [f"Q57 / S82 — game-level signed-taker-flow FADE taker  [{rep['verdict']}]",
         f"  prereg sha256   {rep['preregistration_sha256'][:16]}…",
         f"  substrate       {rep['substrate']['n_trade_games']} traded games / "
         f"{rep['substrate']['n_tickers_with_close_time']} tickers with close_time",
         f"  entries         {rep['n_ticker_candidates']} ticker → {rep['n_game_entries']} game",
         f"  entry drops     {rep['entry_drops']}"]
    if "population" in rep:
        p = rep["population"]
        L.append(f"  scoreable       {p['n_entries_scoreable']} entries / "
                 f"{p['n_game_units']} game units (floor {p['min_units']})")
        sv = p["sign_variation"]["census"]
        L.append(f"  sides           {sv['units_per_side']} exclusive-minority="
                 f"{sv['minority_side_units_exclusive']} (floor {MIN_MINORITY_UNITS})")
        L.append(f"  mean overround  {p['mean_overround']}")
    if "sign_variation_sensitivity" in rep:
        sv = rep["sign_variation_sensitivity"]
        L.append(f"  sensitivity     {sv['n_cells']} outcome-blind cells; "
                 f"{sv['n_cells_meeting_unit_floor']} meet the unit floor; "
                 f"{sv['n_cells_meeting_unit_floor_and_sign_variation']} ALSO clear "
                 f"sign-variation; max exclusive-minority units anywhere = "
                 f"{sv['max_minority_exclusive_over_all_cells']}")
    if "minority_arm_fillability" in rep:
        m = rep["minority_arm_fillability"]
        L.append(f"  minority arm    negative-flow share {m['negative_flow_share']}; "
                 f"of those, fillable-in-band = {m['minority_arm_fillable_count']}  "
                 f"({m['negative_flow_fade_to_yes']})")
    if "bootstrap" in rep:
        b = rep["bootstrap"]
        L.append(f"  block bootstrap mean ${b['mean']:+.4f} 95% CI "
                 f"[{b['ci95'][0]:+.4f}, {b['ci95'][1]:+.4f}]  "
                 f"n_units={b['n_units']} n_obs={b['n_obs']}")
        L.append(f"  kish eff n      {rep['kish_effective_n']['kish_n']}")
        L.append(f"  admissible={rep['admissibility']['admissible']} "
                 f"clears_tick={rep['clears_tick_magnitude']} "
                 f"fade wins {rep['n_fade_wins']}/{b['n_obs']}")
    L.append(f"  {rep.get('note', '')}")
    return "\n".join(L)


def main(argv: Optional[Sequence[str]] = None) -> int:
    rep = run()
    os.makedirs(REPORT_PATH.parent, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(_fmt_human(rep))
    print(f"\nwrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
