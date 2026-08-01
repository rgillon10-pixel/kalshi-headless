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

EXIT TREATMENT — BOTH BRANCHES, WORSE OF THE TWO (L256; built 2026-08-01)
-------------------------------------------------------------------------
Two of the four fill categories (``yes_only``, ``no_only``) leave an UNHEDGED single-side
position. Marking that orphan to the ``broker_truth`` $0/$1 settlement is the most GENEROUS
treatment available — a free directional lottery ticket. Every cell is therefore bootstrapped
twice, over the same object, unit and ``n_boot``:

* ``hold_to_settlement`` — the generous branch (``pnl_strategy_level``);
* ``flatten_at_cross``  — the orphan is CLOSED by lifting the other side's REAL ask
  (``flatten_at_cross_pnl``: maker fee on the entry leg, **taker** fee on the crossing exit).

``cell_verdict`` returns the WORSE of the two and RAISES if the flatten branch is absent, so
the generous branch can never become the headline by omission. On a mirrored book that has not
moved since the fill, the flatten costs exactly the two fees.

ROBUSTNESS (added 2026-08-01 after the verifier pass — provenance fix)
---------------------------------------------------------------------
The first cut of this probe reported three "attacks that did NOT kill it" (leave-one-series-out,
longshot-drop, price-offset placebo) as PROSE ONLY: no function, no flag, no artifact. A verifier
had to re-derive them by hand, and in doing so found the longshot CI had been quoted at an
undisclosed ``n_boot=4000`` while the headline used 10,000. Both defects are fixed here — the three
attacks are re-runnable code (``leave_one_series_out``, ``drop_longshot_single_side``,
``price_offset_placebo``, driven by ``run_robustness``), they run BY DEFAULT, they use the SAME
``n_boot`` as the headline, and every reported number carries its own ``n_boot`` in the output.

CLI (direct form is load-bearing per L232 — a repo-root conftest.py masks broken cross-script
imports under pytest, so a green suite does not prove the CLI works)::

    python3 scripts/q50_s68_gate_ladder.py
    python3 scripts/q50_s68_gate_ladder.py --gate-ticks 0,1,2,3,5 --horizons 24,6
    python3 scripts/q50_s68_gate_ladder.py --robustness-only     # the three attacks alone
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
    load_settlements, maker_fee, per_series_pnl, queue_ahead_at, simulate_leg_fill,
    simulate_leg_fill_touch, single_side_pnl, touch_departures_between,
    two_sided_wide_entry,
)
from core.depth import capturable_depth, lottery_tail_fraction  # noqa: E402
from core.pricing import TAKER_FEE_RATE, fee_per_contract  # noqa: E402
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
ROBUSTNESS_OUT = REPO_ROOT / "reports" / "q50_s68_gate_ladder_robustness.json"

