#!/usr/bin/env python3
"""Q51 MILESTONE-3 FILL PROJECTION: how many of milestone 3's legs can EVER fill, and what
does the larger population do to the two fill rates the probe reports?

Read-only, fully offline, NO network. Computes NO settlement outcome, NO P&L, NO mean, NO
bootstrap, NO CI and NO verdict about the strategy. It is a DATA-ADEQUACY instrument, not a
probe (the `scripts/q37_bootstrap_unit_preflight.py` / `scripts/q51_m3_preflight.py`
precedent). The two-agent verdict rule does not apply to what it prints, because nothing it
prints is verdict-class.

WHY THIS EXISTS
---------------
`scripts/q51_m3_preflight.py` (2026-08-05) answered milestone 3's POPULATION question — an
08-10 firing buys 44 game units / 128 intervals / 256 legs, four times the L41 floor of 10,
so FIRE ON 08-10 AS GATED. It did not ask the next question, and nothing else has:

    of those 256 legs, how many can ever FILL?

That question is answerable TODAY, outcome-independently, because a fill in
`scripts/q51_maker_fillsim.py` is decided by BOOK + PRINTS alone:
`yes_bid_fill`/`no_bid_fill` read `tape/orderbook_depth/` and `tape/kalshi_trades/` and
never touch the settlement cache. Settlement decides only WHICH legs are scored at all and
whether a filled leg WON — and `won` is exactly the thing this module refuses to compute.
So every count below is fixed by already-committed tape and cannot move on 08-10.

WHAT IT FINDS (the reason it is worth committing before the gate opens)
----------------------------------------------------------------------
Milestone 2's headline fill rate of 65.0% is NOT a property of the mechanism. It is a
property of the SETTLED SUBSET: on 2026-08-04 the only markets that had settled were the
games PLAYED on 2026-08-03, which are precisely the markets that TRADED on 2026-08-03. As
the settled population grows to include games played 08-04..08-09, whose 08-03 book
snapshots are pre-game and whose 08-03 prints are sparse, the headline branch fills a
steadily smaller share of its legs. Conditional on a covered interval the fill rate barely
moves. The headline number and the conditional number therefore diverge, and only the
conditional one is comparable across populations.

The consequence for reading the 08-10 result: on the `all_intervals` HEADLINE branch the
reported mean is, by construction, the exact identity

    mean_over_all_legs = (n_fills / n_legs) * mean_over_FILLED_legs

because an unfilled leg contributes an exact 0.0. That multiplier is not an estimate — it
is known today. If it falls, ANY per-fill edge is compressed by the same factor before the
L27 one-tick magnitude gate is applied to it. This module reports the multiplier and the
compression ratio and STOPS THERE: it deliberately does not multiply it by any per-fill
edge, because doing so would be a P&L forecast, which is verdict-class and outcome-dependent
and not this instrument's lane.

WHAT IT DOES NOT DO
-------------------
  * No settlement `result` is read for any purpose other than `close_time` (a schedule
    field, not an outcome). `won`, `pnl`, `mean`, `ci95` appear nowhere in the report and
    a test asserts the report is free of those tokens.
  * No queue-position, time-to-fill or sub-interval adverse-selection number, for the same
    reason the probe forbids them: the ~3h book cadence cannot support them (L283).
  * No recommendation to change `scripts/q51_maker_fillsim.py`. Milestone 3's spec requires
    that file to run UNCHANGED, and this module imports it rather than reimplementing it so
    the projection cannot drift from what will actually run.

REDUNDANCY (the sanctioned fallback when no `verifier` subagent is dispatchable)
-------------------------------------------------------------------------------
The projection calls the probe's OWN fill predicates, so it faithfully projects the probe —
but that means it also inherits any orientation error the probe has (the L279 failure mode).
`independent_fill_decisions()` therefore re-implements both predicates from the raw print
records on a separate code path (explicit cent arithmetic, its own window convention, its
own orientation constants passed in rather than module-level) and `run()` reports the number
of leg-level DISAGREEMENTS. Zero disagreement is a redundancy check, NOT a verifier
confirmation, and it cannot catch an error both paths share.

Run:
    python3 scripts/q51_m3_fill_projection.py
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from core.io import REPO_ROOT  # noqa: E402
from scripts import q51_maker_fillsim as M  # noqa: E402

# The FROZEN milestone-2 settlement snapshot (L284's repair). `close_time` is read from it
# and nothing else is. Using the frozen file rather than the live one keeps this projection
# reproducible after the 08-10 `--build-cache` overwrites `settlement.json`.
M2_CACHE = REPO_ROOT / "tape" / "q51_settlement_cache" / "settlement-m2-2026-08-04.json"
REPORT_PATH = REPO_ROOT / "reports" / "q51_m3_fill_projection.json"

# The fire dates `scripts/q51_m3_preflight.py` tabulates, so the two reports join row-wise.
FIRE_DATES = ("2026-08-04", "2026-08-09", "2026-08-10", "2026-08-12", "2026-08-23")

# Tokens this report is FORBIDDEN to contain. The first group is outcome-dependence (this
# instrument must not become a P&L forecast); the second is the probe's own L283 ceiling.
FORBIDDEN_REPORT_TOKENS = ("pnl", "mean", "ci95", "won", "settle_result", "profit",
                           "queue", "time_to_fill", "seconds_to_fill", "fill_latency")


# --------------------------------------------------------------------------- #
# leg enumeration — outcome-independent by construction
# --------------------------------------------------------------------------- #
def close_days(cache_path: Path = M2_CACHE) -> Dict[str, str]:
    """ticker -> `close_time`'s UTC date (a SCHEDULE field, never an outcome). Markets whose
    cache entry has no parseable close_time map to "" and are excluded from every dated row
    — an unknown close day is reported as unknown, never folded into a date bucket (L289)."""
    out: Dict[str, str] = {}
    for tk, rec in (M.load_settlement_cache(cache_path) or {}).items():
        ct = (rec or {}).get("close_time")
        out[tk] = ct[:10] if isinstance(ct, str) and len(ct) >= 10 else ""
    return out


def enumerate_legs(day: str = M.DAY, cache_path: Path = M2_CACHE,
                   depth: Optional[Tuple[List[str], Dict[str, List[dict]]]] = None,
                   prints: Optional[Dict[str, List[dict]]] = None) -> List[dict]:
    """One record per (ticker, interval, side) the probe WOULD score if that ticker's market
    were settled with a binary result — with the fill decision resolved from committed tape.

    The eligibility filters are the probe's own, applied in the probe's own order:
    `len(snapshots) < 2` drops the ticker; `entry_ts >= close_ts` drops the interval
    (post-close); a non-positive or non-numeric `best_yes_bid`/`best_no_bid` drops the
    interval (one-sided book). What is NOT applied is the settlement filter — that is the
    whole point: this enumerates the legs a LARGER settled population unlocks.

    Carries `rest_price` tagged `real_bid` and, for a fill, `fill_trade_id` tagged
    `broker_truth`. Carries no outcome and no P&L.
    """
    order, snaps = depth if depth is not None else M.load_depth(day)
    pl_by_ticker = prints if prints is not None else M.load_prints(day)
    universe = [t for t in M.reconstruct_sample(order) if M.is_sports_game_market(t)]
    cds = close_days(cache_path)

    legs: List[dict] = []
    for tk in universe:
        ss = snaps.get(tk) or []
        if len(ss) < 2:
            continue
        pl = pl_by_ticker.get(tk) or []
        close_ts = _close_ts(tk, cache_path)
        for a, b in zip(ss[:-1], ss[1:]):
            covered = any(a["ts"] < pr["ts"] <= b["ts"] for pr in pl)
            if close_ts is not None and a["ts"] >= close_ts:
                continue
            ybid, nbid = a.get("best_yes_bid"), a.get("best_no_bid")
            if not isinstance(ybid, (int, float)) or not isinstance(nbid, (int, float)) \
                    or ybid <= 0 or nbid <= 0:
                continue
            for side, price, filler in (("yes_bid", float(ybid), M.yes_bid_fill),
                                        ("no_bid", float(nbid), M.no_bid_fill)):
                pr = filler(pl, a["ts"], b["ts"], price)
                legs.append({
                    "ticker": tk,
                    "game": M.game_of(tk),
                    "close_day": cds.get(tk, ""),
                    "side": side,
                    "entry_captured_at": a["captured_at"],
                    "next_captured_at": b["captured_at"],
                    "rest_price": price,
                    "price_source_tag": "real_bid",
                    "interval_covered": covered,
                    "filled": pr is not None,
                    "fill_trade_id": (pr or {}).get("trade_id"),
                    "fill_evidence_tag": "broker_truth" if pr else None,
                })
    return legs


_CLOSE_TS_CACHE: Dict[Tuple[str, str], Optional[float]] = {}


def _close_ts(ticker: str, cache_path: Path) -> Optional[float]:
    key = (str(cache_path), ticker)
    if key not in _CLOSE_TS_CACHE:
        rec = (M.load_settlement_cache(cache_path) or {}).get(ticker) or {}
        _CLOSE_TS_CACHE[key] = M.parse_ts(rec.get("close_time"))
    return _CLOSE_TS_CACHE[key]


# --------------------------------------------------------------------------- #
# redundancy: a second, independent implementation of the two fill predicates
# --------------------------------------------------------------------------- #
def independent_fill_decisions(legs: Sequence[dict], day: str = M.DAY,
                               prints: Optional[Dict[str, List[dict]]] = None,
                               taker_buys: str = "bid",
                               taker_sells: str = "ask") -> List[bool]:
    """Recompute each leg's fill on a separate code path: integer-cent comparison instead of
    a float epsilon, an explicit half-open window written out rather than the probe's
    two-sided guard, and the orientation supplied as ARGUMENTS so it is visibly a parameter
    and not a module constant. Returns one bool per leg, positionally aligned.

    This is a REDUNDANCY CHECK, not a verifier: both paths read the same tape and share the
    L279 orientation premise, so an error in that premise would be invisible to it. Stated
    plainly because the milestone-2 run's own redundancy check made exactly this mistake."""
    pl_by_ticker = prints if prints is not None else M.load_prints(day)
    out: List[bool] = []
    for leg in legs:
        pl = pl_by_ticker.get(leg["ticker"]) or []
        t0 = M.parse_ts(leg["entry_captured_at"])
        t1 = M.parse_ts(leg["next_captured_at"])
        if t0 is None or t1 is None:
            out.append(False)
            continue
        cents = int(round(float(leg["rest_price"]) * 100))
        hit = False
        for pr in pl:
            ts = pr["ts"]
            if not (t0 < ts <= t1):
                continue
            yes_cents = int(round(float(pr["yes_price"]) * 100))
            side = pr.get("taker_book_side")
            if leg["side"] == "yes_bid":
                if side == taker_sells and yes_cents <= cents:
                    hit = True
                    break
            else:
                if side == taker_buys and yes_cents >= 100 - cents:
                    hit = True
                    break
        out.append(hit)
    return out


