#!/usr/bin/env python3
"""q31_cross_venue_arb_probe.py — Q31: Kalshi<->Polymarket cross-venue two-legged arb.

LOOP-QUEUE.md Q31 (regime-change follow-up). READ-ONLY over committed tape; no network, no
writes. Kalshi and Polymarket quote nearly the same price for matched events (S9 first cut,
2026-07-04: mean gap +0.20c, range -3c/+3c across 48 WC-round markets). Now that Ryan can
trade BOTH venues, a genuine cross-venue arb is possible: buy YES on the cheaper venue + buy
NO (same event) on the dearer venue -- exactly one leg pays $1, so if the combined cost net
of BOTH venues' fees is < $1 it is locked-in profit regardless of outcome.

DATA-COVERAGE LIMITATION (stated up front, per CLAUDE.md trust defaults). Our Polymarket tape
(`collection/polymarket_pairs.py`) captures ONLY the "Yes" outcome token's best_ask/best_bid
off the international CLOB -- there is NO captured Polymarket NO-token ask anywhere in the tape.
So the two-legged arb is fully computable with real resting asks on BOTH legs in exactly ONE
direction: buy Polymarket YES (`polymarket.best_ask`) + buy Kalshi NO (`kalshi.no_ask`). The
mirror direction (Kalshi YES + Polymarket NO) is NOT testable here -- deriving a Polymarket NO
ask as `1 - best_bid` would be a mid/bid-derived synthetic price, exactly what Q31 gate (3)
forbids. We report only the fillable direction as an arb; the raw price gap (both directions) is
reported descriptively, clearly labelled NOT-a-fillable-test.

PROVENANCE (Q31 gate 2). The Polymarket leg is `real_ask` on the INTERNATIONAL book
(`clob.polymarket.com`), NOT a Polymarket-US (QCX/QCEX) fill. Prices Ryan can actually realize
on Polymarket US may differ in level/liquidity. No number here is claimed as Ryan's fill price.

RESOLUTION-EQUIVALENCE (Q31 gate 1). Two `real_ask`-on-both-legs families are present:
  - WC-round ("Will <team> reach <round>?") -- same tournament result, same round definition,
    same timing on both venues -> criteria-equivalent.
  - Fed-decision ("Will the Fed hike/cut Xbps at the <month> meeting?") -- same FOMC
    announcement, same source, same timing -> criteria-equivalent.
Both carry a RESIDUAL settlement-source risk: Polymarket international resolves via the UMA
optimistic oracle, Kalshi centrally by rulebook -- "same question" CAN resolve differently. That
is a non-price capital risk carried on every number, not a criteria non-equivalence, so these
pairs are INCLUDED and the risk is flagged. The CPI family (`polymarket_cpi_pairs`) is EXCLUDED
outright: its Kalshi leg is a `synthetic` differenced probability, failing the both-legs-real_ask
gate -- it is not read by this probe at all.

FEES (Q31 gate: net of BOTH fee models). Kalshi NO leg via `core.pricing.fee_per_contract`
(TAKER_FEE_RATE 0.07); Polymarket YES leg via `core.pricing.polymarket_fee_per_contract`
(POLYMARKET_US_TAKER_RATE 0.05). No fee arithmetic is hand-rolled here.

CAPITAL/SETTLEMENT FRICTION (Q31 gate 4) is real and NOT modelled away: two separate funding
pools (Kalshi USD, Polymarket USDC/fiat), USDC bridging or fiat rails ($5-30), and no instant
cross-venue rebalancing. A "fillable arb" that needs both legs funded simultaneously carries
that friction on top of anything measured here.

METHOD. Value per observation = net two-legged edge (dollars) = 1 - (pm_yes + k_no) - both fees.
Bootstrap unit = the matched PAIR (family, kalshi ticker), block-bootstrapped via
`core.bootstrap.block_bootstrap` (L6: snapshots of one market are correlated draws, not
independent rows -- cluster them). Any positivity is routed through
`core.bootstrap.bootstrap_verdict_admissible` + `clears_tick_magnitude` before it can count.
Because this is repeated same-entity snapshots (hour-over-hour books), a frozen consecutive pair
(both legs unchanged) is a no-fill, not free income (L32): we compute a per-observation frozen
flag and bootstrap BOTH the frozen-inclusive and movement-conditioned cuts, and measure whether a
visible dislocation PERSISTS to the next capture under movement.

Run:
    python scripts/q31_cross_venue_arb_probe.py
    python scripts/q31_cross_venue_arb_probe.py --pm-rate 0.0   # fee-free-PM sensitivity
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.io import REPO_ROOT  # noqa: E402
from core.pricing import (  # noqa: E402
    POLYMARKET_US_TAKER_RATE,
    TAKER_FEE_RATE,
    fee_per_contract,
    polymarket_fee_per_contract,
)
from core.bootstrap import (  # noqa: E402
    block_bootstrap,
    bootstrap_verdict_admissible,
    bracket_by_movement,
    clears_tick_magnitude,
)

# Both tape families carry BOTH legs as real_ask; CPI is deliberately excluded (synthetic leg).
WC_GLOB = str(REPO_ROOT / "tape" / "polymarket_pairs" / "dt=*.jsonl")
FED_GLOB = str(REPO_ROOT / "tape" / "polymarket_macro_pairs" / "dt=*.jsonl")
RESOLUTION_EQUIVALENT_SCHEMAS = {"polymarket_pairs.v1", "polymarket_macro_pairs.v1"}


def two_legged_arb_edge(polymarket_yes_price: float, kalshi_no_price: float,
                        pm_rate: float = POLYMARKET_US_TAKER_RATE,
                        kalshi_rate: float = TAKER_FEE_RATE) -> Dict[str, float]:
    """Dollar edge of locking $1 via buy-Polymarket-YES + buy-Kalshi-NO on the SAME event.

    Exactly one of the two legs pays $1 at resolution (event YES -> the Polymarket YES leg;
    event NO -> the Kalshi NO leg), so the guaranteed-$1 payout costs the sum of the two real
    asks plus both venues' taker fees. Positive `net_edge` == net cost < $1 == a fillable arb.
    Both fees come from `core.pricing`; nothing is hand-rolled. Returns gross (pre-fee) and net
    edges plus the two per-contract fees so a caller can persist the decomposition."""
    gross_cost = float(polymarket_yes_price) + float(kalshi_no_price)
    pm_fee = polymarket_fee_per_contract(polymarket_yes_price, pm_rate)
    kalshi_fee = fee_per_contract(kalshi_no_price, kalshi_rate)
    net_cost = gross_cost + pm_fee + kalshi_fee
    return {
        "gross_cost": gross_cost,
        "gross_edge": 1.0 - gross_cost,
        "pm_fee": pm_fee,
        "kalshi_fee": kalshi_fee,
        "net_cost": net_cost,
        "net_edge": 1.0 - net_cost,
    }


def _iter_records(tape_glob: str, family: str):
    for path in sorted(glob.glob(tape_glob)):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if rec.get("schema_version") not in RESOLUTION_EQUIVALENT_SCHEMAS:
                    continue
                rec["_family"] = family
                yield rec


def load_observations(wc_glob: str = WC_GLOB, fed_glob: str = FED_GLOB,
                      pm_rate: float = POLYMARKET_US_TAKER_RATE) -> List[Dict]:
    """Every resolution-equivalent snapshot with BOTH real asks present, priced.

    Skips a record with a missing/failed leg (`book_fetch_ok` False, or either ask None) --
    recorded in the summary as `n_skipped`, never silently treated as a $0 edge. Each returned
    obs carries its pair key, capture timestamp, the two raw asks, and the net/gross edge."""
    obs: List[Dict] = []
    n_skipped = 0
    for tape_glob, family in ((wc_glob, "wc_round"), (fed_glob, "fed_decision")):
        for rec in _iter_records(tape_glob, family):
            k = rec.get("kalshi") or {}
            p = rec.get("polymarket") or {}
            k_no = k.get("no_ask")
            pm_yes = p.get("best_ask")
            if k_no is None or pm_yes is None or not p.get("book_fetch_ok"):
                n_skipped += 1
                continue
            edge = two_legged_arb_edge(pm_yes, k_no, pm_rate=pm_rate)
            obs.append({
                "family": family,
                "ticker": k.get("ticker"),
                "pair_key": f'{family}:{k.get("ticker")}',
                "captured_at": rec.get("captured_at"),
                "pm_yes_ask": float(pm_yes),
                "k_no_ask": float(k_no),
                "pm_best_bid": p.get("best_bid"),
                "price_gap_yes_ask": rec.get("price_gap_yes_ask"),
                **edge,
            })
    load_observations._n_skipped = n_skipped  # type: ignore[attr-defined]
    return obs


def net_edges_by_pair(obs: List[Dict]) -> Dict[str, List[float]]:
    """`{pair_key: [net_edge, ...]}` -- the block-bootstrap clustering (L6: one market's
    repeated snapshots are one correlated cluster, never independent rows)."""
    out: Dict[str, List[float]] = defaultdict(list)
    for o in obs:
        out[o["pair_key"]].append(o["net_edge"])
    return dict(out)


def frozen_flags_and_values(obs: List[Dict]) -> Tuple[List[bool], List[float], Dict[str, List[float]]]:
    """Per-observation frozen flag for the L32 dual cut, plus the movement-conditioned by-pair
    grouping. Within each pair (sorted by capture time) an observation is FROZEN if BOTH legs
    (Kalshi NO ask and Polymarket YES ask) are unchanged from the previous capture of that pair;
    the first capture of a pair has no prior movement to observe and is counted frozen (the
    max-generous / conservative choice for the movement cut -- it can only shrink that cut).

    Returns (frozen_flags, net_values) aligned in pair-then-time order (for `bracket_by_movement`)
    and `{pair_key: [net_edge where NOT frozen]}` for a movement-conditioned by-pair bootstrap."""
    by_pair: Dict[str, List[Dict]] = defaultdict(list)
    for o in obs:
        by_pair[o["pair_key"]].append(o)

    frozen_flags: List[bool] = []
    net_values: List[float] = []
    moved_by_pair: Dict[str, List[float]] = defaultdict(list)
    for pair_key, rows in by_pair.items():
        rows.sort(key=lambda r: r["captured_at"] or "")
        prev: Optional[Dict] = None
        for r in rows:
            if prev is None:
                frozen = True
            else:
                frozen = (r["k_no_ask"] == prev["k_no_ask"]
                          and r["pm_yes_ask"] == prev["pm_yes_ask"])
            frozen_flags.append(frozen)
            net_values.append(r["net_edge"])
            if not frozen:
                moved_by_pair[pair_key].append(r["net_edge"])
            prev = r
    return frozen_flags, net_values, dict(moved_by_pair)


def persistence_stats(obs: List[Dict]) -> Dict[str, float]:
    """Does a VISIBLE dislocation (net_edge > 0) survive to the next capture of the same pair --
    i.e. is it fillable in time, not just a one-snapshot mirage? Split by whether the book
    actually MOVED between the two captures: a frozen consecutive pair that stays net>0 is the
    same unfilled quote sitting there (L32 no-fill), not a re-offered arb."""
    by_pair: Dict[str, List[Dict]] = defaultdict(list)
    for o in obs:
        by_pair[o["pair_key"]].append(o)

    n_pairs = 0
    n_frozen = 0
    pos_all = pos_all_survive = 0
    pos_moved = pos_moved_survive = 0
    for rows in by_pair.values():
        rows.sort(key=lambda r: r["captured_at"] or "")
        for a, b in zip(rows, rows[1:]):
            n_pairs += 1
            moved = not (a["k_no_ask"] == b["k_no_ask"] and a["pm_yes_ask"] == b["pm_yes_ask"])
            if not moved:
                n_frozen += 1
            if a["net_edge"] > 0:
                pos_all += 1
                if b["net_edge"] > 0:
                    pos_all_survive += 1
                if moved:
                    pos_moved += 1
                    if b["net_edge"] > 0:
                        pos_moved_survive += 1
    return {
        "n_consecutive_pairs": n_pairs,
        "n_frozen_pairs": n_frozen,
        "frac_frozen_pairs": (n_frozen / n_pairs) if n_pairs else 0.0,
        "n_pos_with_next": pos_all,
        "frac_pos_persist_inclusive": (pos_all_survive / pos_all) if pos_all else 0.0,
        "n_pos_moved_with_next": pos_moved,
        "frac_pos_persist_moved": (pos_moved_survive / pos_moved) if pos_moved else 0.0,
    }


def _fmt_boot(b: dict) -> str:
    lo, hi = b["ci95"]
    if b["mean"] is None:
        return f"n_units={b['n_units']} n_obs={b['n_obs']} (empty)"
    return (f"mean={b['mean']:+.5f}  95% CI [{lo:+.5f}, {hi:+.5f}]  "
            f"n_units={b['n_units']} n_obs={b['n_obs']}")


def run(wc_glob: str = WC_GLOB, fed_glob: str = FED_GLOB,
        pm_rate: float = POLYMARKET_US_TAKER_RATE, n_boot: int = 10000) -> Dict:
    """Full read-only verdict pass. Returns a dict summary (also printed)."""
    obs = load_observations(wc_glob, fed_glob, pm_rate=pm_rate)
    n_skipped = getattr(load_observations, "_n_skipped", 0)
    n_obs = len(obs)

    by_pair = net_edges_by_pair(obs)
    n_pairs = len(by_pair)
    all_net = [o["net_edge"] for o in obs]
    all_gross = [o["gross_edge"] for o in obs]
    n_net_pos = sum(1 for x in all_net if x > 0)
    n_gross_pos = sum(1 for x in all_gross if x > 0)
    pooled_mean = (sum(all_net) / n_obs) if n_obs else float("nan")

    # per-pair: any pair whose MEAN net edge is > 0 is a candidate stable arb
    pair_means = {k: sum(v) / len(v) for k, v in by_pair.items()}
    n_pairs_pos = sum(1 for m in pair_means.values() if m > 0)

    # primary by-pair block bootstrap on net edge (L6 clustering)
    boot = block_bootstrap(by_pair, n_boot=n_boot)
    admis = bootstrap_verdict_admissible(by_pair, min_units=10)
    clears = clears_tick_magnitude(boot["ci95"])

    # L32 dual cut: frozen-inclusive vs movement-conditioned, both bootstrapped by pair
    frozen_flags, net_values, moved_by_pair = frozen_flags_and_values(obs)
    dual = bracket_by_movement(frozen_flags, net_values)
    boot_incl = block_bootstrap(by_pair, n_boot=n_boot)          # frozen-inclusive == full pop
    boot_moved = block_bootstrap(moved_by_pair, n_boot=n_boot)   # movement-conditioned

    persist = persistence_stats(obs)

    # per-family descriptive
    fam_stats: Dict[str, Dict] = {}
    for fam in ("wc_round", "fed_decision"):
        fam_obs = [o for o in obs if o["family"] == fam]
        if not fam_obs:
            continue
        fam_net = [o["net_edge"] for o in fam_obs]
        fam_pairs = {k for k in by_pair if k.startswith(fam + ":")}
        fam_stats[fam] = {
            "n_obs": len(fam_obs),
            "n_pairs": len(fam_pairs),
            "mean_net": sum(fam_net) / len(fam_net),
            "frac_net_pos": sum(1 for x in fam_net if x > 0) / len(fam_net),
        }

    verdict_positive = bool(clears and admis["admissible"] and boot["ci95"][0] is not None
                            and boot["ci95"][0] > 0)

    summary = {
        "pm_rate": pm_rate,
        "kalshi_rate": TAKER_FEE_RATE,
        "n_obs": n_obs,
        "n_skipped": n_skipped,
        "n_pairs": n_pairs,
        "n_pairs_positive_mean": n_pairs_pos,
        "n_net_pos_obs": n_net_pos,
        "frac_net_pos_obs": (n_net_pos / n_obs) if n_obs else 0.0,
        "n_gross_pos_obs": n_gross_pos,
        "frac_gross_pos_obs": (n_gross_pos / n_obs) if n_obs else 0.0,
        "pooled_mean_net_edge": pooled_mean,
        "net_edge_min": min(all_net) if all_net else None,
        "net_edge_max": max(all_net) if all_net else None,
        "boot_primary": boot,
        "admissible": admis,
        "clears_tick_magnitude": clears,
        "frac_frozen_obs": dual["frac_frozen"],
        "boot_frozen_inclusive": boot_incl,
        "boot_movement_conditioned": boot_moved,
        "persistence": persist,
        "by_family": fam_stats,
        "verdict_positive": verdict_positive,
        "price_source_tag": "real_ask",  # both legs; Polymarket = INTERNATIONAL book (provenance)
    }

    _print_report(summary, n_boot)
    return summary


def _print_report(s: Dict, n_boot: int) -> None:
    print("=" * 82)
    print("Q31 CROSS-VENUE TWO-LEGGED ARB  (buy Polymarket YES + buy Kalshi NO, net of BOTH fees)")
    print("=" * 82)
    print("Direction: ONLY testable one (no captured Polymarket NO ask). Polymarket leg = "
          "real_ask\n           on the INTERNATIONAL book, NOT a Polymarket-US fill (provenance).")
    print(f"Fees: Kalshi taker {s['kalshi_rate']}  |  Polymarket taker {s['pm_rate']} "
          f"(0.0 = intl fee-free sensitivity)")
    print(f"\nObservations priced: {s['n_obs']}   skipped (missing/failed leg): {s['n_skipped']}   "
          f"pairs (clusters): {s['n_pairs']}")
    for fam, fs in s["by_family"].items():
        print(f"  {fam:13} n_obs={fs['n_obs']:5} pairs={fs['n_pairs']:3} "
              f"mean_net={fs['mean_net']:+.5f} frac_net>0={fs['frac_net_pos']:.3f}")
    print(f"\nfillable-arb frequency (net cost < $1): {s['n_net_pos_obs']}/{s['n_obs']} = "
          f"{s['frac_net_pos_obs']:.3f}")
    print(f"gross (pre-fee) cost < $1:               {s['n_gross_pos_obs']}/{s['n_obs']} = "
          f"{s['frac_gross_pos_obs']:.3f}")
    print(f"pairs with a POSITIVE mean net edge:     {s['n_pairs_positive_mean']}/{s['n_pairs']}")
    print(f"pooled mean net edge = {s['pooled_mean_net_edge']:+.5f}  "
          f"(range [{s['net_edge_min']:+.4f}, {s['net_edge_max']:+.4f}])")
    print(f"\nPRIMARY block-bootstrap by pair (n_boot={n_boot}): {_fmt_boot(s['boot_primary'])}")
    print(f"  admissible (>=10 units, >=1 opposing cluster): {s['admissible']['admissible']} "
          f"{s['admissible']['reasons']}")
    print(f"  clears 1-tick magnitude gate: {s['clears_tick_magnitude']}")
    print(f"\nL32 dual cut  frozen fraction={s['frac_frozen_obs']:.3f}")
    print(f"  frozen-inclusive : {_fmt_boot(s['boot_frozen_inclusive'])}")
    print(f"  movement-conditioned: {_fmt_boot(s['boot_movement_conditioned'])}")
    p = s["persistence"]
    print(f"\nPersistence of visible net>0 to next capture:")
    print(f"  frozen books = {p['frac_frozen_pairs']:.1%} of {p['n_consecutive_pairs']} consecutive pairs")
    print(f"  inclusive: {p['frac_pos_persist_inclusive']:.1%} survive (n={p['n_pos_with_next']})")
    print(f"  MOVED only: {p['frac_pos_persist_moved']:.1%} survive (n={p['n_pos_moved_with_next']}) "
          f"<- the fillable-in-time cut")
    print("\n" + "-" * 82)
    if s["verdict_positive"]:
        print("VERDICT: candidate POSITIVE cross-venue edge -- CI>0, admissible, clears tick gate.")
        print("         (Carry provenance + resolution-source + capital-friction caveats; two-agent rule.)")
    else:
        print("VERDICT: DEAD -- no fillable cross-venue arb at real two-legged asks net of both fees.")
    print("-" * 82)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Q31 cross-venue two-legged arb probe (read-only)")
    ap.add_argument("--pm-rate", type=float, default=POLYMARKET_US_TAKER_RATE,
                    help="Polymarket taker fee rate (default = US 0.05; 0.0 = intl fee-free)")
    ap.add_argument("--n-boot", type=int, default=10000)
    ap.add_argument("--wc-glob", default=WC_GLOB)
    ap.add_argument("--fed-glob", default=FED_GLOB)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)
    summary = run(args.wc_glob, args.fed_glob, pm_rate=args.pm_rate, n_boot=args.n_boot)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