#: The cell the three robustness attacks are run against — the ladder's headline
#: (H=24h entry, gate = fees + 1 tick), i.e. the ALIVE cell whose artifact status is the
#: whole question. Overridable on the CLI.
HEADLINE_HORIZON_H = 24.0
HEADLINE_GATE_TICKS = 1
#: A single-side fill at or below this price is the "longshot lottery" leg the drop-attack removes.
LONGSHOT_MAX_PRICE = 0.30
#: The placebo rests this far BELOW the entry best bid (negative = worse price, deeper queue).
PLACEBO_OFFSET = -0.02


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
                                n_boot: int = 10000,
                                grid: Sequence[float] = (0.0, 0.005, 0.01, 0.015, 0.02,
                                                         0.025, 0.03, 0.04, 0.05)
                                ) -> Dict[str, Any]:
    """How large a per-FILLED-LEG adverse-selection charge does it take to destroy this
    population's strategy-level verdict?  Charges `h` per filled leg (2 legs on a double fill,
    1 on a single-side fill, 0 on a no-fill) and re-bootstraps by series at each `h`.

    Returns the smallest grid `h` at which the CI no longer clears (>0 AND one tick), plus the
    whole ladder. A small break-even means the verdict is decided by an UNMEASURED term, which
    is a data-adequacy statement, not an edge.

    `n_boot` defaults to the headline's 10,000 and is echoed on every row of the returned
    ladder — an earlier cut of this module defaulted to 4,000 here while the headline used
    10,000, which is exactly the silent parameter drift a verifier caught in the finding."""
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
                       "clears": clears, "n_boot": n_boot})
        if not clears and breakeven is None:
            breakeven = h
    return {"breakeven_haircut_per_filled_leg": breakeven, "ladder": ladder, "n_boot": n_boot,
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
# EXIT TREATMENT — the L256 flatten-at-cross branch
#
# A both-bid maker sim has FOUR fill categories, and two of them (`yes_only`, `no_only`) leave
# an UNHEDGED single-side position. Q49/Q50 originally marked that orphan to the `broker_truth`
# $0/$1 settlement, which is the MOST GENEROUS possible treatment: it hands the simulation a
# free directional lottery ticket that no maker running this strategy would knowingly keep.
#
# L256 (2026-08-01, Q50 verifier pass) is the rule that came out of it: **report BOTH exit
# treatments — hold-to-settlement AND flatten-at-cross — and take the WORSE of the two as the
# headline.** The verifier applied the flatten treatment BY HAND and every one of Q50's ten
# CI>0 cells died; because it was hand-run, no committed artifact carried the number (an L165
# provenance hole, flagged in the lesson row itself). This section is that treatment as
# re-runnable code, so the claim is reproducible instead of remembered.
#
# The honest flatten is a TAKER exit: we hold an unwanted position and cross the spread to be
# rid of it. Entry keeps the MAKER rate (our bid was lifted), the flatten leg pays the TAKER
# rate. Charging maker on both would be the L5 error (a 4x fee understatement) with its sign
# flipped — it would make the honest branch look better than it is.
# --------------------------------------------------------------------------- #
def taker_fee(fill_price: float) -> float:
    """The flat TAKER fee on ONE crossing leg, via the sanctioned `core.pricing` helper at
    `TAKER_FEE_RATE` (never hand-rolled — L5). Used for the flatten leg only; every entry leg
    in this probe is a resting maker fill and keeps `maker_fee`."""
    return fee_per_contract(float(fill_price), rate=TAKER_FEE_RATE)


def opposite_side_ask(rec: Optional[Dict[str, Any]], side: str) -> Optional[float]:
    """The REAL ask we must LIFT to flatten an orphan `side` leg: `best_no_ask` to close a
    YES position, `best_yes_ask` to close a NO one. Tagged `real_ask` when present.

    Returns None — never a number — when the quote is absent or is 0.0, because a zero ask is
    the ABSENCE of an offer, not a free contract (L1/L105). A None here makes the flatten
    UNMEASURABLE for that trade, and `per_series_pnl` then drops the row rather than booking
    it as a $0.00 exit (L86: never book an unmeasured leg as a free zero)."""
    if rec is None:
        return None
    if side not in ("yes", "no"):
        raise ValueError(f"side must be 'yes' or 'no' (got {side!r})")
    raw = rec.get("best_no_ask") if side == "yes" else rec.get("best_yes_ask")
    if raw is None:
        return None
    a = float(raw)
    if a <= 0.0 or a > 1.0:
        return None
    return a


def flatten_at_cross_pnl(entry_price: float, side: str,
                         opposite_ask: Optional[float]) -> Optional[float]:
    """L256's honest exit for an UNHEDGED single-side leg: instead of riding the orphan to
    settlement, CLOSE it by buying the other side at its ask. Owning YES *and* NO on the same
    binary market pays exactly $1 whichever way it settles, so::

        gross = 1.00 - entry_price - opposite_ask
        pnl   = gross - maker_fee(entry_price) - taker_fee(opposite_ask)

    MAKER on the entry leg (our resting bid was lifted), TAKER on the flatten leg (we cross
    the spread to get out) — the 4x asymmetry L5 exists to protect.

    THE IDENTITY L256 PREDICTS, and which this function reproduces rather than hardcodes: on a
    mirrored binary book (`best_no_ask == 1 - best_yes_bid` by collector construction,
    `collection/normalize.py`) that has not moved since our fill at the touch,
    `opposite_ask == 1 - entry_price`, so `gross == 0` and the exit costs **precisely the two
    fees** — a small CERTAIN loss where hold-to-settlement booked a fat lottery. When the book
    HAS moved the gross is non-zero and signed: it is positive iff the book moved in our
    favour between resting and flattening, which is the direction a fill proxy blind to trade
    direction (L253) cannot otherwise see.

    Returns None when `opposite_ask` is None (unquotable => UNMEASURABLE, never 0.0)."""
    if side not in ("yes", "no"):
        raise ValueError(f"side must be 'yes' or 'no' (got {side!r})")
    if opposite_ask is None:
        return None
    p = float(entry_price)
    a = float(opposite_ask)
    gross = 1.0 - p - a
    return gross - maker_fee(p) - taker_fee(a)


def flatten_analysis(trades: Sequence[dict], model: str = PRIMARY_FILL_MODEL,
                     n_boot: int = 10000) -> Dict[str, Any]:
    """The strategy-level bootstrap under the L256 FLATTEN-AT-CROSS exit treatment — same
    object, same unit (GAME-SERIES, L6/L41), same `n_boot`, same admissibility gate as the
    hold-to-settlement branch it sits beside. The ONLY difference is how an unhedged
    single-side leg is closed.

    `both` (already hedged) and `neither` (nothing to close) rows are IDENTICAL across the two
    treatments by construction; only the orphan legs move.

    `n_unmeasurable_single_side` counts orphans whose flatten quote was absent. Those rows are
    DROPPED from the bootstrap (L86), which is a coverage limit reported here rather than
    hidden — a large count means this branch is speaking for a smaller population than the
    hold-to-settlement branch, and the reader must be told."""
    from core.bootstrap import (block_bootstrap, bootstrap_verdict_admissible,
                                clears_tick_magnitude)

    units = per_series_pnl(trades, "pnl_strategy_flatten", model)
    boot = block_bootstrap(units, n_boot=n_boot)
    adm = bootstrap_verdict_admissible(units, min_units=MIN_CI_UNITS)
    n_unmeasurable = sum(
        1 for t in trades
        if t["models"][model]["fill_category"] in ("yes_only", "no_only")
        and t["models"][model].get("pnl_strategy_flatten") is None)
    n_single = sum(1 for t in trades
                   if t["models"][model]["fill_category"] in ("yes_only", "no_only"))
    return {
        "exit_treatment": "flatten_at_cross",
        "mean": boot["mean"],
        "ci95": boot["ci95"],
        "n_units_series": len(units) if units else 0,
        "n_obs": sum(len(v) for v in units.values()),
        "admissible": adm,
        "clears_tick_magnitude": clears_tick_magnitude(boot["ci95"], tick=PRICE_TICK,
                                                       min_ticks=1.0),
        "n_single_side_legs": n_single,
        "n_unmeasurable_single_side": n_unmeasurable,
        "n_boot": n_boot,
        "price_source_tag": "real_ask(flatten)+real_bid(entry)",
        "note": ("L256: the honest exit for an orphan leg. Entry fee MAKER, flatten fee TAKER. "
                 "Unquotable flattens are dropped, never zeroed (L86)."),
    }


# --------------------------------------------------------------------------- #
# Trade construction (same row schema as Q49 so `analyze_cut` consumes it unchanged)
# --------------------------------------------------------------------------- #
def build_trades_at(per_ticker: Dict[str, List[dict]], settlement: Dict[str, dict],
                    horizon_hours: Optional[float], extra_ticks: int,
                    price_offset: float = 0.0) -> Tuple[List[dict], Dict[str, Any]]:
    """One both-sides resting-maker trade per qualifying ticker, entered by the L251 rule and
    admitted by the L252 gate. The fill simulation runs over the snapshots FROM THE ENTRY INDEX
    ONWARD (we cannot observe queue departures before we have rested an order).

    Every simulation/P&L primitive is the Q49 one, unchanged.

    `price_offset` (default 0.0 = the real behaviour) shifts BOTH resting prices away from the
    entry best bid without changing the ADMISSION gate, so the placebo population is the same
    set of books priced worse. `price_offset=-0.02` is the placebo attack: rest two ticks below
    the touch, where a genuinely price-priority-aware fill model must almost never fill. A
    candidate whose offset price is <= 0 is dropped (a zero/negative price is the ABSENCE of an
    order, never a $0.00 fill — L1/L105) and counted in the funnel."""
    trades: List[dict] = []
    funnel = {"tickers_with_preclose": len(per_ticker), "no_snapshot_within_horizon": 0,
              "entry_missing_quote": 0, "entry_not_two_sided": 0,
              "entry_spread_below_two_fees": 0, "entry_spread_below_fees_plus_ticks": 0,
              "entry_single_snapshot": 0, "offset_price_non_positive": 0, "candidates": 0,
              # L256 flatten-branch coverage, reported not hidden
              "flatten_unquotable_single_side": 0, "flatten_no_fill_instant": 0}
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

        p_yes = round(float(yes_bid) + float(price_offset), 10)
        p_no = round(float(no_bid) + float(price_offset), 10)
        if p_yes <= 0.0 or p_no <= 0.0:
            funnel["offset_price_non_positive"] += 1
            continue
        funnel["candidates"] += 1

        yes_ladders = [s["record"].get("yes_bids") for s in snaps]
        no_ladders = [s["record"].get("no_bids") for s in snaps]
        yes_best = [best_bid_of(s["record"].get("yes_bids"),
                                s["record"].get("best_yes_bid")) for s in snaps]
        no_best = [best_bid_of(s["record"].get("no_bids"),
                               s["record"].get("best_no_bid")) for s in snaps]
        q_yes = queue_ahead_at(yes_ladders[0], p_yes)
        q_no = queue_ahead_at(no_ladders[0], p_no)

        # touch-model fill INSTANTS, needed both by the L253 markout and by the L256
        # flatten (the flatten quote must be read at the snapshot where the orphan filled)
        fy_idx = touch_fill_index(yes_ladders, yes_best, p_yes, q_yes)
        fn_idx = touch_fill_index(no_ladders, no_best, p_no, q_no)

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
            # ---- L256: the SAME population under the flatten-at-cross exit ----------
            # `both` is already hedged and `neither` has nothing to close, so those rows are
            # identical across the two treatments; only an orphan leg moves.
            flat_price: Optional[float] = None
            if category in ("both", "neither"):
                pnl_flatten: Optional[float] = pnl_strategy
            elif model != PRIMARY_FILL_MODEL:
                # the `turnover` rule accumulates departures across the WHOLE hold and never
                # localises a fill instant, so there is no snapshot at which to read a flatten
                # quote. UNMEASURABLE under that model -- reported, never zeroed (L86). It is
                # a labeled diagnostic anyway (L250); the verdict rests on `touch`.
                pnl_flatten = None
                funnel["flatten_no_fill_instant"] += 1
            else:
                orphan_side = "yes" if category == "yes_only" else "no"
                orphan_price = p_yes if category == "yes_only" else p_no
                idx_fill = fy_idx if category == "yes_only" else fn_idx
                flat_rec = (snaps[idx_fill]["record"]
                            if idx_fill is not None and idx_fill < len(snaps) else None)
                flat_price = opposite_side_ask(flat_rec, orphan_side)
                pnl_flatten = flatten_at_cross_pnl(orphan_price, orphan_side, flat_price)
                if pnl_flatten is None:
                    funnel["flatten_unquotable_single_side"] += 1
            models[model] = {
                "filled_yes": fy["filled"], "filled_no": fn["filled"],
                "departures_yes": fy["cumulative_departures"],
                "departures_no": fn["cumulative_departures"],
                "fill_category": category,
                "frozen_both_ladders": fy["frozen"] and fn["frozen"],
                "pnl_both_fill": pnl_both,
                "pnl_strategy_level": pnl_strategy,
                # L256 -- the honest exit treatment, reported beside the generous one
                "pnl_strategy_flatten": pnl_flatten,
                "flatten_price": flat_price,
                "flatten_price_source_tag": (None if flat_price is None else "real_ask"),
            }

        mids = [book_mid(s2["record"]) for s2 in snaps]
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
            "price_offset": float(price_offset),
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
            "price_source_tag": ("real_bid(fills)+real_bid(queue)+broker_truth(settlement)"
                                 "+real_ask(flatten_exit)"),
        })
    return trades, funnel


