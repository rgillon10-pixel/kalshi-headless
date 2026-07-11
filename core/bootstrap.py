"""Shared block-bootstrap + verdict-gate helpers — compounding L6/L27/L28 into code.

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
only takes an already-grouped-by-unit mapping, it never guesses the grouping key).
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