# --------------------------------------------------------------------------- #
# projection
# --------------------------------------------------------------------------- #
def project(legs: Sequence[dict], fire_date: str) -> dict:
    """Counts for the population a firing on `fire_date` unlocks — every market whose
    `close_day` is on or before it. An UPPER BOUND for the same reasons
    `scripts/q51_m3_preflight.py` states: settlement lag and L52 non-binary results can
    only reduce the scored population, never enlarge it."""
    sel = [x for x in legs if x["close_day"] and x["close_day"] <= fire_date]
    cov = [x for x in sel if x["interval_covered"]]
    n_fills = sum(1 for x in sel if x["filled"])
    n_fills_cov = sum(1 for x in cov if x["filled"])
    by_side = {}
    for s in ("yes_bid", "no_bid"):
        ss = [x for x in sel if x["side"] == s]
        f = sum(1 for x in ss if x["filled"])
        by_side[s] = {"n_legs": len(ss), "n_fills": f,
                      "fill_rate": (f / len(ss)) if ss else None}
    # an interval contributes 2 legs, so interval counts are leg counts halved only when
    # both sides survived the one-sided-book filter; count them directly instead.
    intervals = {(x["ticker"], x["entry_captured_at"]) for x in sel}
    intervals_cov = {(x["ticker"], x["entry_captured_at"]) for x in cov}
    return {
        "fire_date": fire_date,
        "n_markets": len({x["ticker"] for x in sel}),
        "n_units_games": len({x["game"] for x in sel}),
        "n_scored_intervals": len(intervals),
        "n_covered_intervals": len(intervals_cov),
        "interval_coverage": (len(intervals_cov) / len(intervals)) if intervals else None,
        "all_intervals": {
            "n_legs": len(sel), "n_fills": n_fills,
            "fill_rate": (n_fills / len(sel)) if sel else None,
            "n_units_games": len({x["game"] for x in sel}),
            "n_structurally_unfillable_legs": len(sel) - len(cov),
        },
        "covered_intervals": {
            "n_legs": len(cov), "n_fills": n_fills_cov,
            "fill_rate": (n_fills_cov / len(cov)) if cov else None,
            "n_units_games": len({x["game"] for x in cov}),
        },
        "by_side": by_side,
        "price_source_tag": "real_bid",
        "fill_evidence_tag": "broker_truth",
        "close_day_source_tag": "broker_truth",
        "bound": "upper",
    }


