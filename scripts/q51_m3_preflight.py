#!/usr/bin/env python3
"""Q51 MILESTONE-3 PRE-FLIGHT: will the 2026-08-10 firing clear the L41 unit floor,
and what will the re-pull do to the tests that pin milestone 2?

Read-only, fully offline, NO network. Computes NO mean, NO bootstrap, NO CI, NO P&L and NO
verdict about the strategy -- it is a DATA-ADEQUACY instrument, not a probe (the
`scripts/q37_bootstrap_unit_preflight.py` precedent). The two-agent verdict rule does not
apply to what it prints, because nothing it prints is verdict-class.

WHY THIS EXISTS
---------------
LOOP-QUEUE.md Q51 milestone 3 is TIME-GATED to 2026-08-10: re-pull
`tape/q51_settlement_cache/settlement.json` for the SAME 60 sampled tickers once the
2026-08-04..08-09 games have been played, then re-run `scripts/q51_maker_fillsim.py`
UNCHANGED over already-committed tape. The milestone-2 run was INADMISSIBLE on
`n_units_games = 7` (below the L41 floor of 10) purely because 49 of the 60 sampled
markets were still `active` at pull time -- settlement RECENCY, not the fill leg, is the
binding constraint.

Two questions can be answered offline TODAY, five days before the gate, and both change
what should happen on 08-10:

  Q1. HOW MANY UNITS does an 08-10 firing actually buy? The queue's recorded expectation
      is "~57 game units / ~330 legs". That is the FULL population and it is reachable
      only after the last two markets close on 2026-08-23 -- not on 08-10. This script
      computes the cumulative-by-close-day projection so the firing date is chosen on a
      number instead of on the word "once the games have been played".

  Q2. WHAT DOES THE RE-PULL BREAK? `q51_maker_fillsim.py --build-cache` OVERWRITES
      `tape/q51_settlement_cache/settlement.json` in place. Three HARD acceptance tests in
      `tests/test_q51_maker_fillsim.py` call `run()` on the DEFAULT cache path and pin
      milestone-2 numbers that are functions of that mutable file (n_units_games == 7,
      n_intervals == 20, drops["unsettled"] == 145, n_fills == 26). Re-pulling flips ~44
      markets from `active` to finalized, so those pins move and the `pytest -q` gate goes
      RED on the exact day the milestone fires. That also violates L191's own stated
      intent for those tests -- "pin acceptance numbers to a slice that cannot grow".
      `hazard_report()` DEMONSTRATES the coupling offline (below); the repair is not in
      this script: it is the immutable snapshot
      `tape/q51_settlement_cache/settlement-m2-2026-08-04.json` plus the repointed
      `cache_path=` arguments in those three tests.

EVERYTHING HERE IS A PROJECTION, NOT A MEASUREMENT
--------------------------------------------------
The projection assumes every market whose `close_time` has passed is FINALIZED with a
BINARY result at the pull instant. Reality can only be WORSE, never better:
  * settlement lag -- Kalshi finalizes at/after close, so a market closing ON the firing
    day may still be `active` when the pull lands (L262's shape);
  * L52 -- a non-binary (`scalar`) result is dropped by
    `core.settlement.filter_binary_results_map`, and this sample has 60 markets whose
    results are, for 49 of them, not yet observable;
  * 3 of the 60 sampled sports markets carry fewer than 2 depth snapshots on
    `dt=2026-08-03`, so they contribute ZERO intervals no matter what they settle to.
Therefore each projected count is an UPPER BOUND. It is quoted as such everywhere.

SYNTHETIC-SETTLEMENT WARNING (prime directive)
----------------------------------------------
`hazard_report()` builds a TEMPORARY synthetic settlement cache (markets projected closed
by the firing date are given a placeholder binary result) purely to show that the pinned
quantities MOVE when the cache moves. Those results are SYNTHETIC. No P&L, mean or CI from
that run is computed, reported or persisted, and none may ever be quoted. The only outputs
taken from it are population COUNTS.

Re-run:  python3 scripts/q51_m3_preflight.py
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from core.io import REPO_ROOT  # noqa: E402
from scripts import q51_maker_fillsim as M  # noqa: E402

# The L41 admissibility floor, taken from the one sanctioned site rather than re-typed.
L41_MIN_UNITS = 10

REPORT_PATH = REPO_ROOT / "reports" / "q51_m3_preflight.json"
FROZEN_M2_CACHE = REPO_ROOT / "tape" / "q51_settlement_cache" / "settlement-m2-2026-08-04.json"

# The dates the queue names: fire the re-pull on 08-10, second sweep after 08-24.
CANDIDATE_FIRE_DATES = ("2026-08-09", "2026-08-10", "2026-08-12", "2026-08-23", "2026-08-24")


# --------------------------------------------------------------------------- #
# population (delegated to the probe's own helpers -- one definition, two callers, L36)
# --------------------------------------------------------------------------- #
def sports_universe(day: str = M.DAY):
    """The probe's own sampled sports universe, plus its per-ticker snapshot series.

    Reuses `q51_maker_fillsim`'s loaders verbatim so this pre-flight cannot drift from the
    probe it is pre-flighting."""
    order, snaps = M.load_depth(day)
    if not order:
        raise SystemExit(f"no committed orderbook_depth tape for dt={day}")
    universe = [t for t in M.reconstruct_sample(order) if M.is_sports_game_market(t)]
    return universe, snaps


def interval_counts(universe: Sequence[str], snaps: Dict[str, list]) -> Dict[str, int]:
    """intervals(ticker) = max(0, n_snapshots - 1) -- an interval is a consecutive pair,
    exactly as `q51_maker_fillsim.build_rows` walks `zip(ss[:-1], ss[1:])`."""
    return {t: max(0, len(snaps.get(t) or []) - 1) for t in universe}


def close_day(entry: Optional[dict]) -> Optional[str]:
    """The UTC calendar day of a cached market's `close_time` (`broker_truth`), or None."""
    ct = (entry or {}).get("close_time") or ""
    return ct[:10] if len(ct) >= 10 else None