def distinct_entry_timestamps(trades: Sequence[dict]) -> int:
    """L251 artifact measure: how many DISTINCT capture instants the population's entries sit
    on. 1 means every 'candidate' was rested at the same moment (a tape-start artifact)."""
    return len({t["entry_captured_at"] for t in trades})


# --------------------------------------------------------------------------- #
# The three robustness attacks — RE-RUNNABLE CODE, not prose
#
# Provenance note (2026-08-01, post-verifier). These three checks were originally reported in
# `findings/2026-08-01-q50-s68-tighter-gate-rederivation.md` as prose with no code behind them;
# a verifier had to re-derive them by hand to confirm they were true, and found the longshot CI
# had been computed at an undisclosed n_boot=4000 while the headline used 10,000. Per the repo's
# own trust default ("no claim without a re-runnable script"), they are code now, they default to
# the SAME n_boot as the headline, and every result dict carries its own `n_boot`.
#
# They are ATTACKS THAT FAILED TO KILL THE CELL. None of them is evidence FOR an edge — the cell
# they are run against is DEAD on OTHER evidence: the flatten-at-cross exit treatment of the
# unhedged single-side legs (L256 — now `flatten_analysis`/`flatten_at_cross_pnl` in this
# module, folded into `cell_verdict` as the worse-of-two, no longer the hand-run verifier
# derivation this comment used to cite), a zero-information "mid-as-truth" control that
# reproduces the same CI shape and sign (L255 — still verifier-hand-run, NOT code here, and
# therefore still an open L165 provenance hole), and the L253 blindness caveat bounds all three
# of these attacks anyway. Published so they are not re-run.
# --------------------------------------------------------------------------- #
def strategy_units_by_series(trades: Sequence[dict],
                             model: str = PRIMARY_FILL_MODEL) -> Dict[str, List[float]]:
    """The L249-correct bootstrap object, grouped by the L6/L41 unit (GAME-SERIES)."""
    units: Dict[str, List[float]] = {}
    for t in trades:
        units.setdefault(t["series"], []).append(float(t["models"][model]["pnl_strategy_level"]))
    return units


