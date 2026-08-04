#!/usr/bin/env python3
"""q51_maker_fillsim_rederive.py — INDEPENDENT re-derivation of Q51 milestone 2's verdict.

WHY THIS EXISTS. LOOP-QUEUE.md's two-agent verdict rule requires a second, independent
confirmation before a verdict-class number is recorded. No `verifier` subagent was
dispatchable in the producing run's environment (no `Task` tool in context — the same
constraint recorded on Q49/Q50/Q19 and on Q51 milestone 1 itself). The sanctioned fallback
this repo has used in that situation is a SECOND INDEPENDENT CODE PATH: own reader, own
fee arithmetic, own grouping, own bootstrap, own gates, different seed, reading ONLY the
persisted per-row artifact and never importing the probe it is checking.

That is a REDUNDANCY CHECK, NOT A VERIFIER. It cannot catch a shared misconception (it
would, for instance, not have caught the `taker_book_side` orientation error on its own —
only the tape did). A result confirmed only by this path stays PROVISIONAL and flips
nothing in `kb/strategies/00-index.md`.

Reads `reports/q51_maker_fillsim_rows.jsonl` and re-derives, from the row's own
`rest_price` / `side` / `settle_result` / `filled`:
  * the maker fee, by an independent Decimal round-up (the probe uses `math.ceil`),
  * the per-leg P&L, compared byte-for-byte against the persisted `pnl`,
  * the GAME grouping, by its own string parse,
  * the bootstrap CI, with its own RNG and a DIFFERENT seed,
  * the L41 admissibility and L27 tick gates, hand-derived here.

Run:  python3 scripts/q51_maker_fillsim_rederive.py
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.io import REPO_ROOT  # noqa: E402
from core.pricing import MAKER_FEE_RATE  # noqa: E402  (the rate constant is a repo invariant)
from core.settlement import binary_outcome  # noqa: E402  (L52: never a bare == "yes")

ROWS_PATH = REPO_ROOT / "reports" / "q51_maker_fillsim_rows.jsonl"
SEED = 20260804          # deliberately NOT the probe's seed
N_BOOT = 10000
MIN_UNITS = 10
TICK = 0.01


def maker_fee(price: float) -> float:
    """Kalshi fee, round UP to the cent on rate*p*(1-p) — derived here with Decimal's
    ROUND_CEILING rather than `math.ceil`, so a float-boundary disagreement would show."""
    raw = Decimal(str(MAKER_FEE_RATE)) * Decimal(str(price)) * (Decimal(1) - Decimal(str(price)))
    return float((raw * 100).to_integral_value(rounding=ROUND_CEILING) / 100)


def own_game_key(ticker: str) -> str:
    parts = ticker.split("-")
    return "-".join(parts[:-1]) if len(parts) > 1 else ticker


def own_bootstrap(units: Dict[str, List[float]], n_boot: int, seed: int) -> dict:
    keys = sorted(units)
    if not keys:
        return {"n_units": 0, "mean": None, "ci95": [None, None]}
    flat = [x for k in keys for x in units[k]]
    mean = sum(flat) / len(flat)
    rng = random.Random(seed)
    draws = []
    for _ in range(n_boot):
        tot = 0.0
        cnt = 0
        for _ in keys:
            k = keys[rng.randrange(len(keys))]
            tot += sum(units[k])
            cnt += len(units[k])
        if cnt:
            draws.append(tot / cnt)
    draws.sort()
    return {"n_units": len(keys), "n_obs": len(flat), "mean": mean,
            "ci95": [draws[int(0.025 * len(draws))], draws[int(0.975 * len(draws))]]}


def rederive(rows_path: Path = ROWS_PATH, n_boot: int = N_BOOT, seed: int = SEED) -> dict:
    rows = []
    with open(rows_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    pnl_mismatches = []
    fill_without_print = []
    tag_violations = []
    non_binary_fills = []
    for r in rows:
        p = float(r["rest_price"])
        if not r["filled"]:
            expect = 0.0
            if r.get("fill_trade_id"):
                fill_without_print.append(r)
        else:
            if not r.get("fill_trade_id") or r.get("fill_price_source_tag") != "broker_truth":
                fill_without_print.append(r)
            # L52: a settled Kalshi market's result is not always binary. Classify through
            # core.settlement rather than comparing to a bare "yes"/"no" literal; a
            # non-binary value yields None and is recorded as an unscoreable row, never
            # silently booked as the losing side.
            outcome = binary_outcome(r["settle_result"])
            if outcome is None:
                non_binary_fills.append(r)
                continue
            won = (outcome == 1) if r["side"] == "yes_bid" else (outcome == 0)
            expect = (1.0 if won else 0.0) - p - maker_fee(p)
        if abs(expect - float(r["pnl"])) > 1e-12:
            pnl_mismatches.append({"row": r, "expected": expect})
        if r.get("price_source_tag") != "real_bid":
            tag_violations.append(r)

    def cut(sel) -> dict:
        sub = [r for r in rows if sel(r)]
        units: Dict[str, List[float]] = {}
        for r in sub:
            units.setdefault(own_game_key(r["ticker"]), []).append(float(r["pnl"]))
        boot = own_bootstrap(units, n_boot, seed)
        unit_means = {k: sum(v) / len(v) for k, v in units.items() if v}
        pooled = boot["mean"]
        opposing = 0
        if pooled is not None and pooled > 0:
            opposing = sum(1 for m in unit_means.values() if m < 0)
        elif pooled is not None and pooled < 0:
            opposing = sum(1 for m in unit_means.values() if m > 0)
        lo = boot["ci95"][0]
        return {
            "n_legs": len(sub),
            "n_filled": sum(1 for r in sub if r["filled"]),
            "fill_rate": (sum(1 for r in sub if r["filled"]) / len(sub)) if sub else None,
            "n_units": boot["n_units"],
            "n_opposing_units": opposing,
            "mean": boot["mean"],
            "ci95": boot["ci95"],
            "admissible": bool(boot["n_units"] >= MIN_UNITS and opposing >= 1),
            "clears_tick": bool(lo is not None and lo >= TICK),
        }

    covered = sum(1 for r in rows if r["interval_covered"])
    return {
        "rows": len(rows),
        "pnl_mismatches": len(pnl_mismatches),
        "untraced_fills": len(fill_without_print),
        "non_binary_result_fills": len(non_binary_fills),
        "price_tag_violations": len(tag_violations),
        "seed": seed,
        "all_intervals": cut(lambda r: True),
        "covered_intervals": cut(lambda r: r["interval_covered"]),
        "row_level_interval_coverage": covered / len(rows) if rows else None,
        "examples_of_mismatch": pnl_mismatches[:3],
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rows", default=str(ROWS_PATH))
    ap.add_argument("--n-boot", type=int, default=N_BOOT)
    ap.add_argument("--seed", type=int, default=SEED)
    a = ap.parse_args(argv)
    out = rederive(Path(a.rows), a.n_boot, a.seed)
    print(json.dumps(out, indent=1, sort_keys=True))
    ok = (out["pnl_mismatches"] == 0 and out["untraced_fills"] == 0
          and out["price_tag_violations"] == 0 and out["non_binary_result_fills"] == 0)
    print(f"[q51:rederive] independent P&L agreement: {'CLEAN' if ok else 'MISMATCH'}")
    print("[q51:rederive] this is a redundancy check, not a verifier — the verdict stays "
          "PROVISIONAL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
