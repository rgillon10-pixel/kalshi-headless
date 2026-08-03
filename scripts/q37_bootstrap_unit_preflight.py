#!/usr/bin/env python3
"""Q37 PRE-FLIGHT: how many BOOTSTRAP UNITS will the gate's 21 contract-days actually buy?

Read-only, offline, NO network. Computes NO mean, NO bootstrap, NO CI, NO P&L aggregate and NO
verdict -- it is a DATA-ADEQUACY instrument, not a probe, and the two-agent verdict rule does not
apply to what it prints (LOOP-QUEUE.md step 5).

WHY THIS EXISTS
---------------
`scripts/q37_weather_summer_makerno_probe.py` self-activates when `tape/weather_books/` holds
>=21 SUMMER daily contract-days. That gate counts BOOK-TAPE contract-days. Its block bootstrap
resamples something else: a contract-day that yields at least one FILLED, SETTLEMENT-MEASURABLE
primary trade. The 2026-07-31 pre-flight audit already caught the gate counting the wrong ROWS
(phantom non-temperature series); this one asks whether it counts the wrong UNIT, and it does --
on 2026-08-03's committed tape, 20 gate-days buy 15 bootstrap units.

The deficit is not noise and does not close by waiting. Three disjoint causes, each measured:
  * `incomplete_book`  -- the first tape day has no book at T = close - 24h for ANY group.
  * `zero_fill`        -- a fully booked, fully settled day where nothing ever touched our price.
  * `settlement_lag`   -- the NEWEST gate-days carry no settled result yet (L262), so all their
                          rows are dropped as unmeasurable (L86). This window travels with the
                          fire date: whichever day the probe runs, its last ~3 gate-days are dead.

The counting functions themselves live in the probe module (one definition, two callers -- L36);
this script only force-builds the population (a labeled DIAGNOSTIC: the real gate is untouched and
this script can never emit a verdict) and prints the ledger.

Re-run:  python3 scripts/q37_bootstrap_unit_preflight.py
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

_spec = importlib.util.spec_from_file_location(
    "_q37_probe", str(REPO / "scripts" / "q37_weather_summer_makerno_probe.py"))
q37 = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(q37)


def build_population(books_glob: Optional[str] = None, actuals_glob: Optional[str] = None
                     ) -> Dict[str, Any]:
    """Force-build Q37's trade population WITHOUT opening its gate (diagnostic only).

    Uses the probe's own loaders and `simulate_group` verbatim -- nothing is re-derived here, so a
    change to the probe's population rules changes this pre-flight too, by construction."""
    bg = books_glob or q37.BOOKS_GLOB
    ag = actuals_glob or q37.ACTUALS_GLOB
    snaps = q37.load_daily_snapshots(bg)
    groups = q37.group_snapshots(snaps)
    results, _actuals = q37.load_settlement(ag)
    rows: List[Dict[str, Any]] = []
    skips: Dict[str, int] = {}
    for (series, cday), by_ticker in groups.items():
        r, reason = q37.simulate_group(series, cday, by_ticker, results)
        if reason != "ok":
            skips[reason] = skips.get(reason, 0) + 1
        rows.extend(r)
    ledger = q37.bootstrap_unit_ledger(rows, groups, results)
    return {
        "gate_days_present": q37._summer_contract_days_available(bg),
        "gate_days_required": q37.SUMMER_DAYS_REQUIRED,
        "n_snapshots": len(snaps),
        "n_groups": len(groups),
        "n_settled_result_tickers": len(results),
        "n_rows": len(rows),
        "skips": skips,
        "ledger": ledger,
        "gate_vs_units": q37.gate_vs_units_summary(ledger),
        "dual_cut_degeneracy": q37.dual_cut_degeneracy(rows),
        "note": ("DIAGNOSTIC population, built with the probe's gate BYPASSED for counting only. "
                 "No CI, no P&L, no verdict -- and this script cannot produce one."),
    }


def print_report(rep: Dict[str, Any]) -> None:
    print("=" * 96)
    print("Q37 PRE-FLIGHT — gate-days vs bootstrap-units (read-only; NO CI, NO verdict)")
    print("=" * 96)
    print(f"gate days present={rep['gate_days_present']} (gate opens at "
          f"{rep['gate_days_required']})   snapshots={rep['n_snapshots']}  "
          f"groups={rep['n_groups']}  settled result tickers={rep['n_settled_result_tickers']}")
    print(f"candidate longshot rows={rep['n_rows']}  group skips={rep['skips']}")
    print(f"\n{'contract_day':<13}{'grps':>5}{'settled':>8}{'rows':>6}{'meas':>6}{'prim':>6}"
          f"{'primmeas':>9}{'filled':>7}  unit  reason")
    for r in rep["ledger"]:
        mark = "YES " if r["contributes_unit"] else "no  "
        print(f"{r['contract_day']:<13}{r['n_groups']:>5}{r['n_groups_settled']:>8}"
              f"{r['n_rows']:>6}{r['n_measurable']:>6}{r['n_primary']:>6}"
              f"{r['n_primary_measurable']:>9}{r['n_filled']:>7}  {mark}  "
              f"{r['deficit_reason'] or ''}")
    g = rep["gate_vs_units"]
    yield_s = "n/a" if g["unit_yield"] is None else f"{100.0 * g['unit_yield']:.1f}%"
    print(f"\nGATE DAYS {g['n_gate_days']}  ->  BOOTSTRAP UNITS {g['n_bootstrap_units']}  "
          f"(deficit {g['unit_deficit']}, yield {yield_s})")
    print(f"  deficit_by_reason={g['deficit_by_reason']}")
    print(f"  L41 admissibility floor min_ci_units={g['min_ci_units']}  "
          f"clears={g['clears_min_ci_units']}")
    d = rep["dual_cut_degeneracy"]
    print(f"\nL32 DUAL CUT: touched={d['n_touched']}  frozen={d['n_frozen']}  "
          f"touched_AND_frozen={d['n_touched_and_frozen']}  "
          f"optimistic={d['n_filled_optimistic']}  movement={d['n_filled_movement']}  "
          f"degenerate={d['degenerate']}")
    if d["degenerate"]:
        print("  -> movement-conditioned == optimistic BY CONSTRUCTION (a frozen book cannot be "
              "touched without a crossed quote). The probe's two printed cuts are ONE number.")
    print(f"\n{rep['note']}")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Q37 gate-day vs bootstrap-unit pre-flight")
    ap.add_argument("--books-dir", default=None)
    ap.add_argument("--actuals-dir", default=None)
    ap.add_argument("--json-out", default=None)
    a = ap.parse_args(argv)
    bg = str(Path(a.books_dir) / "dt=*.jsonl") if a.books_dir else None
    ag = str(Path(a.actuals_dir) / "dt=*.jsonl") if a.actuals_dir else None
    rep = build_population(bg, ag)
    print_report(rep)
    if a.json_out:
        Path(a.json_out).write_text(json.dumps(rep, indent=2, default=str))
        print(f"[q37-preflight] wrote {a.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