def _boot_row(units: Dict[str, List[float]], n_boot: int) -> Dict[str, Any]:
    from core.bootstrap import (block_bootstrap, bootstrap_verdict_admissible,
                                clears_tick_magnitude)
    b = block_bootstrap(units, n_boot=n_boot)
    adm = bootstrap_verdict_admissible(units, min_units=MIN_CI_UNITS)
    lo = b["ci95"][0]
    return {"mean": b["mean"], "ci95": b["ci95"], "n_units_series": b["n_units"],
            "n_obs": b["n_obs"], "n_boot": n_boot, "admissible": adm,
            "ci_lower_positive": lo is not None and lo > 0.0,
            "clears_tick_magnitude": clears_tick_magnitude(b["ci95"], tick=PRICE_TICK,
                                                           min_ticks=1.0)}


def leave_one_series_out(trades: Sequence[dict], model: str = PRIMARY_FILL_MODEL,
                         n_boot: int = 10000) -> Dict[str, Any]:
    """L57's jackknife: drop each GAME-SERIES in turn and re-bootstrap the remaining units.

    A CI carried by a single series is a one-unit result wearing a bootstrap's clothes. Reports
    every drop, plus how many drops keep the lower bound strictly > 0 (and how many additionally
    clear the L27 one-tick gate). `n_boot` is echoed on every row."""
    units = strategy_units_by_series(trades, model)
    full = _boot_row(units, n_boot)
    drops: List[Dict[str, Any]] = []
    for s in sorted(units):
        remaining = {k: v for k, v in units.items() if k != s}
        row = _boot_row(remaining, n_boot)
        row["dropped_series"] = s
        row["n_obs_dropped"] = len(units[s])
        drops.append(row)
    positive = [d for d in drops if d["ci_lower_positive"]]
    clearing = [d for d in drops if d["ci_lower_positive"] and d["clears_tick_magnitude"]]
    lows = [d["ci95"][0] for d in drops if d["ci95"][0] is not None]
    return {
        "attack": "leave_one_series_out",
        "n_boot": n_boot,
        "full_population": full,
        "n_series_dropped_one_at_a_time": len(drops),
        "n_drops_ci_lower_positive": len(positive),
        "n_drops_clearing_tick_gate": len(clearing),
        "all_drops_keep_ci_positive": len(positive) == len(drops) and bool(drops),
        "min_ci_lower_over_drops": min(lows) if lows else None,
        "max_ci_lower_over_drops": max(lows) if lows else None,
        "drops": drops,
        "note": ("an attack that FAILED to kill the cell; it is not evidence for an edge — "
                 "the cell dies to the flatten-at-cross exit treatment (L256) and is "
                 "reproduced by the zero-information mid-as-truth control (L255)"),
    }


def single_side_fill_price(trade: dict, model: str = PRIMARY_FILL_MODEL) -> Optional[float]:
    """The price of the UNHEDGED leg for a single-side fill; None for a double fill or a
    no-fill (which are not single-side positions and are never dropped by the longshot attack)."""
    cat = trade["models"][model]["fill_category"]
    if cat == "yes_only":
        return float(trade["yes_fill_price"])
    if cat == "no_only":
        return float(trade["no_fill_price"])
    return None