def marginal_table(rows: Sequence[dict]) -> List[dict]:
    """Between consecutive fire dates: how many legs and how many FILLS does waiting buy?
    A row whose `d_fills` is ~0 while `d_legs` is large says the later sweep adds resample
    units made almost entirely of legs that cannot fill."""
    out = []
    for prev, cur in zip(rows[:-1], rows[1:]):
        d_legs = cur["all_intervals"]["n_legs"] - prev["all_intervals"]["n_legs"]
        d_fills = cur["all_intervals"]["n_fills"] - prev["all_intervals"]["n_fills"]
        out.append({
            "from": prev["fire_date"], "to": cur["fire_date"],
            "d_legs": d_legs, "d_fills": d_fills,
            "d_units_games": cur["n_units_games"] - prev["n_units_games"],
            "marginal_fill_rate": (d_fills / d_legs) if d_legs else None,
        })
    return out


def compression(rows: Sequence[dict], base: str, target: str) -> dict:
    """The ARITHMETIC identity, not a forecast. On the `all_intervals` branch an unfilled leg
    contributes an exact 0.0, so the reported mean equals `fill_rate` times the mean over
    FILLED legs. This reports how that multiplier moves between two fire dates. It does NOT
    multiply it by any edge: that would be a P&L projection, which is outcome-dependent and
    verdict-class, and this instrument does not compute one."""
    r = {x["fire_date"]: x for x in rows}
    b, t = r.get(base), r.get(target)
    if not b or not t:
        return {}
    fb = b["all_intervals"]["fill_rate"]
    ft = t["all_intervals"]["fill_rate"]
    cb = b["covered_intervals"]["fill_rate"]
    ct = t["covered_intervals"]["fill_rate"]
    return {
        "base_fire_date": base, "target_fire_date": target,
        "all_intervals_fill_rate_base": fb, "all_intervals_fill_rate_target": ft,
        "all_intervals_compression_x": (fb / ft) if (fb and ft) else None,
        "covered_intervals_fill_rate_base": cb, "covered_intervals_fill_rate_target": ct,
        "covered_intervals_compression_x": (cb / ct) if (cb and ct) else None,
        "identity": ("mean_over_all_legs == (n_fills / n_legs) * mean_over_FILLED_legs; "
                     "an unfilled leg contributes exactly 0.0"),
        "explicitly_not_computed": "any product of this multiplier with a per-fill edge",
    }


