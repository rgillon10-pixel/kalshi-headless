#!/usr/bin/env python3
"""q39_graveyard_counterfactual_sweep.py — Q39: the graveyard counterfactual sweep.

LOOP-QUEUE.md Q39 (loop-improvement #1). GENERALIZES `scripts/q35_maker_rebate_reframe.py`
(which flipped 2/5 fee-killed MAKERS on a maker-rebate venue) into a systematic counterfactual
MATRIX across the repo's dead-strategy graveyard, answering one question:

    which venue / fee configuration flips the most DEAD strategies from DEAD to
    CI>0-AND-clears-the-tick-gate — i.e. have we been fishing on the wrong venue?

Every strategy whose simulate function exists as an importable module is re-run over its
EXISTING committed tape/cache (imported as a module — NO network, NO live fetch, NO tape
mutation) and its per-unit P&L is re-priced under a matrix of counterfactual FEE lines:

  as_is                  Kalshi fee/rebate as verdicted — the CORRECTNESS CHECK (must
                         reproduce each strategy's own committed simulation)
  pm_maker_rebate_0.5c   Kalshi maker fee REMOVED + a flat +$0.005/contract rebate ADDED
  pm_maker_rebate_1.25c  Kalshi maker fee REMOVED + a flat +$0.0125/contract rebate ADDED
  pm_taker_fee           Kalshi taker fee REMOVED + Polymarket-US taker fee ADDED per leg
                         (core.pricing.polymarket_fee_per_contract @ POLYMARKET_US_TAKER_RATE)
  zero_fee               all original fees REMOVED — the theoretical floor bounding the
                         maximum possible fee-line lift

Only the fee LINE changes; every other leg (premium, $1 settlement, half-spread) is untouched.
Fees come ONLY from `core.pricing` — never hand-rolled (L18). Each config's per-unit series is
block-bootstrapped (`core.bootstrap.block_bootstrap`) on the SAME unit each source strategy
blocked on (GAME / EVENT-hour / TICKER / matched-PAIR — L6), and any positive CI is routed
through `core.bootstrap.clears_tick_magnitude` (L27) before it can count as a "flip".

RUTHLESS SCOPE HONESTY (the whole point). A fee change can only revive a death that happened
ON THE FEE LINE. Every strategy is classified:
  * FLIPS                 a fee config turns DEAD -> CI strictly >0 AND clears the tick gate
                          (a fee-line CANDIDATE, never a proven edge)
  * fee-line marginal     a fee config lifts the mean positive but the CI straddles zero or the
                          lower bound is below the 1¢ tick-magnitude gate (L27)
  * lost by MORE          strictly negative even at zero_fee — the loss exceeds the entire fee
                          line; a fee change CANNOT revive it (report the residual gap)
  * data-adequacy dead    <10 block units — untestable as collected (needs new tape, not a fee)
  * NOT-fee-revivable by construction — died on fillability / calibration / cadence / a
                          structural price floor, so NO fee counterfactual is even run (running
                          one would be misleading). Reason stated per strategy.

S29 REUSE (Q35's two-agent-verifier catch, 2026-07-16): each strategy is fed its finding's
ACTUAL dead-basis population, never a disowned raw population — S6 the movement-conditioned
tight-<=10c cut (L32: a frozen no-fill earns NO rebate either, so booking the frozen-inclusive
cut would credit rebate income on fills that never happened); S29 the two-sided-book entry cut
(reused verbatim from q35). Feeding the raw earliest-entry / frozen-inclusive population into a
fee reframe would silently resurrect an artifact this project's own verifier already refuted.

A fee-line CI flip is a CANDIDATE, NOT a proven edge. Each still owes the two-agent verifier +
a Milestone-B real-venue bar (portability, resolution-basis, capital friction, the full
real-ask CI). This script touches NO registry (kb/strategies/00-index.md) and makes NO status
decision. Read-only. Run:
    python scripts/q39_graveyard_counterfactual_sweep.py
    python scripts/q39_graveyard_counterfactual_sweep.py --n-boot 10000 --json-out /tmp/q39.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import namedtuple
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.bootstrap import block_bootstrap, clears_tick_magnitude  # noqa: E402
from core.pricing import (  # noqa: E402
    MAKER_FEE_RATE,
    TAKER_FEE_RATE,
    fee_per_contract,
    polymarket_fee_per_contract,
)

# ── Counterfactual fee-line constants (INDICATIVE for the rebates, pool-funded — NOT sanctioned
# core rates; the Polymarket taker rate IS a core.pricing constant). Same provenance as Q35:
# LOOP-QUEUE.md 2026-07-15 regime-change note (~+0.5c conservative, ~+1.25c Polymarket-US). ──
PM_MAKER_REBATE_CONSERVATIVE = 0.005   # +$0.005/contract maker rebate (conservative)
PM_MAKER_REBATE_US = 0.0125            # +$0.0125/contract maker rebate (Polymarket-US figure)

PRICE_TICK = 0.01
MIN_CI_UNITS = 10  # shared data-adequacy floor (S19/Q24/Q27/Q30/S24 all use it)

# Config identifiers. A strategy declares which subset applies to its FAMILY:
#   maker family      -> the rebate configs are meaningful (a resting fill earns a rebate)
#   taker family      -> the Polymarket-taker-fee counterfactual is meaningful
#   cross-venue (S34) -> only as_is + zero_fee (its as_is already mixes Kalshi + PM fees;
#                        re-pricing one leg at the other venue's rate would be nonsense)
AS_IS = "as_is"
REBATE_LO = "pm_maker_rebate_0.5c"
REBATE_HI = "pm_maker_rebate_1.25c"
PM_TAKER = "pm_taker_fee"
ZERO_FEE = "zero_fee"
ALL_CONFIGS = [AS_IS, REBATE_LO, REBATE_HI, PM_TAKER, ZERO_FEE]
MAKER_CONFIGS = [AS_IS, REBATE_LO, REBATE_HI, ZERO_FEE]
TAKER_CONFIGS = [AS_IS, PM_TAKER, ZERO_FEE]
CROSS_VENUE_CONFIGS = [AS_IS, ZERO_FEE]
REBATES = {REBATE_LO: PM_MAKER_REBATE_CONSERVATIVE, REBATE_HI: PM_MAKER_REBATE_US}

# A per-unit observation. `legs` is the list of (price, original_fee) for every fee-charged leg
# in the as_is P&L: one leg for a single maker/taker fill, two for a taker round-trip (enter +
# exit). `price` may be None for a maker unit reused from Q35 (the maker rebate/zero configs
# never read a leg price — only pm_taker does, and it never applies to a maker).
Unit = namedtuple("Unit", ["block_key", "as_is_pnl", "legs"])


# --------------------------------------------------------------------------- #
# the one new helper this milestone adds (offline unit-tested): the general fee-swap
# --------------------------------------------------------------------------- #
def apply_fee_config(as_is_pnl: float, legs: List[Tuple[Optional[float], float]],
                     config: str) -> float:
    """Re-price an as_is (Kalshi-fee) P&L onto a counterfactual fee line.

    The as_is P&L had each leg's `original_fee` (a POSITIVE dollar cost) SUBTRACTED. Every
    config first ADDS BACK the full original fee line (removing the Kalshi cost) and then applies
    the counterfactual's own fee/rebate:

      as_is                 -> unchanged (the correctness column)
      zero_fee              -> as_is + Σ original_fee                 (theoretical fee-free floor)
      pm_maker_rebate_*     -> as_is + Σ original_fee + rebate·n_legs (fee->income per resting leg)
      pm_taker_fee          -> as_is + Σ original_fee − Σ pm_fee(price) (Polymarket-US taker/leg)

    `legs[i] == (price, original_fee)`. pm_taker needs each leg's `price` (to recompute the
    Polymarket fee via core.pricing.polymarket_fee_per_contract — never hand-rolled); it raises
    on a None price so a maker unit can never silently take the taker branch. Nothing but the
    fee LINE moves — the entire point of the counterfactual.
    """
    orig_total = sum(f for _, f in legs)
    if config == AS_IS:
        return float(as_is_pnl)
    if config == ZERO_FEE:
        return float(as_is_pnl) + orig_total
    if config in REBATES:
        return float(as_is_pnl) + orig_total + REBATES[config] * len(legs)
    if config == PM_TAKER:
        new_total = 0.0
        for price, _ in legs:
            if price is None:
                raise ValueError("pm_taker_fee requires each leg's price (got None); it never "
                                 "applies to a maker unit")
            new_total += polymarket_fee_per_contract(float(price))
        return float(as_is_pnl) + orig_total - new_total
    raise ValueError(f"unknown fee config {config!r}")


# --------------------------------------------------------------------------- #
# collectors — reuse each source script's OWN simulate/aggregation, offline.
# Maker collectors are reused VERBATIM from q35 (inheriting its S29 two-sided-book fix) and
# wrapped into Units; the taker + cross-venue collectors are new and carry real leg prices.
# --------------------------------------------------------------------------- #
def _wrap_maker(units3: List[Tuple[str, float, float]]) -> List[Unit]:
    """A q35 maker collector returns (block_key, as_is_pnl, kalshi_maker_fee) triples. Wrap each
    into a Unit with a single fee-charged leg; price is None (maker configs never read it)."""
    return [Unit(k, pnl, [(None, fee)]) for k, pnl, fee in units3]


def collect_s6() -> Tuple[List[Unit], Dict[str, Any]]:
    """S6 — inventory-aware maker spread capture. Block unit = TICKER (L6). Population = the
    MOVEMENT-CONDITIONED tight-<=10c cut (a fill plausibly occurred), NOT the frozen-inclusive
    cut: on a rebate venue a frozen no-fill earns NO rebate, so crediting frozen pairs would
    manufacture rebate income on fills that never happened (L32; the S29-lesson generalized)."""
    from scripts import s6_maker_firstcut as s6

    pairs = s6.build_pairs(s6.load_records())
    cap = s6.PRIMARY_SPREAD_CAP_CENTS
    sel = [p for p in pairs if p.spread_cents <= cap and p.moved]
    units = [Unit(p.ticker, p.net, [(p.fill_price, p.maker_fee)]) for p in sel]
    meta = {"block_unit": "ticker", "family": "maker",
            "population": ("movement-conditioned tight <=%dc (L32 honest fill basis; the "
                           "frozen-inclusive cut would credit rebate on no-fills)" % cap),
            "n_pairs": len(sel)}
    return units, meta


def collect_s13() -> Tuple[List[Unit], Dict[str, Any]]:
    """S13 — sports maker bid at DK-devig fair-1c. Block unit = GAME. Reused from q35."""
    from scripts.q35_maker_rebate_reframe import collect_s13 as q35_s13
    units3, meta = q35_s13()
    meta = {**meta, "family": "maker"}
    return _wrap_maker(units3), meta


def collect_s19() -> Tuple[List[Unit], Dict[str, Any]]:
    """S19 — crypto wing-fade maker short. Block unit = EVENT-hour. Reused from q35.
    (Known data-adequacy dead: only ~2 filled event-hours; the adequacy gate marks it.)"""
    from scripts.q35_maker_rebate_reframe import collect_s19 as q35_s19
    units3, meta = q35_s19()
    meta = {**meta, "family": "maker"}
    return _wrap_maker(units3), meta


def collect_s21() -> Tuple[List[Unit], Dict[str, Any]]:
    """S21 — sports-longshot maker rich-ask. Block unit = GAME. Reused from q35.
    (Known data-adequacy dead: 0/81 joinable, L9 non-overlap; the adequacy gate marks it.)"""
    from scripts.q35_maker_rebate_reframe import collect_s21 as q35_s21
    units3, meta = q35_s21()
    meta = {**meta, "family": "maker"}
    return _wrap_maker(units3), meta


def collect_s23() -> Tuple[List[Unit], Dict[str, Any]]:
    """S23 — favorite-underpricing maker bid. Block unit = GAME. Reused from q35."""
    from scripts.q35_maker_rebate_reframe import collect_s23 as q35_s23
    units3, meta = q35_s23()
    meta = {**meta, "family": "maker"}
    return _wrap_maker(units3), meta


def collect_s29() -> Tuple[List[Unit], Dict[str, Any]]:
    """S29 — soccer draw-aversion maker bid. Block unit = GAME. Reused from q35 (two-sided-book
    entry cut — the finding's actual DEAD basis, not the disowned raw earliest-entry headline)."""
    from scripts.q35_maker_rebate_reframe import collect_s29 as q35_s29
    units3, meta = q35_s29()
    meta = {**meta, "family": "maker"}
    return _wrap_maker(units3), meta


def collect_s24() -> Tuple[List[Unit], Dict[str, Any]]:
    """S24 — near-close hourly-return overreaction fade (TAKER round-trip). Block unit = GAME
    (event_ticker, L6). Reuses q28's OWN fade_trades + gate3_roundtrip population verbatim; the
    round-trip charges TWO taker fees (enter at ask, exit at bid), so each Unit carries two legs.
    Entry = real_ask, exit = real_bid."""
    from scripts import q28_s24_nearclose_fade_probe as q28

    settlement = q28.load_settlement_cache(q28.CACHE_PATH)
    paths, _ = q28.load_price_paths(q28.DEPTH_GLOB, settlement)
    trades = [t for path in paths.values()
              for t in q28.fade_trades(path, q28.X_PRIMARY, q28.NEAR_CLOSE_HOURS,
                                       q28.MAX_PAIR_GAP_HOURS)]
    units: List[Unit] = []
    n_excl = 0
    for t in trades:
        # gate3_roundtrip keeps a trade iff BOTH hold_pnl and rt_pnl are non-None (fillable entry
        # AND a realized t+2 exit). Mirror that exact population.
        if t["hold_pnl"] is None or t["rt_pnl"] is None:
            n_excl += 1
            continue
        ea, xb = float(t["entry_ask"]), float(t["exit_bid"])
        fee_in = fee_per_contract(ea, TAKER_FEE_RATE)
        fee_out = fee_per_contract(xb, TAKER_FEE_RATE)
        units.append(Unit(t["event_ticker"], float(t["rt_pnl"]), [(ea, fee_in), (xb, fee_out)]))
    meta = {"block_unit": "game (event_ticker)", "family": "taker",
            "population": "q28 round-trip (enter real_ask, exit real_bid; 2x taker fee)",
            "n_trades": len(units), "n_excluded_unfillable": n_excl}
    return units, meta


def collect_s7c() -> Tuple[List[Unit], Dict[str, Any]]:
    """S7c — sports CLV harvest (TAKER buy of the Kalshi ask vs DK-devig fair). Block unit = GAME
    (kalshi_event_ticker, L6). Reuses s7c.load_games verbatim; per priced outcome the as_is value
    is s7c's own `edge_after_fee` (fair_prob less the pregame ask less the taker fee), a single
    taker leg at `pregame_ask`. It is a mixed real_ask-and-synthetic-devig composite (S7 verdict)."""
    from scripts import s7c_sports_clv_bootstrap as s7c

    games = s7c.load_games()
    units: List[Unit] = []
    for g in games:
        key = g["kalshi_event_ticker"]
        for o in g.get("outcomes", []):
            eaf = o.get("edge_after_fee")
            if eaf is None:
                continue
            ask = float(o["pregame_ask"]["yes_ask"])
            fee = float(o["fee_per_contract"])   # the taker fee that was subtracted (edge_raw-edge)
            units.append(Unit(key, float(eaf), [(ask, fee)]))
    meta = {"block_unit": "game (kalshi_event_ticker)", "family": "taker",
            "population": "s7c priced outcomes (edge_after_fee, single taker leg @ pregame_ask)",
            "n_outcomes": len(units)}
    return units, meta


def collect_s34() -> Tuple[List[Unit], Dict[str, Any]]:
    """S34 — cross-venue two-legged arb (buy Polymarket YES + buy Kalshi NO). Block unit =
    matched PAIR (L6). Reuses q31.load_observations verbatim. Its as_is net_edge already nets
    BOTH venues' taker fees, so the only meaningful counterfactual is zero_fee (does the parity
    death survive removing ALL fees?). Two legs: Kalshi NO (taker) + Polymarket YES (pm taker)."""
    from scripts import q31_cross_venue_arb_probe as q31

    obs = q31.load_observations()
    units: List[Unit] = []
    for o in obs:
        # legs carry the real per-leg fees q31 already computed; zero_fee removes both ->
        # o["gross_edge"] (a built-in cross-check in the tests).
        legs = [(float(o["k_no_ask"]), float(o["kalshi_fee"])),
                (float(o["pm_yes_ask"]), float(o["pm_fee"]))]
        units.append(Unit(o["pair_key"], float(o["net_edge"]), legs))
    meta = {"block_unit": "matched pair (family, kalshi ticker)", "family": "cross_venue",
            "population": "q31 fillable direction (PM YES + Kalshi NO), both real_ask",
            "n_obs": len(units)}
    return units, meta


# Strategies whose deaths are NOT on the fee line — a fee counterfactual would be misleading, so
# NONE is run (per Q39 scope-honesty). Reason cites the finding's actual kill.
NOT_FEE_REVIVABLE: List[Tuple[str, str]] = [
    ("S8 (crypto settlement basis)",
     "died on the rho-guard: settle-vs-spot basis never crosses half a bracket width "
     "(rho 0.9997/0.9998) — a settlement-mechanics kill, fee-invariant"),
    ("S10 (crypto reachability decay)",
     "STRUCTURAL: a 1c-YES-floor mirrors to a $1.00 NO ask (yes_bid=0) so the taker fade has "
     "no fillable price at all; fee_per_contract($1.00)=0 already — a fee change cannot "
     "manufacture a fillable price (L26)"),
    ("S22 (OFI depth-imbalance taker)",
     "died on the directional CALIBRATION precheck (imbalance hit 27.9% vs the mid's 72.1% on "
     "the disagreement subset); gates 3/4 (P&L, bootstrap) were never reached — there is NO "
     "P&L series to re-fee"),
    ("S28 (post-close settlement-lag taker)",
     "data-adequacy: only 4 genuine post-close captures exist and all have an EMPTY book "
     "(Kalshi settles a sports book AT close); no resting-quote window — fee-invariant"),
]


# --------------------------------------------------------------------------- #
# scenario bootstrap + classification
# --------------------------------------------------------------------------- #
def group_by_config(units: List[Unit], config: str) -> Dict[str, List[float]]:
    """`{block_key: [config-priced P&L, ...]}` — the L6 by-unit grouping block_bootstrap needs."""
    out: Dict[str, List[float]] = {}
    for u in units:
        out.setdefault(u.block_key, []).append(apply_fee_config(u.as_is_pnl, u.legs, config))
    return out


def scenario(units: List[Unit], config: str, n_boot: int) -> Dict[str, Any]:
    grouped = group_by_config(units, config)
    boot = block_bootstrap(grouped, n_boot=n_boot)
    ci = boot["ci95"]
    lo = ci[0]
    clears = clears_tick_magnitude(ci, tick=PRICE_TICK, min_ticks=1.0)
    ci_pos = lo is not None and lo > 0.0
    return {"config": config, "mean": boot["mean"], "ci95": ci,
            "n_units": boot["n_units"], "n_obs": boot["n_obs"],
            "ci_strictly_positive": ci_pos, "clears_tick_magnitude": clears,
            "alive": bool(ci_pos and clears)}


def analyze(name: str, collector: Callable[[], Tuple[List[Unit], Dict]], configs: List[str],
            n_boot: int) -> Dict[str, Any]:
    units, meta = collector()
    n_units_distinct = len({u.block_key for u in units})
    scenarios = {c: scenario(units, c, n_boot) for c in configs}
    adequate = n_units_distinct >= MIN_CI_UNITS
    as_is_alive = scenarios[AS_IS]["alive"] and adequate

    flips = [c for c in configs if c != AS_IS and adequate
             and scenarios[c]["alive"] and not as_is_alive]

    # best achievable fee config (highest mean) — bounds whether the loss is even fee-recoverable
    scored = [(c, scenarios[c]["mean"]) for c in configs
              if c != AS_IS and scenarios[c]["mean"] is not None]
    best_config, best_mean = (max(scored, key=lambda kv: kv[1]) if scored else (None, None))
    best_lo = scenarios[best_config]["ci95"][0] if best_config else None

    if not adequate:
        verdict = "DATA-ADEQUACY DEAD (<%d block units, untestable as collected)" % MIN_CI_UNITS
        verdict_class = "data_adequacy"
    elif as_is_alive:
        verdict = "already CI-positive on the Kalshi fee (fee line was NOT the killer)"
        verdict_class = "already_alive"
    elif flips:
        verdict = "FLIPS to CI-positive candidate under: " + ", ".join(flips)
        verdict_class = "flips"
    elif best_mean is not None and best_mean < 0:
        verdict = ("STAYS DEAD — lost by MORE than any fee swing (best fee-free config %s mean "
                   "%+.5f still < 0)" % (best_config, best_mean))
        verdict_class = "lost_by_more"
    else:
        verdict = ("STAYS DEAD — fee-line marginal (best config %s lifts the mean >0 but its CI "
                   "straddles / is below the 1c tick-magnitude gate)" % best_config)
        verdict_class = "fee_marginal"

    return {"name": name, "meta": meta, "configs": configs,
            "n_units_distinct": n_units_distinct, "adequate": adequate,
            "scenarios": scenarios, "as_is_alive": as_is_alive, "flips": flips,
            "best_config": best_config, "best_mean": best_mean, "best_ci_lo": best_lo,
            "verdict": verdict, "verdict_class": verdict_class}


# --------------------------------------------------------------------------- #
# reporting
# --------------------------------------------------------------------------- #
_CELL_W = 31


def _cell(s: Optional[Dict[str, Any]], adequate: bool) -> str:
    if s is None:
        return f"{'n/a':^{_CELL_W}}"
    if s["mean"] is None:
        return f"{'(no units)':^{_CELL_W}}"
    # a positive CI under <10 block units is an L41/adequacy artifact, never a real flip.
    if not adequate:
        tag = "thin"
    elif s["alive"]:
        tag = "FLIP"
    elif s["ci_strictly_positive"]:
        tag = ">0"
    else:
        tag = "dead"
    body = f"{s['mean']:+.4f}[{s['ci95'][0]:+.4f},{s['ci95'][1]:+.4f}] {tag}"
    return f"{body:^{_CELL_W}}"


def _print_report(reports: List[Dict[str, Any]], n_boot: int) -> None:
    print("=" * 118)
    print("Q39 GRAVEYARD COUNTERFACTUAL SWEEP  (read-only, offline; NO network)")
    print("=" * 118)
    print("Re-price each DEAD strategy's own committed simulation under a fee-config matrix. "
          "as_is = correctness check.")
    print("A 'flip' (FLIP) = DEAD -> CI strictly >0 AND clears the 1c tick-magnitude gate "
          "(L27). A flip is a CANDIDATE, never a proven edge.")
    print(f"Rebates INDICATIVE/pool-funded: +${PM_MAKER_REBATE_CONSERVATIVE:.4f} / "
          f"+${PM_MAKER_REBATE_US:.4f}. PM taker via core.pricing.polymarket_fee_per_contract.\n")

    hdr = f"{'strategy':<34}" + "".join(f"{c:^{_CELL_W}}" for c in ALL_CONFIGS)
    print(hdr)
    print("-" * len(hdr))
    for rep in reports:
        row = f"{rep['name']:<34}"
        for c in ALL_CONFIGS:
            if c in rep["configs"]:
                row += _cell(rep["scenarios"].get(c), rep["adequate"])
            else:
                row += f"{'n/a':^{_CELL_W}}"
        print(row)
    print("-" * len(hdr))
    print("(cell = mean [95% CI] tag;  tag: dead / >0 / FLIP / thin(<10 units);  "
          "n/a = config not applicable to family)\n")

    print("PER-STRATEGY VERDICT (block unit / distinct units in parens):")
    for rep in reports:
        flag = "FLIP" if rep["flips"] else "----"
        print(f"  [{flag}] {rep['name']:<34} (unit={rep['meta'].get('block_unit')}, "
              f"n={rep['n_units_distinct']})")
        print(f"         {rep['verdict']}")

    print("\nNOT-FEE-REVIVABLE BY CONSTRUCTION (no fee counterfactual run — would be misleading):")
    for name, reason in NOT_FEE_REVIVABLE:
        print(f"  [n/a ] {name}")
        print(f"         {reason}")

    n_flip = sum(1 for r in reports if r["flips"])
    print("\n" + "=" * 118)
    print(f"SUMMARY: {n_flip}/{len(reports)} swept strategies FLIP DEAD -> fee-line CI-positive "
          f"candidate. Flips are candidates for the two-agent verifier + Milestone B, NOT edges.")
    print("No registry status changed (Q39 spec).")
    print("=" * 118)


# --------------------------------------------------------------------------- #
STRATEGIES: List[Tuple[str, Callable, List[str]]] = [
    ("S6 (maker spread capture)", collect_s6, MAKER_CONFIGS),
    ("S13 (sports maker bid, fair-1c)", collect_s13, MAKER_CONFIGS),
    ("S19 (crypto wing-fade maker)", collect_s19, MAKER_CONFIGS),
    ("S21 (sports-longshot maker)", collect_s21, MAKER_CONFIGS),
    ("S23 (favorite-underpricing maker)", collect_s23, MAKER_CONFIGS),
    ("S29 (soccer draw-aversion maker)", collect_s29, MAKER_CONFIGS),
    ("S24 (near-close fade, taker RT)", collect_s24, TAKER_CONFIGS),
    ("S7c (sports CLV harvest, taker)", collect_s7c, TAKER_CONFIGS),
    ("S34 (cross-venue arb, 2-leg)", collect_s34, CROSS_VENUE_CONFIGS),
]


def run(n_boot: int = 10000) -> List[Dict[str, Any]]:
    reports = [analyze(name, collector, configs, n_boot)
               for name, collector, configs in STRATEGIES]
    _print_report(reports, n_boot)
    return reports


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Q39 graveyard counterfactual sweep (read-only, offline)")
    ap.add_argument("--n-boot", type=int, default=10000)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    reports = run(n_boot=args.n_boot)

    if args.json_out:
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "n_boot": args.n_boot,
            "configs": ALL_CONFIGS,
            "pm_maker_rebate_conservative": PM_MAKER_REBATE_CONSERVATIVE,
            "pm_maker_rebate_us": PM_MAKER_REBATE_US,
            "min_ci_units": MIN_CI_UNITS,
            "not_fee_revivable": [{"name": n, "reason": r} for n, r in NOT_FEE_REVIVABLE],
            "price_source_tag": ("mixed (real_ask/real_bid fills + broker_truth settle + "
                                 "synthetic devig anchors, per each source strategy)"),
            "strategies": reports,
        }
        Path(args.json_out).write_text(json.dumps(payload, indent=2, default=str))
        print(f"[q39] wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