def drop_longshot_single_side(trades: Sequence[dict], model: str = PRIMARY_FILL_MODEL,
                              n_boot: int = 10000,
                              max_price: float = LONGSHOT_MAX_PRICE) -> Dict[str, Any]:
    """Is the cell just a longshot lottery?  Drop every candidate whose realized fill is an
    UNHEDGED single-side leg priced at or below `max_price` (cheap tickets whose rare $1 payout
    is what a tail-driven mean is made of) and re-bootstrap what is left.

    Double fills and no-fills are retained — they are not single-side positions. The dropped
    UNITS are dropped whole (never zeroed: L86 — zeroing a leg fabricates a free outcome)."""
    kept, dropped = [], []
    for t in trades:
        p = single_side_fill_price(t, model)
        (dropped if (p is not None and p <= max_price + _EPS) else kept).append(t)
    return {
        "attack": "drop_longshot_single_side",
        "n_boot": n_boot,
        "max_price_dropped": max_price,
        "n_trades_in": len(trades),
        "n_dropped": len(dropped),
        "n_kept": len(kept),
        "dropped_mean_pnl": _mean_or_none(
            [float(t["models"][model]["pnl_strategy_level"]) for t in dropped]),
        "bootstrap_after_drop": _boot_row(strategy_units_by_series(kept, model), n_boot),
        "note": ("an attack that FAILED to kill the cell; the retained population is still "
                 "tail-shaped and still bounded by the unmeasurable adverse-selection term "
                 "(L253)"),
    }


def price_offset_placebo(per_ticker: Dict[str, List[dict]], settlement: Dict[str, dict],
                         horizon_hours: Optional[float], extra_ticks: int,
                         model: str = PRIMARY_FILL_MODEL, n_boot: int = 10000,
                         offset: float = PLACEBO_OFFSET) -> Dict[str, Any]:
    """Is the `touch` fill model price-sensitive, or is it a generic churn detector?

    Re-rests the SAME admitted books `offset` away from the entry best bid (default two ticks
    BELOW it) and re-simulates. A model with real price priority must see leg fill rates
    collapse; a model that merely counts book churn would not notice. This is a discrimination
    check on the INSTRUMENT — a collapse is a point in the fill model's favour and says nothing
    about whether the strategy has an edge."""
    base, base_funnel = build_trades_at(per_ticker, settlement, horizon_hours, extra_ticks, 0.0)
    plac, plac_funnel = build_trades_at(per_ticker, settlement, horizon_hours, extra_ticks,
                                        offset)

    def rates(trades: Sequence[dict]) -> Dict[str, Any]:
        n = len(trades)
        return {
            "n_candidates": n,
            "yes_leg_fill_rate": (sum(1 for t in trades
                                      if t["models"][model]["filled_yes"]) / n) if n else None,
            "no_leg_fill_rate": (sum(1 for t in trades
                                     if t["models"][model]["filled_no"]) / n) if n else None,
            "both_fill_rate": (sum(1 for t in trades
                                   if t["models"][model]["fill_category"] == "both")
                               / n) if n else None,
        }

    return {
        "attack": "price_offset_placebo",
        "n_boot": n_boot,
        "offset": offset,
        "fill_model": model,
        "baseline": rates(base),
        "placebo": rates(plac),
        "placebo_dropped_non_positive_price": plac_funnel["offset_price_non_positive"],
        "baseline_funnel": base_funnel,
        "bootstrap_placebo": _boot_row(strategy_units_by_series(plac, model), n_boot),
        "fill_rate_collapsed": _rates_collapsed(rates(base), rates(plac)),
        "note": ("a discrimination check on the FILL MODEL, not on the strategy: a collapse "
                 "shows `touch` respects price priority (L250), nothing more"),
    }


def _rates_collapsed(base: Dict[str, Any], plac: Dict[str, Any],
                     factor: float = 0.5) -> bool:
    """True when BOTH leg fill rates fall to below `factor` x their baseline under the placebo
    price. False (not an exception) when either rate is unmeasurable."""
    for k in ("yes_leg_fill_rate", "no_leg_fill_rate"):
        b, p = base.get(k), plac.get(k)
        if b is None or p is None or b <= 0.0:
            return False
        if p >= factor * b:
            return False
    return True


def _mean_or_none(xs: Sequence[float]) -> Optional[float]:
    return (sum(xs) / len(xs)) if xs else None


def run_robustness(per_ticker: Dict[str, List[dict]], settlement: Dict[str, dict],
                   horizon_hours: Optional[float] = HEADLINE_HORIZON_H,
                   extra_ticks: int = HEADLINE_GATE_TICKS,
                   model: str = PRIMARY_FILL_MODEL, n_boot: int = 10000) -> Dict[str, Any]:
    """All three attacks against ONE cell, at the SAME `n_boot` as the headline (the defect a
    verifier caught: the original longshot CI was silently computed at n_boot=4000)."""
    trades, funnel = build_trades_at(per_ticker, settlement, horizon_hours, extra_ticks, 0.0)
    return {
        "cell": {"horizon_hours": horizon_hours, "gate_extra_ticks": extra_ticks,
                 "fill_model": model, "n_candidates": len(trades),
                 "n_series": len({t["series"] for t in trades}),
                 "n_games": len({t["event_ticker"] for t in trades}),
                 "n_distinct_entry_timestamps": distinct_entry_timestamps(trades),
                 "median_ttc_hours_entry": _median_or_none(
                     [float(t["ttc_hours_entry"]) for t in trades]),
                 "median_entry_spread": _median_or_none(
                     [float(t["entry_spread"]) for t in trades]),
                 "funnel": funnel},
        "n_boot": n_boot,
        "bootstrap_unit": "game_series (L6/L41)",
        "price_source_tags": {"fills": "real_bid", "queue_depth": "real_bid",
                              "settlement": "broker_truth"},
        "headline": _boot_row(strategy_units_by_series(trades, model), n_boot),
        "leave_one_series_out": leave_one_series_out(trades, model, n_boot),
        "drop_longshot_single_side": drop_longshot_single_side(trades, model, n_boot),
        "price_offset_placebo": price_offset_placebo(per_ticker, settlement, horizon_hours,
                                                     extra_ticks, model, n_boot),
        "interpretation": ("ALL THREE ARE ATTACKS THAT FAILED. None is evidence for an edge. "
                           "The cell is DEAD on other evidence: flatten-at-cross on the "
                           "unhedged legs leaves the CI straddling zero (L256), a "
                           "zero-information mid-as-truth control reproduces the same CI shape "
                           "(L255), the estimate is monotone in the entry horizon and negative "
                           "in the near-close windows (L254 — a spread-regime difference: the "
                           "wide-spread population does not exist near close), and the verdict "
                           "sits inside an adverse-selection term this depth-only tape cannot "
                           "measure (L253)."),
    }


