"""Shared block-bootstrap + verdict-gate helpers — compounding L6/L27/L28/L32/L41 into code.

Every probe so far (`s6_maker_firstcut.py`, `s10_reachability_probe.py`,
`s7c_sports_clv_bootstrap.py`, ...) has hand-rolled its own block bootstrap. That
duplication is exactly how a fixable methodology bug (L27: a sign-only CI check lets a
floored-at-$1.00 population masquerade as "alive"; L28: building a whole decay pipeline
before checking the floor is even reachable) recurs per-script instead of getting fixed
once. This module is the reusable home kb/lessons/00-lessons.md L27/L28 asked for
("likely terminal as protocol... once a probe-precedent encodes it") — new probes should
import from here rather than re-deriving the bootstrap loop and the magnitude gate.

Does NOT replace per-probe judgment calls (the bootstrap UNIT — hour, ticker, game — is
always a modeling choice specific to what's correlated in that dataset, per L6; this module
only takes an already-grouped-by-unit mapping, it never guesses the grouping key). The same
discipline applies to `bracket_by_movement` (L32): what counts as "frozen" for a given
snapshot pair (BBO unchanged? mid unchanged? something else?) is a per-probe judgment call
— this module only takes the caller's already-computed per-observation frozen flags, it
never inspects raw book fields itself.
"""
from __future__ import annotations

import random
from typing import Dict, List, Sequence


def block_bootstrap(unit_values: Dict[str, Sequence[float]], *, n_boot: int = 10000,
                     seed: int = 42) -> dict:
    """Resample UNIT blocks with replacement (L6: the unit is whatever the caller has
    already grouped by — hour, ticker, game — never the raw observation), pool each
    resample's values, and report the pooled-mean distribution's 95% CI.

    `unit_values` maps a unit key to that unit's list of per-trade/per-observation values
    (e.g. realized P&L). Empty input returns an honest all-None report rather than raising.
    """
    units = list(unit_values.keys())
    if not units:
        return {"n_units": 0, "n_obs": 0, "mean": None, "ci95": [None, None],
                "n_boot": n_boot, "seed": seed}

    total = sum(sum(v) for v in unit_values.values())
    count = sum(len(v) for v in unit_values.values())
    if count == 0:
        return {"n_units": len(units), "n_obs": 0, "mean": None, "ci95": [None, None],
                "n_boot": n_boot, "seed": seed}
    grand_mean = total / count

    rng = random.Random(seed)
    means: List[float] = []
    for _ in range(n_boot):
        tot = 0.0
        cnt = 0
        for _ in units:
            v = unit_values[rng.choice(units)]
            tot += sum(v)
            cnt += len(v)
        # a resample can (rarely) draw only empty units for every slot; skip rather than
        # divide by zero, so one degenerate resample can't crash the whole bootstrap.
        if cnt == 0:
            continue
        means.append(tot / cnt)
    means.sort()
    if not means:
        return {"n_units": len(units), "n_obs": count, "mean": grand_mean,
                "ci95": [None, None], "n_boot": n_boot, "seed": seed}
    lo = means[int(0.025 * len(means))]
    hi = means[int(0.975 * len(means))]
    return {
        "n_units": len(units), "n_obs": count, "mean": grand_mean,
        "ci95": [lo, hi], "n_boot": n_boot, "seed": seed,
    }


