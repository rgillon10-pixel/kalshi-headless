"""q50_s68_gate_ladder — S68 both-bid maker capture re-derived on a TIGHTER admission gate.

WHAT THIS IS AND WHY IT EXISTS
------------------------------
Q49 (`scripts/q49_s68_bothside_maker_fillsim.py`,
`findings/2026-08-01-q49-s68-bothside-maker-fillsim-verdict.md`) returned **DEAD** for S68
(rest BOTH a YES bid and a NO bid on a wide-spread two-sided game moneyline; if both fill you
own both sides for `yes_bid + no_bid` < $1 and exactly one side pays $1). That verdict was
verifier-CONFIRMED, and it stands. But it left TWO explicitly-owed follow-ups, filed the same
day as UNENFORCED lessons:

* **L252** — Q49's admission gate was ``yes-spread >= fee(yes_bid) + fee(no_bid)``. On a
  mirrored binary book (``best_yes_ask == 1 - best_no_bid`` by collector construction,
  ``collection/normalize.py``) that gate is IDENTICAL to "gross capture >= the two fees", so at
  the realistic population it admits books sitting almost exactly on the ZERO-PROFIT BOUNDARY.
  Q49's 11 double fills all netted between $0.0000 and one cent — the gate's own boundary, not
  a sampled range around it. L252's candidate enforcement: such a design "should set its
  admission gate at fees-plus-N-ticks (not fees exactly) and re-derive the resulting population
  size/economics under that tighter gate before treating a fee-boundary result as informative."
  **This module is that re-derivation.**
* **L251** — Q49's primary cut selected the ticker's EARLIEST pre-close snapshot and then
  filtered to ``ttc <= 24h``. On a young tape that silently selects on TAPE START DATE: all 20
  Q49 candidates shared ONE ``entry_captured_at`` (the depth tape's first-ever capture pass).
  The honest at-T-minus-H rule is "**first snapshot with ttc <= H**". **This module uses that
  rule** and PUBLISHES the distinct-entry-timestamp count per cell so the artifact is visible
  rather than inferred.

THE QUESTION (falsifiable, one binding test)
--------------------------------------------
Over ``tape/orderbook_depth/`` (queue ladders, ``real_bid``) joined ex-post (L50) to
``tape/settlement_ledger/`` (``broker_truth``), under the L251 entry rule and the gate

    yes_spread >= fee(yes_bid) + fee(no_bid) + N * $0.01     for N in {0, 1, 2, 3, 5}

does the S68 both-bid capture produce a block-bootstrapped-by-GAME-SERIES 95% CI **strictly
> 0**, net of both maker fees, on a population clearing the L41 >=10-unit floor AND the L27
``clears_tick_magnitude`` gate?  N=0 reproduces the Q49 gate and is the sanity anchor.

WHICH OBJECT IS BOOTSTRAPPED (L249 — load-bearing)
--------------------------------------------------
The **strategy-level** P&L: every rested both-bid pair contributes — a double fill books the
realized net capture, a single-side fill books the UNHEDGED directional position you are
actually left holding (marked to ``broker_truth`` settlement), a no-fill books 0. That object
is non-degenerate.

The double-fill-only P&L is reported too, but it is **SIGN-BOUNDED BY CONSTRUCTION** (L249): the
entry gate arithmetically guarantees gross capture >= the two fees, so its net can never be
negative, no resample can ever produce an opposing-sign cluster, and its ``admissible=False``
is a property of the GATE, not information about the strategy. It is a DIAGNOSTIC here and is
never the verdict — that is precisely the reporting error L249 was filed to prevent.

FILL MODEL (L250)
-----------------
``touch`` (departures at OUR own price level, only while we are at the touch) is PRIMARY. The
``turnover`` rule (departures at any level >= our price) SATURATES on a multi-day hold — 98%
"fill rate" in Q49 — and is a labeled diagnostic only. A high turnover fill rate is not a fill.

DISCIPLINE
----------
Read-only over committed tape. No network. Imports nothing from ``execution/``. No order verbs.
Fees ONLY via ``core.pricing.fee_per_contract`` at ``MAKER_FEE_RATE`` (L18/L30). Bootstrap unit
= GAME-SERIES (L6/L41), routed through ``bootstrap_verdict_admissible`` + ``clears_tick_magnitude``.
All fill/queue prices ``real_bid``; settlement ``broker_truth``; no synthetic price is ever a fill.

Every simulation primitive (queue accounting, both fill models, both P&L branches, tape
loading) is IMPORTED from the Q49 module rather than re-implemented — Q49's code is already
verifier-CONFIRMED, and a second copy would be a second thing to get wrong. What is new here is
only the ENTRY RULE and the GATE.

CLI (direct form is load-bearing per L232 — a repo-root conftest.py masks broken cross-script
imports under pytest, so a green suite does not prove the CLI works)::

    python3 scripts/q50_s68_gate_ladder.py
    python3 scripts/q50_s68_gate_ladder.py --gate-ticks 0,1,2,3,5 --horizons 24,6
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.io import REPO_ROOT  # noqa: E402
from scripts.q49_s68_bothside_maker_fillsim import (  # noqa: E402
    DEPTH_GLOB, MIN_CI_UNITS, PRICE_TICK, SETTLEMENT_GLOB, analyze_cut,
    best_bid_of, both_fill_pnl, build_trades, load_preclose_snapshots,
    load_settlements, maker_fee, queue_ahead_at, simulate_leg_fill,
    simulate_leg_fill_touch, single_side_pnl, touch_departures_between,
    two_sided_wide_entry,
)
from core.depth import capturable_depth, lottery_tail_fraction  # noqa: E402
from core.settlement import require_binary_result  # noqa: E402

_EPS = 1e-9

DEFAULT_GATE_TICKS: Tuple[int, ...] = (0, 1, 2, 3, 5)
DEFAULT_HORIZONS_H: Tuple[float, ...] = (6.0, 12.0, 18.0, 24.0, 36.0, 48.0, 72.0)
PRIMARY_FILL_MODEL = "touch"

#: L251 artifact flag — a population whose entries cluster on fewer than this many distinct
#: capture instants is a TAPE-START artifact, not a temporal near-close sample.
MIN_DISTINCT_ENTRY_TS = 3

ROWS_OUT = REPO_ROOT / "reports" / "q50_s68_gate_ladder_rows.jsonl"
SUMMARY_OUT = REPO_ROOT / "reports" / "q50_s68_gate_ladder_summary.json"


# --------------------------------------------------------------------------- #
# The two NEW pieces: the L251 entry rule and the L252 fees-plus-N-ticks gate
# --------------------------------------------------------------------------- #
def select_entry_index(snaps: Sequence[dict], horizon_hours: Optional[float]) -> Optional[int]:
    """L251's honest at-T-minus-H entry: the index of the FIRST snapshot whose time-to-close is
    <= `horizon_hours` (snapshots are already sorted ascending by capture time, so this is a
    genuine "we arrive at T-minus-H" entry).

    This is NOT "earliest snapshot, then filter ttc <= H": that form keeps the ticker's very
    first capture and merely discards tickers whose first capture was too early, which on a
    young tape selects on TAPE START DATE (Q49's 20 candidates all shared one capture instant).

    `horizon_hours=None` means "no horizon" -> the earliest pre-close snapshot (index 0), i.e.
    the Q49 unrestricted behaviour, kept so the ladder has an anchor. Returns None when no
    snapshot satisfies the horizon."""
    if horizon_hours is None:
        return 0 if snaps else None
    for i, s in enumerate(snaps):
        if float(s["ttc_hours"]) <= float(horizon_hours) + _EPS:
            return i
    return None


def gate_with_ticks(yes_bid: Optional[float], no_bid: Optional[float],
                    yes_offer: Optional[float], extra_ticks: int,
                    tick: float = PRICE_TICK) -> Dict[str, Any]:
    """L252's gate: Q49's two-sided wide-entry test, then the STRICTLY TIGHTER requirement

        spread >= fee_yes + fee_no + extra_ticks * tick

    `extra_ticks == 0` is exactly Q49's gate (verified by test). Returns Q49's dict shape with
    two extra keys: `extra_ticks` and `required_spread`. A book failing only the tick margin
    reports reason `spread_below_fees_plus_ticks` so the population decay is attributable."""
    if extra_ticks < 0:
        raise ValueError(f"extra_ticks must be >= 0 (got {extra_ticks})")
    out = dict(two_sided_wide_entry(yes_bid, no_bid, yes_offer))
    out["extra_ticks"] = int(extra_ticks)
    out["required_spread"] = None
    if out["fee_total"] is None:
        return out
    required = float(out["fee_total"]) + float(extra_ticks) * float(tick)
    out["required_spread"] = required
    if not out["eligible"]:
        return out
    if float(out["spread"]) < required - _EPS:
        out["eligible"] = False
        out["reason"] = "spread_below_fees_plus_ticks"
    return out


# --------------------------------------------------------------------------- #
# Adverse-selection instrumentation (the term Q49's own spec required and no probe
# in this repo has ever charged) — L253
# --------------------------------------------------------------------------- #
def touch_fill_index(ladders: Sequence[Optional[Sequence[Sequence[float]]]],
                     best_bids: Sequence[Optional[float]], price: float,
                     queue_ahead: float) -> Optional[int]:
    """The snapshot index at which `simulate_leg_fill_touch` would declare this leg FILLED
    (None if it never fills). Same accounting as the Q49 primitive — re-walked here only to
    recover WHEN the fill happened, which the boolean API does not expose. Kept in lockstep
    with `simulate_leg_fill_touch` by `tests/test_q50_s68_gate_ladder.py`."""
    cumulative = 0.0
    for i in range(len(ladders) - 1):
        cumulative += touch_departures_between(ladders[i], ladders[i + 1], price, best_bids[i])
        if cumulative > 0.0 and cumulative >= queue_ahead - _EPS:
            return i + 1
    return None


def book_mid(rec: Dict[str, Any]) -> Optional[float]:
    """The binary book's own mid from its two REAL bids: (yes_bid + (1 - no_bid)) / 2.
    The upper leg is the mirrored offer the collector derives (`collection/normalize.py`), so
    this is a two-sided mid in YES terms, tagged `real_bid`. None on a one-sided book (L23)."""
    yb, nb = rec.get("best_yes_bid"), rec.get("best_no_bid")
    if yb is None or nb is None:
        return None
    return (float(yb) + (1.0 - float(nb))) / 2.0


def leg_markout(mids: Sequence[Optional[float]], fill_idx: int, side: str, price: float,
                k: int) -> Optional[float]:
    """Post-fill MARKOUT of one filled leg, marked to the BOOK'S OWN mid `k` snapshots after
    the fill (clamped to the last snapshot): `mid - price` for a YES fill, `(1 - mid) - price`
    for a NO fill.

    Sign convention: NEGATIVE = the book moved against us after the fill = ADVERSE SELECTION,
    the term that killed S6/S13 and that this probe's fill model does not charge.

    READ THE CAVEAT BEFORE QUOTING THIS (L253): `tape/orderbook_depth/` carries no trade or
    volume field (L68/L106), so the `touch` rule cannot tell a CANCEL at our price from a
    TRADE against us. A fill proxy blind to trade direction cannot exhibit adverse selection,
    so a non-negative markout here is NOT evidence that adverse selection is absent — it is
    the expected output of a blind instrument. This measures the half-spread we book, not the
    informational cost of the counterparty we booked it against."""
    if fill_idx is None or not mids:
        return None
    j = min(fill_idx + k, len(mids) - 1)
    mid = mids[j]
    if mid is None:
        return None
    return (mid - price) if side == "yes" else ((1.0 - mid) - price)


MARKOUT_HORIZONS_K: Tuple[int, ...] = (0, 1, 5, 10)


def adverse_selection_breakeven(trades: Sequence[dict], model: str = PRIMARY_FILL_MODEL,
                                n_boot: int = 4000,
                                grid: Sequence[float] = (0.0, 0.005, 0.01, 0.015, 0.02,
                                                         0.025, 0.03, 0.04, 0.05)
                                ) -> Dict[str, Any]:
    """How large a per-FILLED-LEG adverse-selection charge does it take to destroy this
    population's strategy-level verdict?  Charges `h` per filled leg (2 legs on a double fill,
    1 on a single-side fill, 0 on a no-fill) and re-bootstraps by series at each `h`.

    Returns the smallest grid `h` at which the CI no longer clears (>0 AND one tick), plus the
    whole ladder. A small break-even means the verdict is decided by an UNMEASURED term, which
    is a data-adequacy statement, not an edge."""
    from core.bootstrap import block_bootstrap, clears_tick_magnitude

    ladder = []
    breakeven = None
    for h in grid:
        units: Dict[str, List[float]] = {}
        for t in trades:
            m = t["models"][model]
            cat = m["fill_category"]
            n_legs = 2 if cat == "both" else (0 if cat == "neither" else 1)
            units.setdefault(t["series"], []).append(
                float(m["pnl_strategy_level"]) - n_legs * float(h))
        b = block_bootstrap(units, n_boot=n_boot)
        lo = b["ci95"][0]
        clears = (lo is not None and lo > 0.0
                  and clears_tick_magnitude(b["ci95"], tick=PRICE_TICK, min_ticks=1.0))
        ladder.append({"haircut_per_filled_leg": h, "mean": b["mean"], "ci95": b["ci95"],
                       "clears": clears})
        if not clears and breakeven is None:
            breakeven = h
    return {"breakeven_haircut_per_filled_leg": breakeven, "ladder": ladder,
            "note": ("charge that flips the cell to DEAD; compare against the UNMEASURABLE "
                     "adverse-selection term (L253) — orderbook_depth has no trade field")}


def aggregate_markouts(trades: Sequence[dict]) -> Dict[str, Any]:
    """Mean/median markout across every filled leg in the population, per k."""
    out: Dict[str, Any] = {}
    for k in MARKOUT_HORIZONS_K:
        vals = [v for t in trades for v in t.get("markouts", {}).get(str(k), [])
                if v is not None]
        out[str(k)] = {
            "n_filled_legs": len(vals),
            "mean": (sum(vals) / len(vals)) if vals else None,
            "median": _median_or_none(vals),
        }
    return out


def _median_or_none(xs: Sequence[float]) -> Optional[float]:
    v = sorted(float(x) for x in xs)
    if not v:
        return None
    m = len(v) // 2
    return v[m] if len(v) % 2 else (v[m - 1] + v[m]) / 2.0


# --------------------------------------------------------------------------- #
# Trade construction (same row schema as Q49 so `analyze_cut` consumes it unchanged)
# --------------------------------------------------------------------------- #
def build_trades_at(per_ticker: Dict[str, List[dict]], settlement: Dict[str, dict],
                    horizon_hours: Optional[float], extra_ticks: int) -> Tuple[List[dict],
                                                                               Dict[str, Any]]:
    """One both-sides resting-maker trade per qualifying ticker, entered by the L251 rule and
    admitted by the L252 gate. The fill simulation runs over the snapshots FROM THE ENTRY INDEX
    ONWARD (we cannot observe queue departures before we have rested an order).

    Every simulation/P&L primitive is the Q49 one, unchanged."""
    trades: List[dict] = []
    funnel = {"tickers_with_preclose": len(per_ticker), "no_snapshot_within_horizon": 0,
              "entry_missing_quote": 0, "entry_not_two_sided": 0,
              "entry_spread_below_two_fees": 0, "entry_spread_below_fees_plus_ticks": 0,
              "entry_single_snapshot": 0, "candidates": 0}
    for tk, all_snaps in sorted(per_ticker.items()):
        idx = select_entry_index(all_snaps, horizon_hours)
        if idx is None:
            funnel["no_snapshot_within_horizon"] += 1
            continue
        snaps = all_snaps[idx:]
        entry = snaps[0]
        rec = entry["record"]
        yes_bid = rec.get("best_yes_bid")
        no_bid = rec.get("best_no_bid")
        yes_offer = rec.get("best_yes_ask")
        gate = gate_with_ticks(yes_bid, no_bid, yes_offer, extra_ticks)
        if not gate["eligible"]:
            reason = gate["reason"]
            if reason == "missing_quote":
                funnel["entry_missing_quote"] += 1
            elif reason == "not_two_sided":
                funnel["entry_not_two_sided"] += 1
            elif reason == "spread_below_fees_plus_ticks":
                funnel["entry_spread_below_fees_plus_ticks"] += 1
            else:
                funnel["entry_spread_below_two_fees"] += 1
            continue
        if len(snaps) < 2:
            # no later snapshot after entry -> no observable departure -> unmeasurable,
            # which is NOT a fill (L86: never book an unmeasured leg as a free zero)
            funnel["entry_single_snapshot"] += 1
            continue
        funnel["candidates"] += 1

        p_yes, p_no = float(yes_bid), float(no_bid)
        yes_ladders = [s["record"].get("yes_bids") for s in snaps]
        no_ladders = [s["record"].get("no_bids") for s in snaps]
        yes_best = [best_bid_of(s["record"].get("yes_bids"),
                                s["record"].get("best_yes_bid")) for s in snaps]
        no_best = [best_bid_of(s["record"].get("no_bids"),
                               s["record"].get("best_no_bid")) for s in snaps]
        q_yes = queue_ahead_at(yes_ladders[0], p_yes)
        q_no = queue_ahead_at(no_ladders[0], p_no)

        s = settlement[tk]
        # L52: a Kalshi settlement is NOT always binary ('scalar' exists). `load_settlements`
        # already drops non-binary rows, but this probe must not depend on an upstream filter
        # to stay correct — guard here so a 'scalar' can never be booked as the losing side.
        result = require_binary_result(s["result"], context=f"settlement for {tk}")
        legs = {
            "turnover": (simulate_leg_fill(yes_ladders, p_yes, q_yes),
                         simulate_leg_fill(no_ladders, p_no, q_no)),
            "touch": (simulate_leg_fill_touch(yes_ladders, yes_best, p_yes, q_yes),
                      simulate_leg_fill_touch(no_ladders, no_best, p_no, q_no)),
        }
        models: Dict[str, Any] = {}
        for model, (fy, fn) in legs.items():
            if fy["filled"] and fn["filled"]:
                category = "both"
                pnl_strategy = both_fill_pnl(p_yes, p_no)
                pnl_both = pnl_strategy
            elif fy["filled"]:
                category, pnl_both = "yes_only", None
                pnl_strategy = single_side_pnl(p_yes, "yes", result)
            elif fn["filled"]:
                category, pnl_both = "no_only", None
                pnl_strategy = single_side_pnl(p_no, "no", result)
            else:
                category, pnl_both, pnl_strategy = "neither", None, 0.0
            models[model] = {
                "filled_yes": fy["filled"], "filled_no": fn["filled"],
                "departures_yes": fy["cumulative_departures"],
                "departures_no": fn["cumulative_departures"],
                "fill_category": category,
                "frozen_both_ladders": fy["frozen"] and fn["frozen"],
                "pnl_both_fill": pnl_both,
                "pnl_strategy_level": pnl_strategy,
            }

        mids = [book_mid(s2["record"]) for s2 in snaps]
        fy_idx = touch_fill_index(yes_ladders, yes_best, p_yes, q_yes)
        fn_idx = touch_fill_index(no_ladders, no_best, p_no, q_no)
        markouts: Dict[str, List[Optional[float]]] = {str(k): [] for k in MARKOUT_HORIZONS_K}
        for k in MARKOUT_HORIZONS_K:
            if fy_idx is not None:
                markouts[str(k)].append(leg_markout(mids, fy_idx, "yes", p_yes, k))
            if fn_idx is not None:
                markouts[str(k)].append(leg_markout(mids, fn_idx, "no", p_no, k))

        trades.append({
            "ticker": tk,
            "event_ticker": s["event_ticker"],
            "series": s["series"],
            "result": result,
            "settles_yes": result == "yes",
            "entry_index": idx,
            "entry_captured_at": entry["captured_at"].isoformat(),
            "ttc_hours_entry": entry["ttc_hours"],
            "n_snapshots": len(snaps),
            "n_snapshots_before_entry": idx,
            "yes_fill_price": p_yes,
            "no_fill_price": p_no,
            "entry_spread": gate["spread"],
            "required_spread": gate["required_spread"],
            "gate_extra_ticks": int(extra_ticks),
            "horizon_hours": horizon_hours,
            "gross_capture": gate["gross_capture"],
            "fee_yes": gate["fee_yes"],
            "fee_no": gate["fee_no"],
            "queue_ahead_yes": q_yes,
            "queue_ahead_no": q_no,
            "capturable_depth_yes": capturable_depth(yes_ladders[0], p_yes),
            "capturable_depth_no": capturable_depth(no_ladders[0], p_no),
            "lottery_tail_frac_yes": lottery_tail_fraction(yes_ladders[0], p_yes),
            "lottery_tail_frac_no": lottery_tail_fraction(no_ladders[0], p_no),
            "models": models,
            "touch_fill_index_yes": fy_idx,
            "touch_fill_index_no": fn_idx,
            "markouts": markouts,
            # Q49's cut flags kept so a Q50 row is schema-compatible with `cut_trades`
            "fillable_entry_spread": True,
            "fillable_entry_nearclose": (horizon_hours is not None),
            "price_source_tag": "real_bid(fills)+real_bid(queue)+broker_truth(settlement)",
        })
    return trades, funnel


def distinct_entry_timestamps(trades: Sequence[dict]) -> int:
    """L251 artifact measure: how many DISTINCT capture instants the population's entries sit
    on. 1 means every 'candidate' was rested at the same moment (a tape-start artifact)."""
    return len({t["entry_captured_at"] for t in trades})


# --------------------------------------------------------------------------- #
# Per-cell verdict
# --------------------------------------------------------------------------- #
def cell_verdict(cell: Dict[str, Any]) -> Tuple[str, str]:
    """The kill ladder for ONE (N, H) cell, applied to the L249-correct object (the
    strategy-level bootstrap). Returns (verdict, reason).

    Order matters: an empty/thin population is a DATA-ADEQUACY answer and must never be
    dressed up as a CI falsification (L53/L43)."""
    a = cell["analysis"]
    n = a["n_candidates"]
    if n == 0:
        return "DEAD-by-adequacy", "empty_population"
    strat = a["bootstrap_strategy_level_diagnostic"]
    n_units = strat["n_units_series"]
    if n_units is None or n_units < MIN_CI_UNITS:
        return "DEAD-by-adequacy", f"n_units_series={n_units} < {MIN_CI_UNITS} (L41 floor)"
    if not strat["admissible"]["admissible"]:
        return ("DEAD-by-adequacy",
                f"bootstrap inadmissible: {','.join(strat['admissible']['reasons'])}")
    lo = strat["ci95"][0]
    if lo is None or lo <= 0.0:
        return "DEAD-by-CI", f"strategy-level 95% CI lower bound {lo} not > 0"
    if not cell["clears_tick_magnitude_strategy"]:
        return "DEAD-by-magnitude", "CI positive but below one fillable tick (L27)"
    return "ALIVE-CANDIDATE", "admissible strategy-level CI > 0 clearing the tick gate"


def run(depth_glob: str = DEPTH_GLOB, settlement_glob: str = SETTLEMENT_GLOB,
        gate_ticks: Sequence[int] = DEFAULT_GATE_TICKS,
        horizons: Sequence[Optional[float]] = DEFAULT_HORIZONS_H,
        model: str = PRIMARY_FILL_MODEL, n_boot: int = 10000) -> Dict[str, Any]:
    """Load the tape once, then sweep the (N, H) ladder. READ-ONLY."""
    from core.bootstrap import clears_tick_magnitude  # local: keeps module import light

    settlement, settle_stats = load_settlements(settlement_glob)
    per_ticker, funnel = load_preclose_snapshots(depth_glob, settlement)

    # Q49 anchor: its own earliest-entry build over the identical tape, so the two probes'
    # populations are comparable in one artifact rather than by re-running two scripts.
    q49_trades, q49_funnel = build_trades(per_ticker, settlement)

    cells: List[Dict[str, Any]] = []
    all_rows: List[dict] = []
    for h in horizons:
        for n_ticks in gate_ticks:
            trades, cell_funnel = build_trades_at(per_ticker, settlement, h, n_ticks)
            analysis = analyze_cut(trades, model=model, n_boot=n_boot)
            strat_ci = analysis["bootstrap_strategy_level_diagnostic"]["ci95"]
            cell = {
                "gate_extra_ticks": int(n_ticks),
                "horizon_hours": h,
                "fill_model": model,
                "funnel": cell_funnel,
                "n_distinct_entry_timestamps": distinct_entry_timestamps(trades),
                "entry_timestamp_artifact_flag": (
                    len(trades) > 0
                    and distinct_entry_timestamps(trades) < MIN_DISTINCT_ENTRY_TS),
                "clears_tick_magnitude_strategy": clears_tick_magnitude(
                    strat_ci, tick=PRICE_TICK, min_ticks=1.0),
                "markouts_by_k": aggregate_markouts(trades),
                "adverse_selection_breakeven": adverse_selection_breakeven(trades, model),
                "analysis": analysis,
            }
            v, why = cell_verdict(cell)
            cell["verdict"], cell["verdict_reason"] = v, why
            cells.append(cell)
            for t in trades:
                row = dict(t)
                row.pop("models", None)
                row["fill_category"] = t["models"][model]["fill_category"]
                row["pnl_strategy_level"] = t["models"][model]["pnl_strategy_level"]
                row["pnl_both_fill"] = t["models"][model]["pnl_both_fill"]
                row["fill_model"] = model
                all_rows.append(row)

    alive = [c for c in cells if c["verdict"] == "ALIVE-CANDIDATE"]
    return {
        "probe": "q50_s68_gate_ladder",
        "question": ("does the S68 both-bid maker capture clear a block-bootstrapped-by-series "
                     "95% CI > 0 under a fees-plus-N-ticks gate (L252) and the "
                     "first-snapshot-with-ttc<=H entry rule (L251)?"),
        "bootstrapped_object": ("strategy_level_pnl (double fill = realized capture; "
                                "single-side fill = unhedged directional position marked to "
                                "broker_truth settlement; no fill = 0) — L249"),
        "double_fill_object_note": ("pnl_both_fill is SIGN-BOUNDED BY CONSTRUCTION under this "
                                    "gate (L249) — reported as a diagnostic, never a verdict"),
        "fill_model_note": ("touch is primary (L250); the turnover rule saturates on "
                            "multi-day holds and is a labeled diagnostic only"),
        "price_source_tags": {"fills": "real_bid", "queue_depth": "real_bid",
                              "settlement": "broker_truth"},
        "bootstrap_unit": "game_series (L6/L41)",
        "n_boot": n_boot,
        "settlement_stats": settle_stats,
        "join_funnel": {k: (len(v) if isinstance(v, set) else v) for k, v in funnel.items()},
        "q49_anchor": {"note": ("Q49's own earliest-pre-close-entry build over the identical "
                                "tape, for population comparison only"),
                       "funnel": q49_funnel,
                       "n_trades": len(q49_trades),
                       "n_distinct_entry_timestamps": distinct_entry_timestamps(q49_trades)},
        "cells": cells,
        "rows": all_rows,
        "any_alive_cell": bool(alive),
        "overall_verdict": ("ALIVE-CANDIDATE(S) PRESENT — requires independent verification"
                            if alive else "DEAD across every (N,H) cell"),
    }


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def _f(x: Optional[float], nd: int = 4) -> str:
    return "n/a" if x is None else f"{x:.{nd}f}"


def _ci(ci: Sequence[Optional[float]]) -> str:
    if not ci or ci[0] is None or ci[1] is None:
        return "[n/a, n/a]"
    return f"[{ci[0]:+.4f}, {ci[1]:+.4f}]"


def print_report(rep: Dict[str, Any]) -> None:
    print("=" * 100)
    print("Q50 / S68 — fees-plus-N-ticks gate ladder (L252) x first-snapshot-with-ttc<=H entry "
          "(L251)")
    print("=" * 100)
    print(f"bootstrapped object : {rep['bootstrapped_object']}")
    print(f"double-fill object  : {rep['double_fill_object_note']}")
    print(f"fill model          : {rep['fill_model_note']}")
    print(f"price tags          : {rep['price_source_tags']}")
    print(f"bootstrap unit      : {rep['bootstrap_unit']}  n_boot={rep['n_boot']}")
    jf = rep["join_funnel"]
    print(f"join funnel         : depth_lines={jf['depth_lines']} "
          f"depth_tickers={jf['depth_tickers']} joined={jf['joined_tickers']} "
          f"preclose={jf['preclose_tickers']} excluded_series={jf['excluded_series_tickers']}")
    q = rep["q49_anchor"]
    print(f"Q49 anchor          : {q['n_trades']} candidates on "
          f"{q['n_distinct_entry_timestamps']} distinct entry instant(s)")
    print()
    hdr = (f"{'H':>5} {'N':>2} {'cands':>6} {'ser':>4} {'games':>6} {'entTS':>6} "
           f"{'both%':>7} {'meanPnL':>9} {'CI95(strategy)':>21} {'adm':>4} {'tick':>5}  verdict")
    print(hdr)
    print("-" * len(hdr))
    for c in rep["cells"]:
        a = c["analysis"]
        st = a["bootstrap_strategy_level_diagnostic"]
        bf = a["fills"]["both_fill_rate"]
        flag = "*" if c["entry_timestamp_artifact_flag"] else " "
        print(f"{str(c['horizon_hours']):>5} {c['gate_extra_ticks']:>2} {a['n_candidates']:>6} "
              f"{a['n_series']:>4} {a['n_games']:>6} "
              f"{str(c['n_distinct_entry_timestamps']) + flag:>6} "
              f"{('n/a' if bf is None else f'{bf * 100:.1f}%'):>7} "
              f"{_f(st['mean']):>9} {_ci(st['ci95']):>21} "
              f"{'Y' if st['admissible']['admissible'] else 'N':>4} "
              f"{'Y' if c['clears_tick_magnitude_strategy'] else 'N':>5}  "
              f"{c['verdict']} ({c['verdict_reason']})")
    print()
    print("* = entries cluster on < 3 distinct capture instants (L251 tape-start artifact)")
    print()
    print("DIAGNOSTIC ONLY (L249 — sign-bounded by the gate, carries NO evidentiary weight):")
    for c in rep["cells"]:
        a = c["analysis"]
        b = a["bootstrap_both_fill_by_series"]
        mag = a["net_pnl_magnitude"]
        print(f"  H={c['horizon_hours']} N={c['gate_extra_ticks']}: "
              f"double-fills={b['n_obs_double_fills']} mean={_f(b['mean'])} "
              f"CI={_ci(b['ci95'])} units={b['n_units_series']} "
              f"clears_tick={mag.get('n_clears_tick')}/{mag.get('n')}")
    print()
    print("ADVERSE SELECTION — the term this fill model does NOT charge (L253):")
    print("  markout = book's own mid k snapshots after the fill, minus our fill price;")
    print("  NEGATIVE would mean the book moved against us (adverse selection).")
    print("  CAVEAT: orderbook_depth has NO trade/volume field (L68/L106), so `touch` cannot")
    print("  tell a cancel from a trade — a blind proxy CANNOT exhibit adverse selection, so a")
    print("  non-negative markout here is NOT evidence that adverse selection is absent.")
    for c in rep["cells"]:
        if not (c["verdict"] == "ALIVE-CANDIDATE" or (c["gate_extra_ticks"] == 1
                                                      and c["horizon_hours"] == 24.0)):
            continue
        mk = c["markouts_by_k"]
        be = c["adverse_selection_breakeven"]["breakeven_haircut_per_filled_leg"]
        print(f"  H={c['horizon_hours']} N={c['gate_extra_ticks']} [{c['verdict']}]: "
              + " ".join(f"k={k}:{_f(mk[str(k)]['mean'])}" for k in MARKOUT_HORIZONS_K)
              + f"  | break-even adverse-selection charge = "
              + (f"{be * 100:.1f}c/filled leg" if be is not None else "never within grid"))
    print()
    print(f"OVERALL: {rep['overall_verdict']}")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--depth-glob", default=DEPTH_GLOB)
    ap.add_argument("--settlement-glob", default=SETTLEMENT_GLOB)
    ap.add_argument("--gate-ticks", default=",".join(str(n) for n in DEFAULT_GATE_TICKS),
                    help="comma-separated N values for the fees-plus-N-ticks gate (L252)")
    ap.add_argument("--horizons", default=",".join(str(h) for h in DEFAULT_HORIZONS_H),
                    help="comma-separated entry horizons in hours (L251 first-ttc<=H rule)")
    ap.add_argument("--fill-model", default=PRIMARY_FILL_MODEL, choices=("touch", "turnover"))
    ap.add_argument("--n-boot", type=int, default=10000)
    ap.add_argument("--rows-out", default=str(ROWS_OUT))
    ap.add_argument("--summary-out", default=str(SUMMARY_OUT))
    ap.add_argument("--no-write", action="store_true", help="report only; write no files")
    args = ap.parse_args(argv)

    gate_ticks = [int(x) for x in args.gate_ticks.split(",") if x.strip()]
    horizons: List[Optional[float]] = [float(x) for x in args.horizons.split(",") if x.strip()]
    rep = run(depth_glob=args.depth_glob, settlement_glob=args.settlement_glob,
              gate_ticks=gate_ticks, horizons=horizons, model=args.fill_model,
              n_boot=args.n_boot)
    print_report(rep)

    if not args.no_write:
        rows = rep.pop("rows")
        Path(args.rows_out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.rows_out, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, sort_keys=True) + "\n")
        with open(args.summary_out, "w", encoding="utf-8") as f:
            json.dump(rep, f, indent=2, sort_keys=True, default=str)
        print(f"\nwrote {args.rows_out} ({len(rows)} rows) and {args.summary_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