def print_robustness(rob: Dict[str, Any]) -> None:
    c = rob["cell"]
    nb = rob["n_boot"]
    print("=" * 100)
    print(f"ROBUSTNESS — attacks against H={c['horizon_hours']} N={c['gate_extra_ticks']} "
          f"({c['n_candidates']} candidates / {c['n_series']} series / {c['n_games']} games, "
          f"model={c['fill_model']})")
    print(f"n_boot = {nb} for EVERY number below (same as the headline — no silent drift)")
    print("=" * 100)
    h = rob["headline"]
    print(f"headline                 : mean {_f(h['mean'])} CI {_ci(h['ci95'])} "
          f"units={h['n_units_series']} n={h['n_obs']} n_boot={h['n_boot']}")
    print(f"median entry ttc         : {_f(c['median_ttc_hours_entry'], 2)}h   "
          f"median entry spread: {_f(c['median_entry_spread'])}")
    loo = rob["leave_one_series_out"]
    print(f"leave-one-series-out     : {loo['n_drops_ci_lower_positive']}/"
          f"{loo['n_series_dropped_one_at_a_time']} drops keep CI lower bound > 0 "
          f"({loo['n_drops_clearing_tick_gate']} also clear the L27 tick gate); "
          f"worst lower bound {_f(loo['min_ci_lower_over_drops'])}  n_boot={loo['n_boot']}")
    for d in loo["drops"]:
        print(f"    drop {d['dropped_series']:<14} n={d['n_obs_dropped']:>3} -> "
              f"mean {_f(d['mean'])} CI {_ci(d['ci95'])}")
    ls = rob["drop_longshot_single_side"]
    b = ls["bootstrap_after_drop"]
    print(f"longshot-drop (<= ${ls['max_price_dropped']:.2f} single-side): dropped "
          f"{ls['n_dropped']}/{ls['n_trades_in']} -> mean {_f(b['mean'])} CI {_ci(b['ci95'])} "
          f"units={b['n_units_series']} n={b['n_obs']} n_boot={b['n_boot']}")
    pp = rob["price_offset_placebo"]
    bl, pl = pp["baseline"], pp["placebo"]
    print(f"price-offset placebo ({pp['offset']:+.2f}) : leg fill rates "
          f"yes {_pct(bl['yes_leg_fill_rate'])} -> {_pct(pl['yes_leg_fill_rate'])}, "
          f"no {_pct(bl['no_leg_fill_rate'])} -> {_pct(pl['no_leg_fill_rate'])}, "
          f"both {_pct(bl['both_fill_rate'])} -> {_pct(pl['both_fill_rate'])} "
          f"[collapsed={pp['fill_rate_collapsed']}]")
    print()
    print(rob["interpretation"])


def _pct(x: Optional[float]) -> str:
    return "n/a" if x is None else f"{x * 100:.0f}%"


# --------------------------------------------------------------------------- #
# Per-cell verdict
# --------------------------------------------------------------------------- #
#: How bad each verdict is. `cell_verdict` takes the MAX over the two exit treatments, so the
#: WORSE branch always wins (L256). ALIVE is the least severe answer, never a tiebreak winner.
VERDICT_SEVERITY: Dict[str, int] = {
    "ALIVE-CANDIDATE": 0,
    "DEAD-by-magnitude": 1,
    "DEAD-by-CI": 2,
    "DEAD-by-adequacy": 3,
}


def branch_verdict(n_candidates: int, strat: Dict[str, Any], clears_tick: bool,
                   label: str) -> Tuple[str, str]:
    """The kill ladder applied to ONE exit treatment's strategy-level bootstrap.

    Order matters: an empty/thin population is a DATA-ADEQUACY answer and must never be
    dressed up as a CI falsification (L53/L43)."""
    if n_candidates == 0:
        return "DEAD-by-adequacy", f"{label}: empty_population"
    n_units = strat["n_units_series"]
    if n_units is None or n_units < MIN_CI_UNITS:
        return ("DEAD-by-adequacy",
                f"{label}: n_units_series={n_units} < {MIN_CI_UNITS} (L41 floor)")
    if not strat["admissible"]["admissible"]:
        return ("DEAD-by-adequacy",
                f"{label}: bootstrap inadmissible: {','.join(strat['admissible']['reasons'])}")
    lo = strat["ci95"][0]
    if lo is None or lo <= 0.0:
        return "DEAD-by-CI", f"{label}: strategy-level 95% CI lower bound {lo} not > 0"
    if not clears_tick:
        return "DEAD-by-magnitude", f"{label}: CI positive but below one fillable tick (L27)"
    return "ALIVE-CANDIDATE", f"{label}: admissible strategy-level CI > 0 clearing the tick gate"