def cumulative_by_close_day(universe: Sequence[str], ivs: Dict[str, int],
                            settlement: Dict[str, dict]) -> List[Dict[str, Any]]:
    """For each distinct close-day D, the UPPER BOUND on what a re-pull dated D buys.

    `markets_closed`   -- sampled sports markets whose close_time day <= D
    `with_intervals`   -- ...of those, the ones carrying >=1 depth interval on the probe's day
    `game_units`       -- distinct `game_of()` keys among those (the L6 bootstrap unit)
    `legs`             -- 2 * intervals (the yes_bid leg and the no_bid leg, per milestone 2)
    `clears_l41_floor` -- game_units >= 10. This is the ONLY verdict-shaped field here and it
                          is an ADEQUACY statement, never a statement about edge."""
    days = sorted({d for d in (close_day(settlement.get(t)) for t in universe) if d})
    out: List[Dict[str, Any]] = []
    for d in days:
        closed = [t for t in universe if (close_day(settlement.get(t)) or "9999") <= d]
        with_iv = [t for t in closed if ivs.get(t, 0) > 0]
        games = {M.game_of(t) for t in with_iv}
        legs = 2 * sum(ivs[t] for t in with_iv)
        out.append({
            "close_day": d,
            "markets_closed": len(closed),
            "with_intervals": len(with_iv),
            "game_units": len(games),
            "intervals": sum(ivs[t] for t in with_iv),
            "legs": legs,
            "clears_l41_floor": len(games) >= L41_MIN_UNITS,
        })
    return out


def projection_for(table: Sequence[Dict[str, Any]], fire_date: str) -> Optional[Dict[str, Any]]:
    """The last cumulative row at or before `fire_date` (markets closing ON the fire date
    are INCLUDED -- the optimistic reading; `conservative_*` below drops them)."""
    rows = [r for r in table if r["close_day"] <= fire_date]
    return dict(rows[-1]) if rows else None


def fire_date_projections(table: Sequence[Dict[str, Any]],
                          dates: Sequence[str] = CANDIDATE_FIRE_DATES) -> Dict[str, Any]:
    """Optimistic (close_time <= fire date) and conservative (close_time < fire date, i.e.
    allow a full day of settlement lag) projections for each candidate firing date."""
    out: Dict[str, Any] = {}
    for d in dates:
        opt = projection_for(table, d)
        prev = [r for r in table if r["close_day"] < d]
        con = dict(prev[-1]) if prev else None
        out[d] = {
            "optimistic_includes_same_day_closes": opt,
            "conservative_one_day_settlement_lag": con,
            "clears_l41_floor_even_conservatively": bool(con and con["clears_l41_floor"]),
        }
    return out


# --------------------------------------------------------------------------- #
# the firing hazard: the milestone-2 pins are coupled to a MUTABLE file
# --------------------------------------------------------------------------- #
#: the three acceptance tests that call `M.run()` on the DEFAULT cache path and pin
#: milestone-2 population numbers. Named here so the report is self-describing.
M2_PINNED_TESTS = (
    "tests/test_q51_maker_fillsim.py::test_acceptance_headline_verdict_is_data_inadequate_below_min_units",
    "tests/test_q51_maker_fillsim.py::test_acceptance_settlement_recency_is_the_binding_constraint_not_the_fill_leg",
    "tests/test_q51_maker_fillsim.py::test_acceptance_every_real_fill_traces_to_a_broker_truth_trade_id",
)

