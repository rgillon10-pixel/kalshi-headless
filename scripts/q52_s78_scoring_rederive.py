#!/usr/bin/env python3
"""Independent re-derivation of the Q52/S78 sealed probe's SCORED half (P&L + bootstrap CI).

This is the sanctioned NO-VERIFIER REDUNDANCY FALLBACK, and it is reported as redundancy,
NEVER as verification (the L287/L288/L290/L291/L295/L308/L313/L325 precedent chain). The
two-agent verdict rule needs a second AGENT; this file is a second IMPLEMENTATION. A run
that has only this may commit the verdict PROVISIONAL and must not flip the registry.

Companion to `scripts/q52_s78_population_rederive.py`, which already re-derives the
OUTCOME-BLIND half (split, train cell table, admitted cells, candidate/fill/unit counts)
and agrees with the sealed probe on every one of those numbers. This file adds the only
part that re-derivation deliberately refused to touch while the gate was shut:

  * the settlement DIRECTION per ticker (`yes`/`no`), read straight at the committed
    cache/ledger files with its own first-hit precedence walk over the declared source
    order — never through `core.settlement_sources`;
  * the per-candidate realized P&L (unfilled candidates score an honest $0.00 — the
    sealed probe's pre-registered `all_candidates` headline branch);
  * a block bootstrap BY GAME with a HAND-ROLLED 64-bit LCG, deliberately not
    `random.Random`, so the CI is a genuinely independent Monte-Carlo estimate rather
    than a replay of the same stream. Two independent RNGs agree only up to Monte-Carlo
    error; the MEAN is exact and is the number that must match to the last digit.

Independence boundaries, stated rather than implied:
  * the maker FEE RATE is imported from `core.pricing` (L5 — a hand-rolled rate literal is
    a GATING invariant failure; the 4x maker/taker mix-up sank an S13 draft). What stays
    independent is the round-up-to-cent FORMULA and the payout arithmetic.
  * the loaders / cell rule / orientation / queue-aware fill loop come from the population
    re-derivation, which shares no code with the probe. Re-using them here keeps this file
    independent OF THE PROBE, which is the axis that matters.

Read-only. No network. No credentials. No `execution/` import. No order path.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys
from typing import Dict, List, Optional, Sequence, Tuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from scripts.q52_s78_population_rederive import (  # noqa: E402
    BAND_HI, BAND_LO, MAX_INTERVAL_S, MAX_STALENESS_S, MIN_EXCLUSIVE_MINORITY, MIN_UNITS,
    _fee, _game, cell, load, run as population_run)

# The declared settlement source order, restated (first hit wins, exactly as
# `core.settlement_sources.resolve_market_results` does). Restated ON PURPOSE: importing
# the tuple would make an agreement on precedence circular.
SOURCE_ORDER: Tuple[Tuple[str, str, str], ...] = (
    ("settlement_ledger", "settlement_ledger/dt=*.jsonl", "ledger"),
    ("q26_settlement_cache", "q26_settlement_cache/settlement*.json", "cache"),
    ("q27_settlement_cache", "q27_settlement_cache/settlement*.json", "cache"),
    ("q29_settlement_cache", "q29_settlement_cache/settlement*.json", "cache"),
    ("q30_settlement_cache", "q30_settlement_cache/settlement*.json", "cache"),
    ("q51_settlement_cache", "q51_settlement_cache/settlement*.json", "cache"),
    ("q56_settlement_cache", "q56_settlement_cache/settlement*.json", "cache"),
)

N_BOOT = 10000
SEED = 42
TICK = 0.01
MIN_TICKS = 1.0


# --------------------------------------------------------------------------- #
# Settlement DIRECTION — the value the outcome-blind re-derivation refused to read
# --------------------------------------------------------------------------- #
def _norm(result: object) -> Optional[str]:
    """'yes'/'no' or None. Anything else (scalar, blank, unknown) is NOT a loss (L52)."""
    if result is None:
        return None
    s = str(result).strip().lower()
    return s if s in ("yes", "no") else None


def settled_direction(root: Optional[str] = None) -> Tuple[Dict[str, str], Dict[str, dict]]:
    """Ticker -> 'yes'/'no' by first hit in declared source order, plus a conflict census.

    The conflict census is not decoration: two settlement families disagreeing about the
    same ticker would silently change the sign of a P&L, and a first-hit walk hides it.
    """
    base = root or os.path.join(REPO, "tape")
    first: Dict[str, str] = {}
    seen: Dict[str, Dict[str, str]] = {}
    for name, pattern, kind in SOURCE_ORDER:
        for path in sorted(glob.glob(os.path.join(base, pattern))):
            rows: List[dict] = []
            if kind == "cache":
                try:
                    blob = json.load(open(path))
                except Exception:
                    continue
                for tk, rec in (blob.get("markets") or {}).items():
                    if isinstance(rec, dict):
                        rows.append({"ticker": tk, "result": rec.get("result")})
            else:
                with open(path) as fh:
                    for line in fh:
                        if not line.strip():
                            continue
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            continue
            for r in rows:
                tk = r.get("ticker")
                res = _norm(r.get("result"))
                if not tk or res is None:
                    continue
                seen.setdefault(tk, {}).setdefault(name, res)
                if tk not in first:
                    first[tk] = res
    conflicts = {tk: srcs for tk, srcs in seen.items() if len(set(srcs.values())) > 1}
    return first, conflicts


# --------------------------------------------------------------------------- #
# P&L
# --------------------------------------------------------------------------- #
def leg_pnl_rederived(side: str, rest_price: float, result: str) -> float:
    """Net dollars per FILLED contract held to venue settlement. Restated arithmetic:
    payout (1 if our side is the settled side else 0) minus what we paid minus ONE maker
    fee. The losing leg is fully priced, never dropped."""
    payout = 1.0 if ((side == "yes" and result == "yes")
                     or (side == "no" and result == "no")) else 0.0
    return payout - rest_price - _fee(rest_price)


# --------------------------------------------------------------------------- #
# Hand-rolled bootstrap (deliberately NOT random.Random)
# --------------------------------------------------------------------------- #
class LCG:
    """64-bit linear congruential generator (Knuth MMIX constants). Independent stream."""

    __slots__ = ("_s",)

    def __init__(self, seed: int) -> None:
        self._s = (seed ^ 0x5DEECE66D) & ((1 << 64) - 1)

    def next_below(self, n: int) -> int:
        self._s = (6364136223846793005 * self._s + 1442695040888963407) & ((1 << 64) - 1)
        return (self._s >> 17) % n


def block_bootstrap_rederived(unit_values: Dict[str, Sequence[float]], *,
                              n_boot: int = N_BOOT, seed: int = SEED) -> dict:
    """Resample UNIT blocks with replacement (L6), pool, report the pooled-mean 95% CI."""
    units = sorted(unit_values)
    if not units:
        return {"n_units": 0, "n_obs": 0, "mean": None, "ci95": [None, None]}
    n_obs = sum(len(unit_values[u]) for u in units)
    if n_obs == 0:
        return {"n_units": len(units), "n_obs": 0, "mean": None, "ci95": [None, None]}
    mean = sum(sum(unit_values[u]) for u in units) / n_obs
    sums = [sum(unit_values[u]) for u in units]
    lens = [len(unit_values[u]) for u in units]
    rng = LCG(seed)
    k = len(units)
    means: List[float] = []
    for _ in range(n_boot):
        tot = 0.0
        cnt = 0
        for _ in range(k):
            j = rng.next_below(k)
            tot += sums[j]
            cnt += lens[j]
        if cnt:
            means.append(tot / cnt)
    means.sort()
    lo = means[int(0.025 * len(means))]
    hi = means[int(0.975 * len(means))]
    return {"n_units": len(units), "n_obs": n_obs, "mean": mean, "ci95": [lo, hi],
            "n_boot": n_boot, "seed": seed, "rng": "hand-rolled 64-bit LCG"}


def verdict_of(boot: dict, *, min_units: int = MIN_UNITS) -> str:
    ci = boot.get("ci95") or [None, None]
    if (boot.get("n_units") or 0) < min_units:
        return "INADMISSIBLE"
    if ci[0] is not None and ci[0] > 0 and ci[0] >= MIN_TICKS * TICK:
        return "ALIVE"
    return "DEAD"


# --------------------------------------------------------------------------- #
# run
# --------------------------------------------------------------------------- #
def score_candidates(prints: Dict[str, List[tuple]], books: Dict[str, List[tuple]],
                     hold_games: Sequence[str], admitted: Sequence[str],
                     direction: Dict[str, str]) -> List[dict]:
    """Rebuild the holdout candidates with the SAME queue-aware fill loop the outcome-blind
    re-derivation uses, then attach P&L. A candidate whose ticker has no binary direction is
    dropped (not scored as zero — absent is absent, L23/L296)."""
    hold = set(hold_games)
    adm = set(admitted)
    rows: List[dict] = []
    for tk in sorted(prints):
        if _game(tk) not in hold:
            continue
        snaps = books.get(tk) or []
        if len(snaps) < 2:
            continue
        res = direction.get(tk)
        prow = prints[tk]
        for i in range(len(snaps) - 1):
            t0, rec = snaps[i]
            t1 = snaps[i + 1][0]
            if t1 - t0 > MAX_INTERVAL_S:
                continue
            hi_a, lo_b = rec.get("best_yes_ask"), rec.get("best_yes_bid")
            if hi_a is None or lo_b is None:
                continue
            spread = float(hi_a) - float(lo_b)
            window = [p for p in prow if t0 < p[0] <= t1]
            for side in ("yes", "no"):
                bid = rec.get("best_yes_bid") if side == "yes" else rec.get("best_no_bid")
                if bid is None:
                    continue
                bid = float(bid)
                if not (BAND_LO <= bid <= BAND_HI):
                    continue
                if cell(bid, spread) not in adm:
                    continue
                if res is None:            # unsettled/non-binary: not scoreable at all
                    continue
                ladder = rec.get("yes_bids") if side == "yes" else rec.get("no_bids")
                qa = sum(float(l[1]) for l in (ladder or []) if float(l[0]) >= bid - 1e-9)
                cum = 0.0
                filled = False
                for _, yp, cnt, tbs, _tid in window:
                    consumes = (tbs == "bid" and yp >= (1.0 - bid) - 1e-9) if side == "no" \
                        else (tbs == "ask" and yp <= bid + 1e-9)
                    if not consumes:
                        continue
                    cum += cnt
                    if cum > qa + 1e-9:
                        filled = True
                        break
                rows.append({
                    "unit": _game(tk), "ticker": tk, "side": side, "rest_price": bid,
                    "filled": filled,
                    "pnl": leg_pnl_rederived(side, bid, res) if filled else 0.0,
                })
    return rows


def run(*, root: Optional[str] = None) -> dict:
    pop = population_run()
    prints, books = load()
    gdays: Dict[str, set] = {}
    from scripts.q52_s78_population_rederive import _day_of
    for tk, prow in prints.items():
        gdays.setdefault(_game(tk), set()).update(_day_of(p[0]) for p in prow)
    hold_days = set(pop["holdout_days"])
    train_days = set(pop["train_days"])
    hold_games = sorted(g for g, ds in gdays.items()
                        if (ds & hold_days) and not (ds & train_days))

    direction, conflicts = settled_direction(root=root)
    rows = score_candidates(prints, books, hold_games, pop["admitted_cells"], direction)

    def branch(only_filled: bool) -> dict:
        uv: Dict[str, List[float]] = {}
        for r in rows:
            if only_filled and not r["filled"]:
                continue
            uv.setdefault(r["unit"], []).append(float(r["pnl"]))
        b = block_bootstrap_rederived(uv)
        b["branch"] = "conditional_on_fill" if only_filled else "all_candidates"
        b["verdict"] = verdict_of(b)
        return b

    headline = branch(False)
    conditional = branch(True)
    return {
        "schema_version": "q52_s78_scoring_rederive.v1",
        "queue_item": "Q52",
        "strategy": "S78",
        "role": "REDUNDANCY (second implementation) — NOT the two-agent verifier",
        "admitted_cells": pop["admitted_cells"],
        "n_holdout_games": pop["n_holdout_games"],
        "n_scored": len(rows),
        "n_filled": sum(1 for r in rows if r["filled"]),
        "settlement_direction_conflicts": conflicts,
        "n_settlement_direction_conflicts": len(conflicts),
        "headline": headline,
        "conditional_on_fill": conditional,
        "verdict": headline["verdict"],
        "price_source_tags": {"rest_price": "real_bid", "fill_evidence": "broker_truth",
                              "settlement": "broker_truth"},
        "fee_side": "maker",
        "network_calls": 0,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-write", action="store_true",
                    help="do not write reports/q52_s78_scoring_rederive.json")
    args = ap.parse_args(argv)
    rep = run()
    if not args.no_write:
        from core.io import write_report
        write_report("q52_s78_scoring_rederive", rep)
    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        h, c = rep["headline"], rep["conditional_on_fill"]
        print("SCORING-REDERIVE %s scored=%d filled=%d | all_candidates mean=%.10f "
              "ci95=[%.10f, %.10f] n_units=%d | cond_on_fill mean=%.10f ci95=[%.10f, %.10f] "
              "n_units=%d | settlement_conflicts=%d"
              % (rep["verdict"], rep["n_scored"], rep["n_filled"], h["mean"],
                 h["ci95"][0], h["ci95"][1], h["n_units"], c["mean"], c["ci95"][0],
                 c["ci95"][1], c["n_units"], rep["n_settlement_direction_conflicts"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