def drops_unit_audit() -> dict:
    """`scripts/q51_maker_fillsim.py::build_rows`'s `drops` dict MIXES UNITS: five keys count
    INTERVALS (`+= len(ss) - 1`, or `+= 1` inside the per-interval loop) while
    `single_snapshot` counts TICKERS (`+= 1` in the per-ticker loop, for a ticker that
    contributes ZERO intervals). The dict is emitted under `report["intervals"]` beside
    `n_intervals`, which invites reading every value as an interval count and summing them.
    Read-only observation: milestone 3's spec requires the probe to run UNCHANGED, so this is
    reported, not repaired. Same defect class as L289/L296 (a counter whose denominator means
    two different things)."""
    return {
        "keys_counting_intervals": ["no_settlement", "non_binary_result", "unsettled",
                                    "not_two_sided", "post_close"],
        "keys_counting_tickers": ["single_snapshot"],
        "consequence": ("sum(drops.values()) is not a count of anything; a ticker with <2 "
                        "snapshots contributes 0 intervals yet adds 1 to the dict"),
        "milestone_2_observed": {"single_snapshot": 3, "unsettled": 145},
        "repair_status": ("REPORTED NOT REPAIRED — milestone 3 requires "
                          "scripts/q51_maker_fillsim.py to run UNCHANGED"),
    }