def bootstrap_verdict_admissible(unit_values: Dict[str, Sequence[float]], *,
                                  min_units: int = 10) -> dict:
    """The L41 degeneracy gate: a cluster bootstrap whose units ALL resolved the same
    direction cannot produce a single resample on the other side of zero, so its
    one-sided p is mechanically 0 and its CI "significance" carries no evidentiary
    weight — S20's sole FDR "survivor" (8/8 longshot-sell clusters won, p=0.0) and
    S19's 2-event-hour filled population (CI [+0.285,+0.425], a resampling artifact)
    are the exhibits. A directional edge claim is admissible only if the resample
    population could have disagreed with it.

    Gate (both required):
      1. `n_units >= min_units` (units with at least one observation) — the S19
         data-adequacy floor, now checked BEFORE a CI is quoted, not after.
      2. At least one unit's mean sits strictly on the OPPOSITE side of zero from the
         pooled mean (≥1 losing cluster for a positive claim, ≥1 winning cluster for a
         negative one). A pooled mean of exactly 0 makes no directional claim; it
         requires ≥1 strictly-positive AND ≥1 strictly-negative unit to count as a
         genuinely mixed population rather than an all-zeros artifact.

    Returns a dict (not a bare bool) so verdict reports can record WHY a CI was
    inadmissible: `{"admissible", "n_units", "n_opposing_units", "reasons"}` where
    `reasons` is a list drawn from {"below_min_units", "no_opposing_unit", "empty"}
    (empty list when admissible). Sibling to `clears_tick_magnitude` (L27) in the
    verdict rule: a CI that fails EITHER gate is not-a-verdict by construction.
    Empty input is inadmissible, never a crash.
    """
    unit_means = {k: sum(v) / len(v) for k, v in unit_values.items() if len(v) > 0}
    n_units = len(unit_means)
    count = sum(len(v) for v in unit_values.values())
    if count == 0 or n_units == 0:
        return {"admissible": False, "n_units": n_units, "n_opposing_units": 0,
                "reasons": ["empty"]}
    pooled = sum(sum(v) for v in unit_values.values()) / count
    if pooled > 0:
        n_opposing = sum(1 for m in unit_means.values() if m < 0)
    elif pooled < 0:
        n_opposing = sum(1 for m in unit_means.values() if m > 0)
    else:
        n_opposing = min(sum(1 for m in unit_means.values() if m > 0),
                         sum(1 for m in unit_means.values() if m < 0))
    reasons = []
    if n_units < min_units:
        reasons.append("below_min_units")
    if n_opposing < 1:
        reasons.append("no_opposing_unit")
    return {"admissible": not reasons, "n_units": n_units,
            "n_opposing_units": n_opposing, "reasons": reasons}


def clears_tick_magnitude(ci95: Sequence, *, tick: float = 0.01, min_ticks: float = 1.0
                           ) -> bool:
    """The L27 economic-significance gate: a CI whose lower bound is strictly > 0 is
    necessary but NOT sufficient — `fee_per_contract($1.00) == 0` means a bootstrap
    dominated by $1.00-priced legs can float a CI lower bound of +0.000000, three orders
    of magnitude below a fillable 1-cent tick (S10's own near-miss). Require the lower
    bound to clear `min_ticks * tick`, not just zero.

    False on a [None, None] CI (empty-input bootstrap) rather than raising.
    """
    lo = ci95[0] if ci95 else None
    if lo is None:
        return False
    return lo >= min_ticks * tick


def floor_pinned_fraction(values: Sequence[float], floor: float, *, tol: float = 1e-9
                           ) -> float:
    """The L28 precheck: before building a decay/CI pipeline to test whether a price
    moves away from a boundary, check what fraction of the EARLIEST observations are
    already pinned at that boundary — S10 built a full early/late decay join only to
    find 99.98% of far brackets were already floor-pinned pre-close, i.e. there was no
    decay window beneath the floor to measure. Cheap enough to run before the expensive
    pipeline, not after.

    Returns 0.0 on an empty sequence rather than raising (nothing to be pinned).
    """
    if not values:
        return 0.0
    pinned = sum(1 for v in values if abs(v - floor) <= tol)
    return pinned / len(values)


def bracket_by_movement(frozen_flags: Sequence[bool], values: Sequence[float]) -> dict:
    """The L32 dual-cut bracket: a frozen consecutive snapshot pair (no observed price
    movement) is a no-fill, not free income — booking its nominal edge as riskless profit
    is the exact error that inflated S6's naive maker-spread population into a phantom
    +$0.069 "alive" read (the real populations, both cuts, came back strictly negative).

    Report BOTH populations so a verdict is honest under either fill assumption:
      - frozen_inclusive: every value as-is (max-generous — counts unrealized spread on
        frozen pairs as if it had been captured)
      - movement_conditioned: only values where the matching flag is False (the only
        population where a fill plausibly occurred and adverse selection is measurable)

    `frozen_flags[i]` must correspond to `values[i]` (the caller has already decided what
    "frozen" means for its own probe — this function does not inspect book fields itself).
    Raises on a length mismatch rather than silently misaligning the two sequences.
    """
    if len(frozen_flags) != len(values):
        raise ValueError(
            f"frozen_flags and values must be the same length "
            f"(got {len(frozen_flags)} vs {len(values)})"
        )
    n = len(values)
    frac_frozen = sum(1 for f in frozen_flags if f) / n if n else 0.0
    movement_conditioned = [v for f, v in zip(frozen_flags, values) if not f]
    return {
        "n": n,
        "frac_frozen": frac_frozen,
        "frozen_inclusive": list(values),
        "movement_conditioned": movement_conditioned,
    }
