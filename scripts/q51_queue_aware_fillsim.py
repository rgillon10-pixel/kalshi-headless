#!/usr/bin/env python3
"""q51_queue_aware_fillsim.py — L337 follow-on: the QUEUE-AWARE discount on Q51 milestone
3's maker fill-sim headline.

L337 (2026-08-11): `scripts/q51_maker_fillsim.py` credits a fill whenever ANY qualifying
executed print lands in the interval, with NO accounting for the SIZE already resting ahead
of the order at its own price. That makes its 64/294 fills (21.77%) and +$0.010068 mean an
UPPER BOUND, not a measurement — the gap measured ad hoc by an independent verifier was
~14x on the fill count-derived rate and ~2.5x on the mean. This module is that lesson's
"standalone follow-on script": it recomputes the SAME population through the SAME verdict
machinery under a queue-aware fill rule and reports the discount factor beside the headline.

WHY A SEPARATE MODULE, not a `--queue-aware` flag on the original. The original module is
bound by `tests/test_q51_maker_fillsim.py::test_module_computes_no_queue_position_or_time_to_fill_number`,
which asserts its report and rows carry NO key containing "queue" / "queue_ahead" /
"queue_position" (the ~3h book cadence cannot support a queue-POSITION or time-to-fill
claim). Adding a queue-aware branch to that report would break, or force the weakening of,
a binding invariant. It is not weakened here; the original module is imported READ-ONLY,
never monkeypatched, and its behaviour and report shape are unchanged (pinned by
`tests/test_q51_queue_aware_fillsim.py::test_regression_*`).

WHAT IS AND IS NOT CLAIMED. This is a SIZE gate, not a queue POSITION or a time-to-fill
number: it asks whether enough qualifying volume traded in the interval to clear the size
resting at the order's own price, never WHERE in that queue the order sat or WHEN it would
have filled. The ~3h cadence ceiling from milestone 2/3 is unchanged and restated in the
report.

THE RULE (deliberately the MOST GENEROUS size-aware rule the tape supports — it credits the
interval's ENTIRE cumulative qualifying volume against the queue, i.e. it assumes the order
sits at the BACK of its own price level but that every qualifying print in the interval eats
into that level; a real order also faces size joining behind/ahead intra-interval, which
this tape cannot see):

  1. RESTING SIZE AHEAD = the size at the order's own price level on the ENTRY snapshot's
     OWN-SIDE ladder in `tape/orderbook_depth/`: the `yes_bids` ladder for a `yes_bid` leg,
     the `no_bids` ladder for a `no_bid` leg. A NO bid is NOT mirrored to `1 - p` on the YES
     ladder — its own NO ladder is read directly (the mirrored quote is a derived view; the
     resting SIZE lives on the side it actually rests on). Sizes are carried as FLOATS
     throughout, never coerced to int (L47 — a real observed best-level size was 91,316.82).
  2. QUALIFYING VOLUME = the sum of `count` over ALL `broker_truth` prints in the same
     left-open/right-closed interval (t0, t1] that satisfy the SAME side/price predicate the
     headline probe uses. The predicate is not re-implemented: each print is passed through
     the original module's own `yes_bid_fill` / `no_bid_fill` singleton-wise, so the two
     branches can never drift apart.
  3. FILL IFF `cumulative_qualifying_volume >= resting_size_ahead` (INCLUSIVE `>=`). The
     boundary is load-bearing and is pinned by a test: on the committed slice a strict `>`
     yields 24 fills / 8.163% / mean +$0.002449 instead of 25 / 8.503% / +$0.000714.
  4. A leg the headline did not fill can never become a queue-aware fill: the size gate is
     applied ON TOP of the headline predicate, so a leg with zero qualifying prints stays
     unfilled even if its resting size were 0.0 (0 >= 0 must not fabricate a fill).
  5. If the entry snapshot's own-side ladder carries no level at the rest price, the leg is
     scored NOT FILLED and counted in `queue_depth_profile.n_entry_price_level_missing`.
     On the committed dt=2026-08-03 slice that count is 0, so no verdict here rests on the
     convention.

RECONCILIATION WITH L337's CITED SIDE-NUMBERS (measured here, not restated): median resting
size ahead 500.74 contracts, median CREDITING print 8.905, and 4/64 = 6.25% of headline fills
whose crediting print ALONE clears the queue — all three reproduce the verifier's ad hoc
read. The 6.2% figure is specifically about the CREDITING (earliest qualifying) print, the
one the headline rule attributes the fill to; the more generous "largest qualifying print in
the interval" reading gives 13/64 = 20.3%. Both are reported in `queue_depth_profile` so the
next reader does not have to re-derive which one a 6% is.

TIE-BREAK EXPOSURE (L323, triaged in `scripts/invariants.py::TRADE_PRINT_TIEBREAK_TRIAGE`).
The size gate is a SUM over the interval's qualifying prints, so no exact-timestamp tie order
can change a fill, a P&L or a CI. The `crediting_print_size` diagnostics do inherit the Q51
loader's file-order tie-break: 14 of the 64 headline fills have a tie at the crediting
instant and 12 of those disagree on `count`; reversing the tie order moves
`n_headline_fills_cleared_by_the_crediting_print` 4 -> 5 and `median_crediting_print_size`
8.905 -> 11.22, with every fill count, mean and CI unchanged.

Everything statistical is IMPORTED, never re-implemented: the fee model
(`core.pricing.MAKER_FEE_RATE`, via the original module's `leg_pnl`), the block bootstrap by
GAME (L6), L41 admissibility, the L27 tick-magnitude gate and the `sign_bounded_objective`
check all come from `scripts/q51_maker_fillsim.verdict_for`, applied to the discounted rows.

BOTH branches are computed INDEPENDENTLY through that machinery, never rescaled from the
headline: `all_intervals` (headline-equivalent, an interval with no print is a MEASURED
no-fill) and `covered_intervals` (>=1 print; conditions on activity, sensitivity only).

VERDICT IMPACT: none. The discount runs toward the null — S13/S23/S29 stay `dead x`. What
changes is that the 21.77% / +$0.010068 headline is now accompanied by its own upper-bound
factor instead of an unquantified caveat.

READ-ONLY, 100% OFFLINE. No network, no credentials, no order path. Reads the committed
tape and the FROZEN milestone-3 settlement snapshot (`settlement-m3-2026-08-10.json`, not
the mutable `settlement.json`, which a later sweep overwrites — L191/L284/L325).

Run:
    python3 scripts/q51_queue_aware_fillsim.py
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.io import REPO_ROOT  # noqa: E402
from scripts import q51_maker_fillsim as M  # noqa: E402

DAY = M.DAY
#: The FROZEN milestone-3 settlement input. `M.CACHE_PATH` (settlement.json) is rewritten in
#: place by every `--build-cache` sweep; pinning the snapshot keeps these numbers sourced.
M3_CACHE_PATH = M.CACHE_PATH.parent / "settlement-m3-2026-08-10.json"
REPORT_PATH = REPO_ROOT / "reports" / "q51_queue_aware_fillsim.json"
ROWS_PATH = REPO_ROOT / "reports" / "q51_queue_aware_fillsim_rows.jsonl"

N_BOOT = M.N_BOOT
SEED = M.SEED
#: The maker rate, sourced from the original module (which sources core.pricing) — L5.
FEE_RATE = M.FEE_RATE

PRICE_EPS = 1e-9


# --------------------------------------------------------------------------- #
# ladders
# --------------------------------------------------------------------------- #
def load_ladders(day: str = DAY, path: Optional[Path] = None
                 ) -> Dict[Tuple[str, str], Dict[str, List[Tuple[float, float]]]]:
    """(ticker, captured_at) -> {"yes_bids": [(price, size)], "no_bids": [(price, size)]}.

    Sizes stay FLOAT (L47). The depth tape's `(ticker, captured_at)` pairs are unique on the
    committed slice; a later duplicate would overwrite an earlier one, which is why the
    lookup key is the row's own `entry_captured_at` string rather than a positional index.
    """
    p = path or (M.DEPTH_TAPE / f"dt={day}.jsonl")
    out: Dict[Tuple[str, str], Dict[str, List[Tuple[float, float]]]] = {}
    if not p.exists():
        return out
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            tk, cap = rec.get("ticker"), rec.get("captured_at")
            if not tk or not cap:
                continue
            out[(tk, cap)] = {
                "yes_bids": _levels(rec.get("yes_bids")),
                "no_bids": _levels(rec.get("no_bids")),
            }
    return out


def _levels(raw: Any) -> List[Tuple[float, float]]:
    """[[price, size], ...] -> [(float price, float size)], size never int-coerced (L47)."""
    out: List[Tuple[float, float]] = []
    for lv in raw or []:
        if not isinstance(lv, (list, tuple)) or len(lv) < 2:
            continue
        pr, sz = lv[0], lv[1]
        if not isinstance(pr, (int, float)) or not isinstance(sz, (int, float)):
            continue
        out.append((float(pr), float(sz)))
    return out


def resting_size_at(levels: Sequence[Tuple[float, float]], price: float) -> Optional[float]:
    """Size resting AT `price` on this ladder, or None if the ladder has no such level."""
    for lv_price, lv_size in levels:
        if abs(lv_price - price) < PRICE_EPS:
            return float(lv_size)
    return None


def own_side_ladder(ladder: Dict[str, List[Tuple[float, float]]], side: str
                    ) -> List[Tuple[float, float]]:
    """The ladder the order actually rests on. A NO bid is read off `no_bids`, NEVER mirrored
    onto the YES ladder at `1 - price` (the mirror is a price view, not a size view)."""
    return ladder.get("yes_bids" if side == "yes_bid" else "no_bids") or []


# --------------------------------------------------------------------------- #
# qualifying volume — the headline predicate, reused print-by-print
# --------------------------------------------------------------------------- #
def qualifying_prints(prints: Sequence[dict], t0: float, t1: float, side: str,
                      price: float) -> List[dict]:
    """Every print in (t0, t1] that the HEADLINE fill predicate would have credited.

    The predicate is not re-stated here: each print is handed to the original module's own
    `yes_bid_fill` / `no_bid_fill` as a one-element sequence, so this branch and the headline
    branch cannot drift. The headline uses the FIRST such print; this rule uses all of them.
    """
    filler = M.yes_bid_fill if side == "yes_bid" else M.no_bid_fill
    return [pr for pr in prints if filler([pr], t0, t1, price) is not None]


def qualifying_volume(prints: Sequence[dict], t0: float, t1: float, side: str,
                      price: float) -> Dict[str, float]:
    """Volume summary of the interval's qualifying prints. All sizes FLOAT (L47).

    `crediting` is the size of the EARLIEST qualifying print — the single print the headline
    rule credits the whole fill to; `largest` is the biggest one in the interval; `volume` is
    the cumulative total the queue gate actually spends. Reporting all three is what lets the
    headline's size-blindness be quantified rather than asserted.
    """
    qs = qualifying_prints(prints, t0, t1, side, price)
    counts = [float(pr.get("count") or 0.0) for pr in qs]
    return {
        "volume": sum(counts),
        "n_prints": float(len(qs)),
        "largest": max(counts) if counts else 0.0,
        "crediting": counts[0] if counts else 0.0,
    }


def clears_queue(cumulative_volume: float, resting_size_ahead: Optional[float]) -> bool:
    """The size gate: INCLUSIVE `>=`. `None` (no level at the rest price) is NOT a fill."""
    if resting_size_ahead is None:
        return False
    return cumulative_volume >= resting_size_ahead


# --------------------------------------------------------------------------- #
# discounting the headline rows
# --------------------------------------------------------------------------- #
def apply_queue_discount(rows: Sequence[dict], ladders: Dict, prints: Dict[str, List[dict]],
                         ) -> Tuple[List[dict], dict]:
    """Return (queue-aware rows, profile). Input rows are COPIED, never mutated.

    A queue-aware row keeps the headline's own fields under `headline_*` and overwrites
    `filled` / `pnl` / `fill_trade_id` so the shared `verdict_for` machinery scores the
    discounted leg without knowing anything about this module.
    """
    out: List[dict] = []
    profile = {
        "n_headline_fills": 0,
        "n_queue_aware_fills": 0,
        "n_entry_price_level_missing": 0,
        "n_headline_fills_cleared_by_the_crediting_print": 0,
        "n_headline_fills_cleared_by_the_largest_single_print": 0,
        "resting_size_ahead_at_headline_fills": [],
        "qualifying_volume_at_headline_fills": [],
        "crediting_print_size_at_headline_fills": [],
    }
    for r in rows:
        row = dict(r)
        headline_filled = bool(r["filled"])
        t0 = M.parse_ts(r["entry_captured_at"])
        t1 = M.parse_ts(r["next_captured_at"])
        ladder = ladders.get((r["ticker"], r["entry_captured_at"]))
        side, price = r["side"], float(r["rest_price"])
        resting = (resting_size_at(own_side_ladder(ladder, side), price)
                   if ladder is not None else None)
        vq = {"volume": 0.0, "n_prints": 0.0, "largest": 0.0, "crediting": 0.0}
        if headline_filled and t0 is not None and t1 is not None:
            vq = qualifying_volume(prints.get(r["ticker"]) or [], t0, t1, side, price)
        vol = vq["volume"]
        # rule 4: the size gate only ever REMOVES a headline fill, never creates one
        queue_filled = headline_filled and clears_queue(vol, resting)

        if headline_filled:
            profile["n_headline_fills"] += 1
            if resting is None:
                profile["n_entry_price_level_missing"] += 1
            else:
                profile["resting_size_ahead_at_headline_fills"].append(resting)
                profile["qualifying_volume_at_headline_fills"].append(vol)
                profile["crediting_print_size_at_headline_fills"].append(vq["crediting"])
                if vq["crediting"] >= resting:
                    profile["n_headline_fills_cleared_by_the_crediting_print"] += 1
                if vq["largest"] >= resting:
                    profile["n_headline_fills_cleared_by_the_largest_single_print"] += 1
            if queue_filled:
                profile["n_queue_aware_fills"] += 1

        row.update({
            "headline_filled": headline_filled,
            "headline_fill_trade_id": r.get("fill_trade_id"),
            "headline_pnl": float(r["pnl"]),
            "resting_size_ahead": resting,
            "resting_size_source_tag": "real_bid",
            "n_qualifying_prints": int(vq["n_prints"]),
            "qualifying_volume": vol,
            "crediting_print_size": vq["crediting"],
            "largest_qualifying_print": vq["largest"],
            "queue_aware_filled": queue_filled,
            # fields the shared verdict machinery reads:
            "filled": queue_filled,
            "pnl": float(r["pnl"]) if queue_filled else 0.0,
            "fill_trade_id": r.get("fill_trade_id") if queue_filled else None,
            "fill_price_source_tag": "broker_truth" if queue_filled else None,
        })
        out.append(row)

    profile["median_resting_size_ahead"] = _median(profile.pop(
        "resting_size_ahead_at_headline_fills"))
    profile["median_qualifying_volume"] = _median(profile.pop(
        "qualifying_volume_at_headline_fills"))
    profile["median_crediting_print_size"] = _median(profile.pop(
        "crediting_print_size_at_headline_fills"))
    n = profile["n_headline_fills"]
    profile["share_of_headline_fills_cleared_by_the_crediting_print"] = (
        profile["n_headline_fills_cleared_by_the_crediting_print"] / n) if n else None
    profile["share_of_headline_fills_cleared_by_the_largest_single_print"] = (
        profile["n_headline_fills_cleared_by_the_largest_single_print"] / n) if n else None
    profile["share_of_headline_fills_surviving_queue_gate"] = (
        profile["n_queue_aware_fills"] / n) if n else None
    return out, profile


def _median(xs: Sequence[float]) -> Optional[float]:
    s = sorted(float(x) for x in xs)
    if not s:
        return None
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2.0


def informative_units(rows: Sequence[dict]) -> int:
    """Bootstrap units (GAMES) carrying at least one non-zero leg. The L41 floor is 10 units,
    but a unit whose every leg is an exact 0.0 carries no information about the mean, so this
    count is reported beside `n_units_games` rather than hidden behind it."""
    units: Dict[str, List[float]] = {}
    for r in rows:
        units.setdefault(r["game"], []).append(float(r["pnl"]))
    return sum(1 for v in units.values() if any(x != 0.0 for x in v))


def discount_factor(headline: dict, queue_aware: dict) -> dict:
    """The L337 deliverable: before/after fill count, rate and mean, side by side."""
    def ratio(after: Optional[float], before: Optional[float]) -> Optional[float]:
        if before in (None, 0) or after is None:
            return None
        return after / before
    return {
        "n_legs": headline["n_legs"],
        "fills_headline": headline["n_filled_legs"],
        "fills_queue_aware": queue_aware["n_filled_legs"],
        "fills_removed": headline["n_filled_legs"] - queue_aware["n_filled_legs"],
        "fill_rate_headline": headline["fill_rate"],
        "fill_rate_queue_aware": queue_aware["fill_rate"],
        "fill_rate_retained_fraction": ratio(queue_aware["fill_rate"], headline["fill_rate"]),
        "mean_headline": headline["mean"],
        "mean_queue_aware": queue_aware["mean"],
        "mean_retained_fraction": ratio(queue_aware["mean"], headline["mean"]),
        "ci95_headline": headline["ci95"],
        "ci95_queue_aware": queue_aware["ci95"],
        "informative_units_headline": headline["n_informative_units"],
        "informative_units_queue_aware": queue_aware["n_informative_units"],
        "n_units_games": headline["n_units_games"],
    }


def verdict_for(rows: Sequence[dict], label: str, n_boot: int, seed: int) -> dict:
    """The ORIGINAL module's verdict machinery (block bootstrap by game, L41 admissibility,
    L27 tick gate, sign_bounded_objective), plus the informative-unit count."""
    v = M.verdict_for(rows, label, n_boot=n_boot, seed=seed)
    v["n_informative_units"] = informative_units(rows)
    return v


# --------------------------------------------------------------------------- #
def run(day: str = DAY, n_boot: int = N_BOOT, seed: int = SEED,
        cache_path: Path = M3_CACHE_PATH) -> Tuple[dict, List[dict]]:
    headline_report, headline_rows = M.run(day=day, n_boot=n_boot, seed=seed,
                                           cache_path=cache_path)
    ladders = load_ladders(day)
    prints = M.load_prints(day)
    queue_rows, profile = apply_queue_discount(headline_rows, ladders, prints)

    def branch(rows: Sequence[dict], covered_only: bool) -> Sequence[dict]:
        return [r for r in rows if r["interval_covered"]] if covered_only else list(rows)

    verdicts = {
        "headline": {
            "all_intervals": verdict_for(
                branch(headline_rows, False),
                "HEADLINE any-print rule / all_intervals (UPPER BOUND — L337)",
                n_boot, seed),
            "covered_intervals": verdict_for(
                branch(headline_rows, True),
                "HEADLINE any-print rule / covered_intervals (UPPER BOUND — L337)",
                n_boot, seed),
        },
        "queue_aware": {
            "all_intervals": verdict_for(
                branch(queue_rows, False),
                "QUEUE-AWARE size gate / all_intervals (conservative branch)",
                n_boot, seed),
            "covered_intervals": verdict_for(
                branch(queue_rows, True),
                "QUEUE-AWARE size gate / covered_intervals (conditions on activity)",
                n_boot, seed),
        },
    }
    discount = {
        k: discount_factor(verdicts["headline"][k], verdicts["queue_aware"][k])
        for k in ("all_intervals", "covered_intervals")
    }
    fills = [r for r in queue_rows if r["queue_aware_filled"]]
    untraced = [r for r in fills if not r.get("fill_trade_id")]
    report = {
        "schema_version": "q51_queue_aware_fillsim.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "day": day,
        "lesson": "L337",
        "settlement_cache": str(Path(cache_path).name),
        "headline_module": "scripts/q51_maker_fillsim.py",
        "headline_schema_version": headline_report["schema_version"],
        "population": headline_report["population"],
        "intervals": headline_report["intervals"],
        "queue_rule": (
            "fill iff cumulative qualifying volume in (t0,t1] >= the size resting at the "
            "order's OWN price on the entry snapshot's OWN-SIDE ladder (yes_bids for a "
            "yes_bid leg, no_bids for a no_bid leg; a NO bid is never mirrored to 1-p). "
            "Inclusive >=. Applied ON TOP of the headline predicate, so it can only remove "
            "a fill, never create one."),
        "queue_depth_profile": profile,
        "resolution_ceiling": (
            "book cadence is ~3h. This is a SIZE gate only: it asks whether enough "
            "qualifying volume traded to clear the size resting at the order's own price. "
            "No queue POSITION, time-to-fill or sub-interval adverse-selection number is "
            "computed or claimable, exactly as in the headline module."),
        "fill_traceability": {
            "n_fills": len(fills),
            "n_fills_traced_to_broker_truth_print": len(fills) - len(untraced),
            "all_fills_traced": not untraced,
        },
        "discount_factor": discount,
        "verdicts": verdicts,
        "verdict_class_change": False,
        "verdict_note": (
            "The discount runs TOWARD the null: both queue-aware CIs still straddle zero and "
            "still fail the L27 tick gate. S13/S23/S29 remain dead; what changes is that the "
            "headline fill rate and mean are now labelled with their measured upper-bound "
            "factor instead of an unquantified caveat."),
    }
    return report, queue_rows


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="L337 queue-aware discount on Q51 milestone 3")
    ap.add_argument("--day", default=DAY)
    ap.add_argument("--n-boot", type=int, default=N_BOOT)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--cache", default=str(M3_CACHE_PATH),
                    help="settlement cache (default: the FROZEN milestone-3 snapshot)")
    ap.add_argument("--json-out", default=str(REPORT_PATH))
    ap.add_argument("--rows-out", default=str(ROWS_PATH))
    args = ap.parse_args(argv)

    report, rows = run(day=args.day, n_boot=args.n_boot, seed=args.seed,
                       cache_path=Path(args.cache))

    Path(args.rows_out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.rows_out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")
    with open(args.json_out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1, sort_keys=True)

    pf = report["queue_depth_profile"]
    print(f"[q51:queue] day={report['day']} cache={report['settlement_cache']} "
          f"fee_rate={FEE_RATE}")
    print(f"[q51:queue] headline fills={pf['n_headline_fills']} -> queue-aware "
          f"{pf['n_queue_aware_fills']}  median resting size ahead="
          f"{pf['median_resting_size_ahead']}  median crediting print="
          f"{pf['median_crediting_print_size']}  median qualifying volume="
          f"{pf['median_qualifying_volume']}")
    print(f"[q51:queue] headline fills whose CREDITING print alone clears the queue="
          f"{pf['n_headline_fills_cleared_by_the_crediting_print']} "
          f"({pf['share_of_headline_fills_cleared_by_the_crediting_print']});"
          f" whose LARGEST qualifying print does="
          f"{pf['n_headline_fills_cleared_by_the_largest_single_print']} "
          f"({pf['share_of_headline_fills_cleared_by_the_largest_single_print']}); "
          f"entry price level missing={pf['n_entry_price_level_missing']}")
    for rule in ("headline", "queue_aware"):
        for br in ("all_intervals", "covered_intervals"):
            v = report["verdicts"][rule][br]
            print(f"  {rule:<12} {br:<18} legs={v['n_legs']} fills={v['n_filled_legs']} "
                  f"rate={v['fill_rate']} units={v['n_units_games']} "
                  f"inf={v['n_informative_units']} mean={v['mean']} ci95={v['ci95']} "
                  f"admissible={v['admissible']} tick={v['clears_tick_magnitude']} "
                  f"-> {v['verdict']}")
    for br, d in report["discount_factor"].items():
        print(f"  DISCOUNT {br}: fills {d['fills_headline']}->{d['fills_queue_aware']}  "
              f"rate {d['fill_rate_headline']}->{d['fill_rate_queue_aware']} "
              f"(x{d['fill_rate_retained_fraction']})  mean {d['mean_headline']}->"
              f"{d['mean_queue_aware']} (x{d['mean_retained_fraction']})")
    print(f"[q51:queue] wrote {args.json_out} and {args.rows_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