def cell_verdict(cell: Dict[str, Any]) -> Tuple[str, str]:
    """The kill ladder for ONE (N, H) cell, applied to the L249-correct object (the
    strategy-level bootstrap) under BOTH exit treatments, returning the WORSE of the two.

    **L256 is enforced here, in code, not in a comment.** A single-side fill leaves an
    unhedged position; marking it to `broker_truth` settlement (`hold_to_settlement`) is the
    most generous possible treatment, and a cell that survives ONLY that branch has not
    survived anything. The flatten-at-cross branch (`flatten_analysis`) is therefore a
    REQUIRED key: `cell_verdict` raises rather than quietly falling back to the generous
    branch, so the honest treatment cannot be dropped by a future refactor without the suite
    going red. That absence-of-fallback is the assertable half of the lesson."""
    a = cell["analysis"]
    n = a["n_candidates"]
    hold = branch_verdict(n, a["bootstrap_strategy_level_diagnostic"],
                          cell["clears_tick_magnitude_strategy"], "hold_to_settlement")
    if "flatten_at_cross" not in cell:
        raise KeyError(
            "cell is missing its `flatten_at_cross` branch — L256 requires BOTH exit "
            "treatments before any verdict is issued; there is no generous-branch fallback")
    flat_a = cell["flatten_at_cross"]
    flat = branch_verdict(n, flat_a, flat_a["clears_tick_magnitude"], "flatten_at_cross")
    worse = max((hold, flat), key=lambda vr: VERDICT_SEVERITY[vr[0]])
    if hold[0] == flat[0] == "ALIVE-CANDIDATE":
        return "ALIVE-CANDIDATE", ("BOTH exit treatments admissible, CI > 0, clearing the tick "
                                   "gate (L256 worse-of-two)")
    return worse[0], f"{worse[1]} [L256 worse-of-two; hold={hold[0]} flatten={flat[0]}]"


def run(depth_glob: str = DEPTH_GLOB, settlement_glob: str = SETTLEMENT_GLOB,
        gate_ticks: Sequence[int] = DEFAULT_GATE_TICKS,
        horizons: Sequence[Optional[float]] = DEFAULT_HORIZONS_H,
        model: str = PRIMARY_FILL_MODEL, n_boot: int = 10000,
        robustness: bool = True,
        robustness_cell: Tuple[Optional[float], int] = (HEADLINE_HORIZON_H,
                                                        HEADLINE_GATE_TICKS)) -> Dict[str, Any]:
    """Load the tape once, then sweep the (N, H) ladder. READ-ONLY.

    `robustness=True` (default) additionally runs the three published attacks against
    `robustness_cell` at the SAME `n_boot`, so a re-run reproduces them from code rather than
    from the finding's prose."""
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
                # the SPREAD REGIME of the cell's own entry books. Load-bearing for L254's
                # corrected mechanism: the near-close cells sit at ~2 ticks (the Q49 fee
                # boundary) while every CI>0 cell sits at 6-7 ticks — i.e. the wide-spread
                # population this ladder is built to find does not exist near close.
                "median_entry_spread": _median_or_none(
                    [float(t["entry_spread"]) for t in trades]),
                "median_ttc_hours_entry": _median_or_none(
                    [float(t["ttc_hours_entry"]) for t in trades]),
                "entry_timestamp_artifact_flag": (
                    len(trades) > 0
                    and distinct_entry_timestamps(trades) < MIN_DISTINCT_ENTRY_TS),
                "clears_tick_magnitude_strategy": clears_tick_magnitude(
                    strat_ci, tick=PRICE_TICK, min_ticks=1.0),
                "markouts_by_k": aggregate_markouts(trades),
                "adverse_selection_breakeven": adverse_selection_breakeven(
                    trades, model, n_boot=n_boot),
                # L256 -- the honest exit treatment. Required by `cell_verdict`.
                "flatten_at_cross": flatten_analysis(trades, model, n_boot=n_boot),
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
                row["pnl_strategy_flatten"] = t["models"][model]["pnl_strategy_flatten"]
                row["flatten_price"] = t["models"][model]["flatten_price"]
                row["flatten_price_source_tag"] = (
                    t["models"][model]["flatten_price_source_tag"])
                row["pnl_both_fill"] = t["models"][model]["pnl_both_fill"]
                row["fill_model"] = model
                all_rows.append(row)

    alive = [c for c in cells if c["verdict"] == "ALIVE-CANDIDATE"]
    rob = (run_robustness(per_ticker, settlement, robustness_cell[0], robustness_cell[1],
                          model=model, n_boot=n_boot) if robustness else None)
    return {
        "probe": "q50_s68_gate_ladder",
        "question": ("does the S68 both-bid maker capture clear a block-bootstrapped-by-series "
                     "95% CI > 0 under a fees-plus-N-ticks gate (L252) and the "
                     "first-snapshot-with-ttc<=H entry rule (L251)?"),
        "bootstrapped_object": ("strategy_level_pnl (double fill = realized capture; "
                                "single-side fill = unhedged directional position marked to "
                                "broker_truth settlement; no fill = 0) — L249"),
        "exit_treatment_note": ("EVERY cell is bootstrapped under BOTH exit treatments and its "
                                "verdict is the WORSE of the two (L256): hold_to_settlement "
                                "marks an orphan single-side leg to the broker_truth payout "
                                "(most generous); flatten_at_cross closes it by lifting the "
                                "other side's real ask (maker fee in, TAKER fee out). A cell "
                                "that is ALIVE only under hold_to_settlement is not ALIVE."),
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
        "robustness": rob,
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
           f"{'medSpd':>7} {'both%':>7} {'meanPnL':>9} {'CI95(strategy)':>21} {'adm':>4} "
           f"{'tick':>5}  verdict")
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
              f"{_f(c['median_entry_spread'], 3):>7} "
              f"{('n/a' if bf is None else f'{bf * 100:.1f}%'):>7} "
              f"{_f(st['mean']):>9} {_ci(st['ci95']):>21} "
              f"{'Y' if st['admissible']['admissible'] else 'N':>4} "
              f"{'Y' if c['clears_tick_magnitude_strategy'] else 'N':>5}  "
              f"{c['verdict']} ({c['verdict_reason']})")
    print()
    print("* = entries cluster on < 3 distinct capture instants (L251 tape-start artifact)")
    print()
    print("EXIT TREATMENT — the generous branch above is NOT the verdict on its own (L256):")
    print("  hold_to_settlement = an orphan single-side leg rides to the broker_truth $0/$1")
    print("  payout (a free directional lottery no maker would knowingly keep).")
    print("  flatten_at_cross   = that orphan is CLOSED by lifting the other side's real ask")
    print("  (maker fee in, TAKER fee out). On a mirrored book that has not moved, the exit")
    print("  costs precisely the two fees — a small CERTAIN loss instead of a fat lottery.")
    print("  Every cell's verdict above is already the WORSE of the two branches.")
    fh = (f"{'H':>5} {'N':>2} {'CI95(hold-to-settle)':>21} {'CI95(flatten-at-cross)':>23} "
          f"{'meanHold':>9} {'meanFlat':>9} {'unmeas':>7}  verdict")
    print(fh)
    print("-" * len(fh))
    for c in rep["cells"]:
        st = c["analysis"]["bootstrap_strategy_level_diagnostic"]
        fl = c["flatten_at_cross"]
        print(f"{str(c['horizon_hours']):>5} {c['gate_extra_ticks']:>2} "
              f"{_ci(st['ci95']):>21} {_ci(fl['ci95']):>23} "
              f"{_f(st['mean']):>9} {_f(fl['mean']):>9} "
              f"{str(fl['n_unmeasurable_single_side']) + '/' + str(fl['n_single_side_legs']):>7}"
              f"  {c['verdict']}")
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
    print(f"  (break-even ladder bootstrapped at n_boot={rep['n_boot']}, same as the headline)")
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
    if rep.get("robustness"):
        print_robustness(rep["robustness"])
        print()
    print(f"OVERALL: {rep['overall_verdict']}")


