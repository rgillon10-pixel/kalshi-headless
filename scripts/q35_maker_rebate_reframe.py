#!/usr/bin/env python3
"""q35_maker_rebate_reframe.py — Q35 Milestone A: re-test the fee-killed maker family on a
maker-REBATE venue (analysis half, read-only, NO Polymarket data needed).

LOOP-QUEUE.md Q35. Five maker-side candidates all died PARTLY on Kalshi's flat ~1¢ maker fee
(L30: `fee_per_contract(P, MAKER_FEE_RATE) == $0.01` at every interior price):

  S13  scripts/s13_maker_fillsim.py                  bid at DK-devig fair-1c on sports MLs
  S19  scripts/s19_wing_fade_fillsim.py              maker-short elevated crypto wing brackets
  S21  scripts/q24_sports_longshot_maker_fillsim.py  maker rich-ask sell on sports longshots
  S23  scripts/q27_favorite_underpricing_fillsim.py  favorite settlement-underpricing maker
  S29  scripts/q30_draw_aversion_maker_probe.py      soccer draw-aversion maker bid

Those deaths are KALSHI-FEE-SPECIFIC. Polymarket's Fee Structure V2 PAYS makers a rebate
instead of charging a fee, so the fee LINE flips from a cost to income. This probe re-runs each
strategy's EXISTING simulation over its EXISTING committed tape/cache (imported as a module,
NO network, NO live fetch, NO tape mutation) and, per filled/settled unit, computes THREE
parallel P&L series:

  (a) as-is       — the already-verdicted Kalshi-fee number (correctness check vs the finding)
  (b) rebate +0.5c  — Kalshi fee REMOVED and a flat +$0.005/contract rebate ADDED
  (c) rebate +1.25c — Kalshi fee REMOVED and a flat +$0.0125/contract rebate ADDED

Because the Kalshi maker fee is a flat $0.01 at every interior fill price (L30), the fee-line
swing is a per-contract constant: swing = kalshi_fee + rebate (recomputed per unit from the
row's own price via core.pricing.fee_per_contract at MAKER_FEE_RATE — never hand-rolled).

Each of the 3 series is block-bootstrapped (core.bootstrap.block_bootstrap) on the SAME unit
each original strategy blocked on (GAME for S13/S21/S23/S29; EVENT-hour for S19), and the CI is
run through core.bootstrap.clears_tick_magnitude (L27). A strategy "flips" only if a rebate
scenario turns it from DEAD (CI ≤ 0 or straddling 0) to CI strictly > 0 AND clearing the tick
gate — and even then it is a fee-line CANDIDATE, never a proven edge (Q35 Milestone B owes it
portability + resolution-basis + the full real-ask bar on the actual venue). This script does
NOT touch kb/strategies/00-index.md and makes NO registry decision (Q35 spec).

Read-only. Fees ONLY from core.pricing. Run:
    python scripts/q35_maker_rebate_reframe.py
    python scripts/q35_maker_rebate_reframe.py --n-boot 10000 --json-out /tmp/q35.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.bootstrap import block_bootstrap, clears_tick_magnitude  # noqa: E402
from core.pricing import MAKER_FEE_RATE, fee_per_contract  # noqa: E402

# ── Polymarket maker-rebate constants (INDICATIVE, pool-funded — NOT a sanctioned core rate) ──
# Q35 spec: there is no `POLYMARKET_MAKER_REBATE` in core/pricing.py yet (that is Milestone B's
# job, gated on the Polymarket collector — out of scope here). Fee Structure V2 makes Polymarket
# TAKER-only and PAYS makers a rebate funded from the taker-fee pool; the rate is indicative and
# varies with volume (LOOP-QUEUE.md 2026-07-15 regime-change note: ~+0.5c/contract conservative,
# ~+1.25c/contract the Polymarket US venue figure). These are local script constants ONLY.
POLYMARKET_REBATE_CONSERVATIVE = 0.005   # +$0.005/contract — conservative maker rebate
POLYMARKET_REBATE_US = 0.0125            # +$0.0125/contract — Polymarket US venue figure

PRICE_TICK = 0.01


# --------------------------------------------------------------------------- #
# the one new helper this milestone adds (offline unit-tested): the fee-swap
# --------------------------------------------------------------------------- #
def rebate_swap(as_is_pnl: float, kalshi_fee: float, rebate: float) -> float:
    """Convert a Kalshi-fee P&L into the same trade's P&L on a maker-REBATE venue.

    The as-is P&L had `kalshi_fee` (a POSITIVE dollar cost) SUBTRACTED. On a rebate venue the
    fee line flips sign: we add the fee back (remove the Kalshi cost) and add the rebate income.
    So new_pnl = as_is_pnl + kalshi_fee + rebate. Every other leg (premium, $1 settlement) is
    untouched — only the fee LINE changes, which is the entire point of Q35 Milestone A.

    `kalshi_fee` must be passed as the positive amount charged (e.g. fee_per_contract(...));
    `rebate` is the positive per-contract rebate income.
    """
    return float(as_is_pnl) + float(kalshi_fee) + float(rebate)


# --------------------------------------------------------------------------- #
# per-strategy unit collection — reuse each script's OWN simulate/aggregation
# functions; recover the Kalshi maker fee from each row's own price field.
# Each collector returns (list[(block_key, as_is_pnl, kalshi_fee)], meta_dict).
# --------------------------------------------------------------------------- #
def collect_s13() -> Tuple[List[Tuple[str, float, float]], Dict[str, Any]]:
    """S13 — sports maker bid at DK-devig fair-1c. Block unit = GAME (kalshi_event_ticker).
    Offline: read the committed candle-summary cache; a cache miss is a no-fill (never a fetch)."""
    from scripts import s13_maker_fillsim as s13

    cache = s13.load_candle_summary_cache()

    def offline_fetcher(series: str, ticker: str, start_ts: int, end_ts: int) -> Dict[str, Any]:
        rec = cache.get(ticker)
        if rec is not None:
            return rec
        return {"min_low_dollars": None, "min_low_end_period_ts": None, "n_candles": 0}

    games = s13.load_games()
    history = s13.load_history_records()
    windows = s13.kalshi_outcome_windows(history)
    moneylines = s13.espn_moneylines(history)
    rows = s13.simulate_outcomes(games, windows, moneylines, offline_fetcher)

    units: List[Tuple[str, float, float]] = []
    for r in rows:
        if not r["filled"] or r.get("edge_after_fee_fill_anchor") is None:
            continue
        # recompute the Kalshi maker fee from the row's own bid price (matches s13's own
        # fee_per_contract(bid, MAKER_FEE_RATE); flat $0.01 at every interior price, L30).
        kalshi_fee = fee_per_contract(r["bid_price"], rate=MAKER_FEE_RATE)
        units.append((r["kalshi_event_ticker"], r["edge_after_fee_fill_anchor"], kalshi_fee))
    meta = {"n_attempts": len(rows), "n_filled": len(units),
            "block_unit": "game (kalshi_event_ticker)"}
    return units, meta


def collect_s19() -> Tuple[List[Tuple[str, float, float]], Dict[str, Any]]:
    """S19 — maker-short elevated crypto wing brackets. Block unit = EVENT-hour (event_ticker).
    Fully offline over crypto_hourly + orderbook_depth + the s14 candle cache."""
    from scripts import s19_wing_fade_fillsim as s19

    records = s19.load_crypto_records()
    depth_idx = s19.build_depth_index()
    candle_cache = s19.load_candle_cache()
    sim = s19.simulate(records, depth_idx, candle_cache)

    units: List[Tuple[str, float, float]] = []
    for r in sim["fill_rows"]:
        # s19's maker fee is on the resting NO-bid fill price (1 minus yes_ask); flat $0.01 (L30).
        kalshi_fee = fee_per_contract(1.0 - float(r["yes_ask"]), rate=MAKER_FEE_RATE)
        units.append((r["event_ticker"], float(r["pnl"]), kalshi_fee))
    meta = {"n_wing": sim["n_wing"], "n_fill": sim["n_fill"],
            "block_unit": "event-hour (event_ticker)"}
    return units, meta


def collect_s21() -> Tuple[List[Tuple[str, float, float]], Dict[str, Any]]:
    """S21 — sports-longshot maker rich-ask sell. Block unit = GAME (event_ticker). The mandated
    join is empty offline (0 fills — every fair-anchored game settled before the sports depth
    tape began, L9), so this is untestable regardless of the fee line. Reported honestly."""
    from scripts import q24_sports_longshot_maker_fillsim as q24

    clv = q24.load_clv_records()
    settle_map = q24.build_settlement_map()
    candle_map = q24.build_candle_volume_map()
    depth_idx = q24.build_depth_index()
    sim = q24.simulate(clv, settle_map, candle_map, depth_idx, selection="fair", ask_delta=0.0)

    units: List[Tuple[str, float, float]] = []
    for r in sim["fill_rows"]:
        kalshi_fee = fee_per_contract(1.0 - float(r["premium"]), rate=MAKER_FEE_RATE)
        units.append((r["event_ticker"], float(r["pnl"]), kalshi_fee))
    meta = {"n_longshot": sim["n_longshot"], "n_joinable": sim["n_joinable"],
            "n_fill": sim["n_fill"], "block_unit": "game (event_ticker)"}
    return units, meta


def collect_s23() -> Tuple[List[Tuple[str, float, float]], Dict[str, Any]]:
    """S23 — favorite settlement-underpricing maker bid. Block unit = GAME (event_ticker).
    Offline over the committed q27 settlement cache + orderbook_depth."""
    from scripts import q27_favorite_underpricing_fillsim as q27

    settlement = q27.load_settlement_cache(q27.CACHE_PATH)
    per_market, _ = q27.load_preclose_snapshots(q27.DEPTH_GLOB, settlement)
    trades, _ = q27.build_favorite_trades(per_market)

    units: List[Tuple[str, float, float]] = []
    for t in trades:
        if not t["filled"] or t.get("pnl") is None:
            continue
        kalshi_fee = fee_per_contract(t["fill_price"], rate=MAKER_FEE_RATE)
        units.append((t["event_ticker"], float(t["pnl"]), kalshi_fee))
    meta = {"n_rested": len(trades), "n_filled": len(units),
            "block_unit": "game (event_ticker)"}
    return units, meta


def collect_s29() -> Tuple[List[Tuple[str, float, float]], Dict[str, Any]]:
    """S29 — soccer draw-aversion maker bid on the -TIE leg. Block unit = GAME (event_ticker).
    Offline over the committed q30 (or q27-fallback) settlement cache + orderbook_depth."""
    from scripts import q30_draw_aversion_maker_probe as q30

    settlement, cache_source = q30.load_settlement_for_run(q30.CACHE_PATH)
    per_market, _ = q30.load_preclose_snapshots(q30.DEPTH_GLOB, settlement)
    trades, _ = q30.build_draw_trades(per_market)

    units: List[Tuple[str, float, float]] = []
    for t in trades:
        if not t["filled"] or t.get("pnl") is None:
            continue
        kalshi_fee = fee_per_contract(t["fill_price"], rate=MAKER_FEE_RATE)
        units.append((t["event_ticker"], float(t["pnl"]), kalshi_fee))
    meta = {"cache_source": cache_source, "n_rested": len(trades), "n_filled": len(units),
            "block_unit": "game (event_ticker)"}
    return units, meta


# --------------------------------------------------------------------------- #
# scenario bootstrap
# --------------------------------------------------------------------------- #
def _group(units: List[Tuple[str, float, float]], rebate: Optional[float]
           ) -> Dict[str, List[float]]:
    """Group per-unit P&L by block key. rebate=None -> the as-is (Kalshi-fee) series; a numeric
    rebate -> the fee-swapped series (fee removed + rebate added, via rebate_swap)."""
    out: Dict[str, List[float]] = {}
    for key, as_is_pnl, kalshi_fee in units:
        val = as_is_pnl if rebate is None else rebate_swap(as_is_pnl, kalshi_fee, rebate)
        out.setdefault(key, []).append(val)
    return out


def _scenario(units: List[Tuple[str, float, float]], rebate: Optional[float], n_boot: int
              ) -> Dict[str, Any]:
    grouped = _group(units, rebate)
    boot = block_bootstrap(grouped, n_boot=n_boot)
    ci = boot["ci95"]
    lo = ci[0]
    clears = clears_tick_magnitude(ci, tick=PRICE_TICK, min_ticks=1.0)
    ci_strictly_positive = lo is not None and lo > 0.0
    return {
        "rebate": rebate,
        "mean": boot["mean"],
        "ci95": ci,
        "n_units": boot["n_units"],
        "n_obs": boot["n_obs"],
        "ci_strictly_positive": ci_strictly_positive,
        "clears_tick_magnitude": clears,
        "alive": bool(ci_strictly_positive and clears),
    }


MIN_CI_UNITS = 10  # the shared data-adequacy floor (S19/Q24/Q27/Q30 all use it)


def analyze(name: str, collector: Callable[[], Tuple[List, Dict]], n_boot: int) -> Dict[str, Any]:
    units, meta = collector()
    n_units_distinct = len({k for k, _, _ in units})
    scenarios = {
        "as_is": _scenario(units, None, n_boot),
        "rebate_conservative": _scenario(units, POLYMARKET_REBATE_CONSERVATIVE, n_boot),
        "rebate_us": _scenario(units, POLYMARKET_REBATE_US, n_boot),
    }
    # data-adequacy: a bootstrap over < MIN_CI_UNITS block units is not a testable CI, so a
    # positive-looking CI there is NOT a flip (S19's n_units=2 artifact, L41 family).
    adequate = n_units_distinct >= MIN_CI_UNITS
    as_is_alive = scenarios["as_is"]["alive"] and adequate
    flips: List[str] = []
    for label in ("rebate_conservative", "rebate_us"):
        s = scenarios[label]
        if adequate and s["alive"] and not as_is_alive:
            flips.append(label)
    if not adequate:
        verdict = "STAYS DEAD (data-adequacy: <%d block units, untestable)" % MIN_CI_UNITS
    elif as_is_alive:
        verdict = "already CI-positive on Kalshi fee (fee line was NOT the killer)"
    elif flips:
        verdict = "FLIPS to CI-positive candidate under: " + ", ".join(flips)
    else:
        verdict = "STAYS DEAD (rebate swing insufficient — lost by more than the fee line)"
    return {"name": name, "meta": meta, "n_units_distinct": n_units_distinct,
            "adequate": adequate, "scenarios": scenarios,
            "as_is_alive": as_is_alive, "flips": flips, "verdict": verdict}


# --------------------------------------------------------------------------- #
# reporting
# --------------------------------------------------------------------------- #
def _fmt_ci(ci: Any) -> str:
    if not ci or ci[0] is None:
        return "[   None ,   None ]"
    return f"[{ci[0]:+.5f}, {ci[1]:+.5f}]"


def _print_strategy(rep: Dict[str, Any]) -> None:
    print("-" * 88)
    print(f"{rep['name']}   block unit: {rep['meta'].get('block_unit')}   "
          f"filled block units: {rep['n_units_distinct']}"
          f"{'' if rep['adequate'] else '  (< %d — data-adequacy)' % MIN_CI_UNITS}")
    for label, tag in (("as_is", "as-is (Kalshi 1c fee)     "),
                       ("rebate_conservative", "rebate +0.5c (fee->income)"),
                       ("rebate_us", "rebate +1.25c (fee->income)")):
        s = rep["scenarios"][label]
        mean = "None" if s["mean"] is None else f"{s['mean']:+.5f}"
        gate = "CLEARS" if s["clears_tick_magnitude"] else "no"
        pos = ">0" if s["ci_strictly_positive"] else "≤0"
        print(f"  {tag}: mean={mean:>10}  95% CI={_fmt_ci(s['ci95'])}  "
              f"n_units={s['n_units']:>3}  n_obs={s['n_obs']:>4}  CI {pos}  tick-gate {gate}")
    print(f"  VERDICT: {rep['verdict']}")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Q35 Milestone A — maker-rebate reframe of the 5 fee-killed maker candidates")
    ap.add_argument("--n-boot", type=int, default=10000)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    collectors = [
        ("S13 (sports maker bid, fair-1c)", collect_s13),
        ("S19 (crypto wing-fade maker short)", collect_s19),
        ("S21 (sports-longshot maker rich-ask)", collect_s21),
        ("S23 (favorite-underpricing maker bid)", collect_s23),
        ("S29 (soccer draw-aversion maker bid)", collect_s29),
    ]

    print("=" * 88)
    print("Q35 MILESTONE A — MAKER-REBATE REFRAME (read-only, offline; NO Polymarket data)")
    print("=" * 88)
    print(f"Kalshi maker fee removed + rebate added. Rebates (INDICATIVE, pool-funded, script-"
          f"local): conservative=+${POLYMARKET_REBATE_CONSERVATIVE:.4f}  "
          f"US=+${POLYMARKET_REBATE_US:.4f}/contract.")
    print("A 'flip' = DEAD (CI ≤ 0 / straddles 0, adequately powered) -> CI strictly > 0 AND "
          "clears the 1-tick gate. A flip is a CANDIDATE, not a proven edge (Q35 Milestone B).")

    reports: List[Dict[str, Any]] = []
    for name, collector in collectors:
        rep = analyze(name, collector, args.n_boot)
        reports.append(rep)
        _print_strategy(rep)

    print("=" * 88)
    print("SUMMARY")
    for rep in reports:
        flag = "FLIP" if rep["flips"] else "----"
        print(f"  [{flag}] {rep['name']:<40} {rep['verdict']}")
    n_flip = sum(1 for r in reports if r["flips"])
    print(f"\n{n_flip}/5 strategies flip DEAD -> fee-line CI-positive candidate on a rebate venue.")
    print("No registry status is changed (Q35 spec) — a fee-line flip is a candidate for the "
          "two-agent verifier + Milestone B, never a proven edge.")
    print("=" * 88)

    if args.json_out:
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "n_boot": args.n_boot,
            "rebate_conservative": POLYMARKET_REBATE_CONSERVATIVE,
            "rebate_us": POLYMARKET_REBATE_US,
            "min_ci_units": MIN_CI_UNITS,
            "price_source_tag": "mixed (real_ask/real_bid fills + broker_truth settle + "
                                "synthetic devig anchors, per each source strategy)",
            "strategies": reports,
        }
        Path(args.json_out).write_text(json.dumps(payload, indent=2, default=str))
        print(f"[q35] wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
