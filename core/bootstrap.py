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


def collapse_duration_gated_runs(is_hit: Sequence[bool], seconds: Sequence[float],
                                  depths: Sequence[float] = None, *,
                                  min_duration_seconds: float, min_depth: float = 0.0
                                  ) -> List[dict]:
    """The L76 duration gate: collapse maximal consecutive runs of `is_hit` snapshots and
    report BOTH snapshot count and wall-clock seconds — never gate executability on
    snapshot count alone. A sub-second repricing burst can rack up >= 2 consecutive hits
    (satisfying a naive `MIN_SNAPS`-style count gate) while lasting < 1s of real time
    (W-D's ladder-coherence probe: every one of its 17 count-gated runs persisted <= 1.0s
    wall-clock). `seconds[i]` is the elapsed time attributed to snapshot `i` (e.g. time
    until the next snapshot, or 0.0 for the last one in a series — the caller's own
    convention); a run's total seconds is the sum over its member snapshots.

    `is_hit`/`seconds`/`depths` (if given) must be the same length and index-aligned
    (caller's own per-snapshot condition and binding depth — this function does not
    inspect price/depth fields itself, same discipline as `bracket_by_movement`).

    Returns one dict per maximal run: `start_index`/`end_index` (inclusive, into the input
    sequences), `n_snaps`, `seconds` (summed wall-clock), `min_depth` (None if `depths` not
    given), and `executable` — True iff `seconds >= min_duration_seconds` AND (no `depths`
    given, or the run's `min_depth >= min_depth`). Never True on snapshot count alone.
    """
    if len(is_hit) != len(seconds) or (depths is not None and len(depths) != len(is_hit)):
        raise ValueError(
            f"is_hit ({len(is_hit)}), seconds ({len(seconds)})"
            + (f", depths ({len(depths)})" if depths is not None else "")
            + " must be the same length"
        )
    runs: List[dict] = []
    cur = None
    for i, hit in enumerate(is_hit):
        if hit:
            if cur is None:
                cur = {"start_index": i, "end_index": i, "n_snaps": 0, "seconds": 0.0,
                       "min_depth": None if depths is None else float("inf")}
            cur["end_index"] = i
            cur["n_snaps"] += 1
            cur["seconds"] += seconds[i]
            if depths is not None:
                cur["min_depth"] = min(cur["min_depth"], depths[i])
        else:
            if cur is not None:
                runs.append(cur)
                cur = None
    if cur is not None:
        runs.append(cur)
    for run in runs:
        run["executable"] = (
            run["seconds"] >= min_duration_seconds
            and (depths is None or run["min_depth"] >= min_depth)
        )
    return runs


def decompose_edge_by_leg_volume(leg_pnls: Sequence[float], leg_volumes: Sequence[float], *,
                                  thin_volume_threshold: float = 100) -> dict:
    """The L39 decomposition: when a net edge is a SMALL NET OF TWO LARGE LEGS (income
    premium collected vs. a near-$1 payout on the rare loss), a candlestick/volume fill
    proxy that credits the income leg on `high >= ask AND volume > 0` alone is biased
    UPWARD — a bar only proves the price printed, not that a resting offer ahead of the
    whole queue would have filled. Before calling such an edge fillable, report what
    FRACTION of it is carried by the thinnest income legs: S14's own +$0.0925 mean was
    78% (+$0.072 of +$0.093) attributable to legs with < 100 contracts of proxy volume —
    the fat nominal overround never underwrote the edge, it was almost entirely thin
    near-money pass-through.

    `leg_pnls[i]` is the per-leg net contribution to the pooled edge and `leg_volumes[i]`
    its matching proxy volume (the caller's own fill-proxy volume field — this function
    does not read tape fields itself, same discipline as `bracket_by_movement`). Raises on
    a length mismatch rather than silently misaligning the two sequences.

    Returns `total` (sum of all leg pnls), `thin_total` (sum of legs with volume below
    `thin_volume_threshold`), `thin_fraction` (thin_total / total, None if total is 0 —
    an honest undefined ratio rather than a divide-by-zero or a fabricated 0.0), `n_legs`,
    and `n_thin_legs`.
    """
    if len(leg_pnls) != len(leg_volumes):
        raise ValueError(
            f"leg_pnls and leg_volumes must be the same length "
            f"(got {len(leg_pnls)} vs {len(leg_volumes)})"
        )
    total = sum(leg_pnls)
    thin_pnls = [p for p, v in zip(leg_pnls, leg_volumes) if v < thin_volume_threshold]
    thin_total = sum(thin_pnls)
    return {
        "total": total,
        "thin_total": thin_total,
        "thin_fraction": (thin_total / total) if total != 0 else None,
        "threshold": thin_volume_threshold,
        "n_legs": len(leg_pnls),
        "n_thin_legs": len(thin_pnls),
    }


def _sign(x: float) -> int:
    return 0 if x == 0 else (1 if x > 0 else -1)


def catastrophic_leg_drop_stress_check(retained_pnls: Sequence[float], n_dropped: int, *,
                                        generous_replacement_value: float = 0.0) -> dict:
    """The L86 stress-check: when a per-unit P&L carries a large, low-frequency
    catastrophic leg (e.g. a binary payout on the rare adverse outcome) and some units
    are DROPPED because that leg's measurability could not be resolved from the tape
    (not because of their outcome), the drop is asymmetric — silently crediting an
    unmeasurable LOSS with payout=0 fabricates a free win and biases the reported mean
    upward. The honest move is to drop the unit entirely, then verify the drop pushed
    the verdict in the CONSERVATIVE direction, never a favorable one. S14's Q34 verdict
    ran exactly this check: crediting the 290 winner-leg-unmeasurable event-hours with
    the most GENEROUS counterfactual toward the verdict (payout = 0, as if the
    catastrophic leg never fired) still moved the mean from -0.0453 to -0.0152 — same
    sign, confirming the drop was not a thumb on the scale.

    `retained_pnls` is the caller's own per-unit net P&L for units where the
    catastrophic leg was measurable (this function computes no P&L itself, same
    discipline as `decompose_edge_by_leg_volume`). `n_dropped` is how many units were
    excluded on that leg's measurability. `generous_replacement_value` is the
    counterfactual value assigned to each dropped unit for the stress test (0.0 by
    default — "the catastrophic leg never fired" is usually the most generous
    assumption available; pass whatever your probe's actual most-favorable-to-the-
    verdict counterfactual is).

    Returns `reported_mean` (mean of `retained_pnls` alone, None if empty),
    `stress_mean` (mean including the dropped units at `generous_replacement_value`,
    None if there are no units at all), `n_retained`, `n_dropped`, and
    `sign_preserved` (True iff both means are defined and share a sign — 0 counts as
    its own sign, so two exact zeros preserve; None if either mean is undefined, an
    honest unknown rather than a fabricated True/False).
    """
    if n_dropped < 0:
        raise ValueError(f"n_dropped must be >= 0 (got {n_dropped})")
    n_retained = len(retained_pnls)
    reported_mean = (sum(retained_pnls) / n_retained) if n_retained else None
    total_n = n_retained + n_dropped
    stress_mean = (
        (sum(retained_pnls) + generous_replacement_value * n_dropped) / total_n
    ) if total_n else None
    sign_preserved = (
        _sign(reported_mean) == _sign(stress_mean)
        if reported_mean is not None and stress_mean is not None else None
    )
    return {
        "reported_mean": reported_mean,
        "stress_mean": stress_mean,
        "n_retained": n_retained,
        "n_dropped": n_dropped,
        "sign_preserved": sign_preserved,
    }