#: population keys only. Deliberately excludes every P&L/CI key -- see the module docstring's
#: SYNTHETIC-SETTLEMENT WARNING. A mean from a synthetic-settlement run is not a number.
_HAZARD_KEYS = ("n_units_games", "n_intervals", "n_covered_intervals", "drops_unsettled", "n_fills")


def _population_snapshot(report: Dict[str, Any]) -> Dict[str, Any]:
    v = report["verdicts"]["all_intervals"]
    iv = report["intervals"]
    return {
        "n_units_games": v["n_units_games"],
        "n_intervals": iv["n_intervals"],
        "n_covered_intervals": iv["n_covered_intervals"],
        "drops_unsettled": iv["drops"].get("unsettled"),
        "n_fills": report["fill_traceability"]["n_fills"],
    }


def synthetic_post_repull_cache(settlement: Dict[str, dict], universe: Sequence[str],
                                ivs: Dict[str, int], fire_date: str) -> Dict[str, dict]:
    """A SYNTHETIC cache in which every market closed by `fire_date` carries a placeholder
    BINARY result. Used ONLY to show the milestone-2 pins move; the results are invented
    and no outcome-dependent number may be read off a run against it."""
    out: Dict[str, dict] = {}
    for i, t in enumerate(sorted(universe)):
        base = dict(settlement.get(t) or {})
        d = close_day(base)
        if d and d <= fire_date and not (base.get("result") or ""):
            base["result"] = "yes" if i % 2 == 0 else "no"   # SYNTHETIC placeholder
            base["status"] = "finalized"
        out[t] = base
    return out


def hazard_report(universe: Sequence[str], ivs: Dict[str, int], settlement: Dict[str, dict],
                  fire_date: str = "2026-08-10", n_boot: int = 50,
                  before_cache_path: Optional[Path] = None) -> Dict[str, Any]:
    """Demonstrate, offline and without touching the real cache, that the three
    milestone-2 acceptance pins are functions of a file `--build-cache` overwrites.

    `before_cache_path` defaults to the LIVE cache, which is what an on-demand diagnostic
    wants: run it after 2026-08-10 and `hazard_confirmed` correctly goes False, because by
    then the live file IS the post-re-pull state. A TEST must pass the frozen milestone-2
    snapshot instead — otherwise the test itself becomes the very time-bomb this function
    exists to find (an assertion whose truth depends on a file a scheduled command
    rewrites). That is the whole lesson, applied to this module."""
    before_rep, _before_rows = M.run(n_boot=n_boot, cache_path=before_cache_path or M.CACHE_PATH)
    before = _population_snapshot(before_rep)
    synth = synthetic_post_repull_cache(settlement, universe, ivs, fire_date)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "settlement.json"
        p.write_text(json.dumps({
            "schema_version": "q51_settlement_cache.v1",
            "price_source_tag": "synthetic",     # NOT broker_truth -- these results are invented
            "source": "SYNTHETIC_PREFLIGHT_PLACEHOLDER_DO_NOT_QUOTE",
            "day": M.DAY,
            "markets": synth,
        }), encoding="utf-8")
        after_rep, _after_rows = M.run(n_boot=n_boot, cache_path=p)
        after = _population_snapshot(after_rep)
    moved = sorted(k for k in _HAZARD_KEYS if before[k] != after[k])
    return {
        "what_this_shows": (
            "the milestone-2 acceptance pins are functions of a MUTABLE file that "
            "`q51_maker_fillsim.py --build-cache` overwrites in place"),
        "price_source_tag_of_the_after_column": "synthetic",
        "after_column_is_not_an_outcome": True,
        "fire_date_modelled": fire_date,
        "before_cache_path": str(before_cache_path or M.CACHE_PATH),
        "before_cache_is_the_frozen_m2_snapshot": (
            (before_cache_path or M.CACHE_PATH) == FROZEN_M2_CACHE),
        "pinned_tests": list(M2_PINNED_TESTS),
        "before_committed_cache": before,
        "after_synthetic_post_repull_cache": after,
        "pinned_quantities_that_move": moved,
        "hazard_confirmed": bool(moved),
        "repair": {
            "frozen_snapshot": str(FROZEN_M2_CACHE.relative_to(REPO_ROOT)),
            "frozen_snapshot_present": FROZEN_M2_CACHE.exists(),
            "method": ("byte-identical copy of the milestone-2 cache; the live "
                       "settlement.json is NOT modified and NOT deleted (append-only); the "
                       "three pinned tests pass `cache_path=` explicitly at the snapshot"),
        },
    }