def _repo_relative(path: str) -> str:
    """`path` expressed relative to the repo root when it lives inside it, else unchanged — a
    committed report must not record one machine's absolute filesystem layout."""
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


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
    ap.add_argument("--robustness-out", default=str(ROBUSTNESS_OUT))
    ap.add_argument("--no-robustness", action="store_true",
                    help="skip the three published attacks (they run by default)")
    ap.add_argument("--robustness-only", action="store_true",
                    help="run ONLY the three attacks against the headline cell (no 35-cell "
                         "ladder) — fast re-verification path")
    ap.add_argument("--robustness-horizon", type=float, default=HEADLINE_HORIZON_H)
    ap.add_argument("--robustness-ticks", type=int, default=HEADLINE_GATE_TICKS)
    ap.add_argument("--no-write", action="store_true", help="report only; write no files")
    args = ap.parse_args(argv)

    gate_ticks = [int(x) for x in args.gate_ticks.split(",") if x.strip()]
    horizons: List[Optional[float]] = [float(x) for x in args.horizons.split(",") if x.strip()]

    if args.robustness_only:
        settlement, _ = load_settlements(args.settlement_glob)
        per_ticker, _ = load_preclose_snapshots(args.depth_glob, settlement)
        rob = run_robustness(per_ticker, settlement, args.robustness_horizon,
                             args.robustness_ticks, model=args.fill_model, n_boot=args.n_boot)
        print_robustness(rob)
        if not args.no_write:
            Path(args.robustness_out).parent.mkdir(parents=True, exist_ok=True)
            with open(args.robustness_out, "w", encoding="utf-8") as f:
                json.dump(rob, f, indent=2, sort_keys=True, default=str)
            print(f"\nwrote {args.robustness_out}")
        return 0

    rep = run(depth_glob=args.depth_glob, settlement_glob=args.settlement_glob,
              gate_ticks=gate_ticks, horizons=horizons, model=args.fill_model,
              n_boot=args.n_boot, robustness=not args.no_robustness,
              robustness_cell=(args.robustness_horizon, args.robustness_ticks))
    print_report(rep)

    if not args.no_write:
        rows = rep.pop("rows")
        rob = rep.pop("robustness")
        # repo-RELATIVE when it sits under the repo, so a committed artifact never carries one
        # machine's absolute paths
        rep["robustness_artifact"] = (_repo_relative(args.robustness_out)
                                      if rob is not None else None)
        Path(args.rows_out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.rows_out, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, sort_keys=True) + "\n")
        with open(args.summary_out, "w", encoding="utf-8") as f:
            json.dump(rep, f, indent=2, sort_keys=True, default=str)
        print(f"\nwrote {args.rows_out} ({len(rows)} rows) and {args.summary_out}")
        if rob is not None:
            with open(args.robustness_out, "w", encoding="utf-8") as f:
                json.dump(rob, f, indent=2, sort_keys=True, default=str)
            print(f"wrote {args.robustness_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