def calibration_vs_milestone_2(rows: Sequence[dict],
                               observed_report: Path = REPO_ROOT / "reports" / "q51_maker_fillsim.json",
                               proxy_fire_date: str = "2026-08-04") -> dict:
    """Measure the PROXY's own error instead of asserting it. This module buckets a market by
    `close_day <= fire_date`; milestone 2's probe bucketed it by whether the venue had
    actually published a binary `result` at the 2026-08-04 pull instant. Those are different
    predicates and the difference is exactly the settlement LAG the projection calls an upper
    bound. Comparing the 08-04 projection row against the committed milestone-2 report turns
    "upper bound" from a claim into a measured direction. Returns {} if the observed report is
    absent, so this can never fail a run."""
    if not observed_report.exists():
        return {}
    try:
        rep = json.load(open(observed_report, encoding="utf-8"))
        head = rep["verdicts"]["all_intervals"]
        obs = {
            "n_scored_intervals": rep["intervals"]["n_intervals"],
            "n_covered_intervals": rep["intervals"]["n_covered_intervals"],
            "n_legs": head["n_legs"],
            "n_fills": head["n_filled_legs"],
            "n_units_games": head["n_units_games"],
        }
    except Exception:
        return {}
    row = {x["fire_date"]: x for x in rows}.get(proxy_fire_date)
    if not row:
        return {}
    proj = {
        "n_scored_intervals": row["n_scored_intervals"],
        "n_covered_intervals": row["n_covered_intervals"],
        "n_legs": row["all_intervals"]["n_legs"],
        "n_fills": row["all_intervals"]["n_fills"],
        "n_units_games": row["n_units_games"],
    }
    delta = {k: proj[k] - obs[k] for k in obs}
    return {
        "proxy_fire_date": proxy_fire_date,
        "proxy_predicate": "close_day <= fire_date",
        "observed_predicate": "venue published a binary result at the 2026-08-04 pull",
        "projected": proj,
        "observed_milestone_2": obs,
        "delta_projected_minus_observed": delta,
        "direction": ("over-inclusive" if all(v >= 0 for v in delta.values())
                      else "MIXED — the upper-bound claim does not hold on every count"),
        "reading": ("a non-negative delta on every count is what an UPPER BOUND must look "
                    "like; a negative one would falsify the bound and is reported as MIXED"),
    }


# --------------------------------------------------------------------------- #
def run(day: str = M.DAY, cache_path: Path = M2_CACHE,
        fire_dates: Sequence[str] = FIRE_DATES) -> dict:
    legs = enumerate_legs(day=day, cache_path=cache_path)
    prints = M.load_prints(day)
    indep = independent_fill_decisions(legs, day=day, prints=prints)
    disagreements = [i for i, (leg, v) in enumerate(zip(legs, indep)) if leg["filled"] != v]

    unknown_close = sorted({x["ticker"] for x in legs if not x["close_day"]})
    rows = [project(legs, d) for d in fire_dates]
    return {
        "schema_version": "q51_m3_fill_projection.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "day": day,
        "settlement_cache": cache_path.name,
        "outcome_independent": True,
        "what_is_read_from_the_cache": "close_time only (a schedule field, never a result)",
        "n_legs_enumerated": len(legs),
        "n_markets_with_unknown_close_day": len(unknown_close),
        "markets_with_unknown_close_day": unknown_close,
        "projections": rows,
        "marginal": marginal_table(rows),
        "compression_m2_to_0810": compression(rows, "2026-08-04", "2026-08-10"),
        "compression_0810_to_terminal": compression(rows, "2026-08-10", "2026-08-23"),
        "calibration_vs_milestone_2": calibration_vs_milestone_2(rows),
        "drops_unit_audit": drops_unit_audit(),
        "redundancy_check": {
            "n_legs_cross_checked": len(legs),
            "n_disagreements": len(disagreements),
            "is_a_verifier": False,
            "limit": ("both paths read the same tape and share the L279 orientation "
                      "premise; an error in that premise is invisible to this check"),
        },
        "bound": "upper — settlement lag and L52 non-binary results can only reduce these",
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Q51 milestone-3 fill projection (read-only)")
    ap.add_argument("--day", default=M.DAY)
    ap.add_argument("--json-out", default=str(REPORT_PATH))
    args = ap.parse_args(argv)

    rep = run(day=args.day)
    Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.json_out, "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=1, sort_keys=True)

    print(f"[q51:m3fill] legs enumerated={rep['n_legs_enumerated']}  "
          f"redundancy disagreements={rep['redundancy_check']['n_disagreements']}")
    for r in rep["projections"]:
        a, c = r["all_intervals"], r["covered_intervals"]
        print(f"  fire {r['fire_date']}: markets={r['n_markets']:3d} units={r['n_units_games']:3d} "
              f"ivs={r['n_scored_intervals']:4d} cov={r['n_covered_intervals']:4d} "
              f"({r['interval_coverage']:.3f})  ALL legs={a['n_legs']:4d} fills={a['n_fills']:3d} "
              f"rate={a['fill_rate']:.4f}  || COVERED legs={c['n_legs']:4d} units={c['n_units_games']:3d} "
              f"fills={c['n_fills']:3d} rate={c['fill_rate']:.4f}")
    for m in rep["marginal"]:
        print(f"  marginal {m['from']}->{m['to']}: d_legs={m['d_legs']:4d} d_fills={m['d_fills']:3d} "
              f"d_units={m['d_units_games']:3d} marginal_fill_rate={m['marginal_fill_rate']}")
    print(f"[q51:m3fill] wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