# --------------------------------------------------------------------------- #
def run(day: str = M.DAY, cache_path: Optional[Path] = None, fire_date: str = "2026-08-10",
        with_hazard: bool = True, n_boot: int = 50) -> Dict[str, Any]:
    universe, snaps = sports_universe(day)
    settlement = M.load_settlement_cache(cache_path or M.CACHE_PATH)
    ivs = interval_counts(universe, snaps)
    table = cumulative_by_close_day(universe, ivs, settlement)

    statuses = Counter((settlement.get(t) or {}).get("status") for t in universe)
    results = Counter((settlement.get(t) or {}).get("result") for t in universe)

    report: Dict[str, Any] = {
        "what_this_is": (
            "PROJECTION, not a measurement. A data-adequacy pre-flight for the TIME-GATED "
            "Q51 milestone 3. No mean, no bootstrap, no CI, no P&L, no strategy verdict."),
        "day": day,
        "generated_for_queue_item": "Q51 milestone 3 (time-gated 2026-08-10)",
        "l41_min_units": L41_MIN_UNITS,
        "population": {
            "sports_game_markets_in_sample": len(universe),
            "total_intervals": sum(ivs.values()),
            "markets_with_at_least_one_interval": sum(1 for t in universe if ivs[t] > 0),
            "markets_with_zero_intervals": sum(1 for t in universe if ivs[t] == 0),
            "cache_status_counts": {str(k): v for k, v in sorted(statuses.items(), key=lambda kv: str(kv[0]))},
            "cache_result_counts": {str(k): v for k, v in sorted(results.items(), key=lambda kv: str(kv[0]))},
            "price_source_tag": "broker_truth",
        },
        "cumulative_by_close_day": table,
        "fire_date_projections": fire_date_projections(table),
        "caveats": {
            "upper_bound_only": (
                "every projected count assumes a closed market is FINALIZED with a BINARY "
                "result at the pull instant; settlement lag and L52 non-binary results can "
                "only reduce it"),
            "markets_that_can_never_contribute": sum(1 for t in universe if ivs[t] == 0),
            "why_they_can_never_contribute": (
                "fewer than 2 depth snapshots on the probe's day, so zero consecutive-pair "
                "intervals regardless of how they settle"),
            "queue_expectation_is_the_full_population": (
                "LOOP-QUEUE's '~57 game units / ~330 legs' is the terminal row of this "
                "table (close_day 2026-08-23), NOT what a 2026-08-10 firing yields"),
            "book_side_is_frozen": (
                "the interval count comes from a PAST day (dt=%s) of tape/orderbook_depth/; a "
                "later stranded-branch sweep could legitimately append snapshots for that day "
                "and raise it, so downstream assertions on it should be directional bounds" % day),
        },
    }
    if with_hazard:
        report["milestone_3_firing_hazard"] = hazard_report(
            universe, ivs, settlement, fire_date=fire_date, n_boot=n_boot)
    return report


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Q51 milestone-3 data-adequacy pre-flight")
    ap.add_argument("--day", default=M.DAY)
    ap.add_argument("--fire-date", default="2026-08-10")
    ap.add_argument("--no-hazard", action="store_true",
                    help="skip the (slower) firing-hazard demonstration")
    ap.add_argument("--json-out", default=str(REPORT_PATH))
    args = ap.parse_args(argv)

    rep = run(day=args.day, fire_date=args.fire_date, with_hazard=not args.no_hazard)

    Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.json_out, "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=1, sort_keys=True)

    p = rep["population"]
    print("[q51:m3-preflight] PROJECTION ONLY -- no CI, no P&L, no verdict about the strategy")
    print(f"[q51:m3-preflight] sports markets={p['sports_game_markets_in_sample']}  "
          f"intervals={p['total_intervals']}  with>=1 interval={p['markets_with_at_least_one_interval']}")
    print("  close_day    markets  with_iv  games  legs  clears_L41")
    for r in rep["cumulative_by_close_day"]:
        print(f"  {r['close_day']}   {r['markets_closed']:>7}  {r['with_intervals']:>7}  "
              f"{r['game_units']:>5}  {r['legs']:>4}  {r['clears_l41_floor']}")
    for d, v in rep["fire_date_projections"].items():
        o = v["optimistic_includes_same_day_closes"]
        c = v["conservative_one_day_settlement_lag"]
        print(f"  fire {d}: optimistic units={o and o['game_units']} legs={o and o['legs']} | "
              f"conservative units={c and c['game_units']} legs={c and c['legs']} | "
              f"clears L41 conservatively={v['clears_l41_floor_even_conservatively']}")
    h = rep.get("milestone_3_firing_hazard")
    if h:
        print(f"[q51:m3-preflight] firing hazard confirmed={h['hazard_confirmed']}  "
              f"moves={h['pinned_quantities_that_move']}")
        print(f"    before(committed cache)={h['before_committed_cache']}")
        print(f"    after (SYNTHETIC cache)={h['after_synthetic_post_repull_cache']}")
        print(f"    frozen snapshot present={h['repair']['frozen_snapshot_present']}")
    print(f"[q51:m3-preflight] wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
