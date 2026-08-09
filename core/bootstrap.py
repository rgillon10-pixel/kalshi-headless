"""Shared block-bootstrap + verdict-gate helpers — compounding L6/L27/L28/L32/L41/L51 into code.

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


def kish_effective_n(unit_sizes: Sequence[int]) -> dict:
    """The L322 reporting companion to `block_bootstrap`: when blocks are ragged in size,
    the raw unit count overstates how independent the pooled mean actually is — report
    Kish's effective sample size beside it.

    `block_bootstrap` pools every unit's observations with EQUAL PER-OBSERVATION weight
    (the correct choice for L6's blocking discipline — each unit still gets resampled as
    a whole block), which means a 23-observation unit counts 23x as heavily toward the
    pooled mean as a 1-observation unit. Comparing the resulting `n_units` against an
    adequacy floor (`bootstrap_verdict_admissible`'s `min_units`) then reads as if all
    units carried equal weight. Kish's formula, `(sum(n_i))**2 / sum(n_i**2)`, is the
    classic survey-sampling answer to "how many EQUALLY-sized units would give the same
    precision as this ragged mixture" — it equals `n_units` exactly when every block is
    the same size and falls below it as sizes get more unequal. Q54/S79's real block
    sizes (24 game-units, 133 pooled entries, sizes from 23 down to 1) give a Kish n of
    ~11.6: 2.4x headroom over the L41 floor of 10 reads as ~1.16x once size is accounted
    for.

    `unit_sizes` is the caller's own per-unit observation COUNT (e.g. `len(v) for v in
    unit_values.values()`, the same `unit_values` mapping `block_bootstrap` takes) — this
    function reads no tape/report fields itself, same discipline as `bracket_by_movement`.
    A negative size raises `ValueError` rather than silently corrupting the sums.

    Returns `n_units` (count of entries, including any zero-size ones), `n_obs` (their
    sum), `kish_n` (the effective sample size, `None` when `n_obs == 0` — an honest
    undefined ratio rather than a fabricated 0.0), and `design_effect`
    (`n_units / kish_n`, `None` when undefined) — `design_effect == 1.0` only when every
    unit is the same size, and grows without bound as block sizes get more ragged.
    """
    sizes = [int(s) for s in unit_sizes]
    for s in sizes:
        if s < 0:
            raise ValueError(f"unit_sizes must be non-negative (got {s})")
    n_units = len(sizes)
    n_obs = sum(sizes)
    if n_obs == 0:
        return {"n_units": n_units, "n_obs": 0, "kish_n": None, "design_effect": None}
    kish_n = (n_obs ** 2) / sum(s * s for s in sizes)
    return {
        "n_units": n_units, "n_obs": n_obs, "kish_n": kish_n,
        "design_effect": (n_units / kish_n) if kish_n else None,
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


SUB_TICK_RESIDUE_FLOOR: float = 1e-9


def hit_magnitude_decomposition(values: Sequence, *, tick: float = 0.01,
                                 residue_floor: float = SUB_TICK_RESIDUE_FLOOR) -> Dict:
    """The L236 granularity rule: `clears_tick_magnitude`'s L27 test (a positive sign at
    float precision is not an edge) applied to a raw HIT COUNT instead of a bootstrap lower
    bound — and applied **PER OBSERVATION**, never to a per-episode / per-group maximum.

    Why per-observation is load-bearing, not a style preference: a group is scored by its
    single best member, so every artifact sharing a group with one real hit disappears from
    the artifact tally. The group-max view therefore ALWAYS understates the artifact share,
    and it understates it in the flattering direction. The concrete case this encodes
    (S17's 2026-07-29 FOMC burst, `free` fee bracket): the per-episode-max view reports
    3 residue episodes covering 4 captures, while the honest per-observation view reports
    **5** residue captures — the fifth sits inside an episode whose max is +$0.003, so the
    max view hides it. Same tape, same scan, two different artifact counts.

    Second half of L236: a float residue belongs to the one subtraction that produced it,
    never to the group — quote the magnitude CLASS for a group and the exact float only for
    the case it belongs to. This function therefore never returns a single "the" residue
    value; it returns counts and shares, plus the max.

    `None` entries and non-finite floats (nan / +-inf) are counted in `n_unmeasurable` and
    EXCLUDED from `n` and from every share (L86: an unmeasurable observation is dropped and
    reported, never silently booked as zero).

    Returned keys (stable — consumers and tests key on these):
      n                 measurable observation count
      n_unmeasurable    None / nan / inf entries, excluded from n and from the shares
      n_residue         measurable v with abs(v) < residue_floor (pure float residue)
      n_sub_tick        measurable v with v < tick — residue INCLUDED (a residue is
                        trivially sub-tick; n_sub_tick - n_residue is the genuinely
                        nonzero-but-still-unfillable population)
      n_clears_tick     measurable v with v >= tick
      residue_share     n_residue / n, or None when n == 0 (never 0.0 masquerading
                        as a measured zero)
      sub_tick_share    n_sub_tick / n, or None when n == 0
      max               max of the measurable values, or None when n == 0
      tick, residue_floor   the thresholds actually used, echoed for provenance

    Pure; never raises on empty / None / ragged input.
    """
    measurable: List[float] = []
    n_unmeasurable = 0
    for v in (values or []):
        f = None
        if v is not None and not isinstance(v, bool):
            try:
                f = float(v)
            except (TypeError, ValueError):
                f = None
        if f is None or f != f or f == float("inf") or f == float("-inf"):
            n_unmeasurable += 1
        else:
            measurable.append(f)
    n = len(measurable)
    n_residue = sum(1 for v in measurable if abs(v) < residue_floor)
    n_sub_tick = sum(1 for v in measurable if v < tick)
    n_clears_tick = sum(1 for v in measurable if v >= tick)
    return {
        "n": n,
        "n_unmeasurable": n_unmeasurable,
        "n_residue": n_residue,
        "n_sub_tick": n_sub_tick,
        "n_clears_tick": n_clears_tick,
        "residue_share": (n_residue / n) if n else None,
        "sub_tick_share": (n_sub_tick / n) if n else None,
        "max": max(measurable) if n else None,
        "tick": tick,
        "residue_floor": residue_floor,
    }


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


def disagreement_subset_calibration(hit_signal: Sequence[bool], hit_mid: Sequence[bool], *,
                                    tol: float = 1e-9) -> dict:
    """The L51 framing guardrail: a "does signal X beat the mid" calibration precheck run
    on a DISAGREEMENT subset (both directional, X's call != the mid's call) produces two
    hit rates that are mechanically COMPLEMENTARY on a strict two-way market — `hit_signal[i]
    == (not hit_mid[i])` for every row, so `signal_accuracy == 1 - mid_accuracy` and the two
    numbers sum to exactly 1.0. They are NOT two independent measurements. Q26/S22's
    disagreement-subset numbers (signal 27.9% vs mid 72.1%) looked like a hidden contrarian
    edge until the verifier confirmed the arithmetic identity: X can only "beat the mid" here
    if the mid is <50% accurate exactly where they disagree — a bar a liquid, calibrated
    2-way market essentially never fails, and sign-flipping X on this subset just reproduces
    betting the mid (zero independent edge either direction).

    Headline guidance (report it this way, per L51): report the single statistic
    "mid accuracy where they disagree = X%", NOT two independent hit rates — quoting both
    `mid_accuracy` and `signal_accuracy` as if they were separate evidence manufactures the
    illusion of an extra data point.

    This is a framing/interpretation guardrail, NOT a bootstrap — it computes no CI and makes
    no verdict; it just exposes the complementarity so a report cannot double-count it.

    Both sequences cover the DISAGREEMENT subset only: `hit_signal[i]` = did signal X's
    directional call win at settlement, `hit_mid[i]` = did the mid's directional call win, for
    observations where X's call != the mid's call. `is_strict_two_way` is True iff every row
    obeys `hit_signal[i] == (not hit_mid[i])`; `violating_indices` lists any rows that don't —
    which PROVE the caller's "disagreement subset" was not a strict directional two-way
    partition (e.g. a 3-way market or a non-directional row leaked in, the per-design caveat
    L51 flags). Violations are reported, never raised on, so the helper never masks a real
    design bug.

    Returns `{"n", "mid_accuracy", "signal_accuracy", "is_strict_two_way",
    "violating_indices"}`. Raises `ValueError` on a length mismatch. On empty input returns an
    honest empty report (`n=0`, accuracies `None`, `is_strict_two_way=True`,
    `violating_indices=[]`) rather than crashing, matching the empty-input discipline of the
    sibling helpers in this file.
    """
    if len(hit_signal) != len(hit_mid):
        raise ValueError(
            f"hit_signal and hit_mid must be the same length "
            f"(got {len(hit_signal)} vs {len(hit_mid)})"
        )
    n = len(hit_signal)
    if n == 0:
        return {"n": 0, "mid_accuracy": None, "signal_accuracy": None,
                "is_strict_two_way": True, "violating_indices": []}
    mid_accuracy = sum(1 for h in hit_mid if h) / n
    signal_accuracy = sum(1 for h in hit_signal if h) / n
    violating_indices = [
        i for i, (s, m) in enumerate(zip(hit_signal, hit_mid)) if bool(s) == bool(m)
    ]
    return {
        "n": n,
        "mid_accuracy": mid_accuracy,
        "signal_accuracy": signal_accuracy,
        "is_strict_two_way": not violating_indices,
        "violating_indices": violating_indices,
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


# --------------------------------------------------------------------------- #
# L251 — entry-instant concentration (the tape-start-artifact descriptor)
# --------------------------------------------------------------------------- #

# The share of a population's entries sitting on ONE instant at or above which
# `entry_instant_concentration` sets its `concentrated` flag. 0.5 is a deliberately
# blunt, DOCUMENTED default, not a derived threshold: at half the population on a
# single capture pass, a per-unit count (games, series, tickers) has stopped being
# evidence of temporal breadth. Callers may override it; the value actually used is
# always echoed back in the result dict so a report can never quietly reinterpret it.
TAPE_START_CONCENTRATION_SHARE = 0.5


def entry_instant_concentration(instants: Sequence, *, unit_labels: Sequence = None,
                                flag_share: float = TAPE_START_CONCENTRATION_SHARE
                                ) -> dict:
    """The L251 precheck: how many DISTINCT moments does a probe's entry population
    actually sample, and how much of it piles onto the single most-populated instant?

    Q49/S68 (2026-08-01) reported its primary population as "20 candidates, 5 game-series,
    14 games" — counts that read as breadth. Every one of those 20 entries shared ONE
    `entry_captured_at` (`2026-07-07T01:23:57.700581+00:00`, the depth tape's first
    full capture pass), because the probe's entry rule was "earliest capture per ticker,
    THEN filter to ttc<=24h" rather than "first snapshot with ttc<=H". An "earliest, then
    filter" rule pulls every ticker whose whole pre-close history begins inside the window
    back to the tape's own start, so the resulting sample is one snapshot of the market
    wearing a unit count as a disguise. The verifier caught it by reading the timestamps;
    this function is the machine-checkable half of that catch.

    What it measures (a DESCRIPTOR, never a verdict): entry counts per distinct instant,
    the top instant's share, and — when `unit_labels` is supplied (the SAME bootstrap unit
    the caller will block on, per L6) — how many of those units are represented on that
    single top instant. `n_units == n_units_on_top_instant` is the exact shape that makes a
    unit count non-evidence: every block the bootstrap will resample draws from one moment,
    so the resample carries no temporal independence at all.

    What it CANNOT do, stated so no caller over-reads it: distinguish a tape-start artifact
    from a genuine, legitimate cluster (an event study around one release instant SHOULD
    concentrate), and it cannot see the entry RULE that produced the distribution — that
    half stays protocol (`.claude/agents/edge-prober.md`, L251). It reports the number and
    names its own threshold; the judgment is the reader's.

    Empty input returns `no_signal=True` with zeroed counts rather than raising or
    implying a clean population — the repo's no_signal-vs-False discipline: "nothing was
    measured" is never reported as "nothing is wrong".

    `unit_labels`, when given, must align element-wise with `instants`; a length mismatch
    raises rather than silently misaligning the two sequences (same posture as
    `bracket_by_movement`). Ties for the top instant are broken by `str()` order so the
    result is deterministic across runs and across mixed `str`/`datetime` inputs.
    """
    if unit_labels is not None and len(unit_labels) != len(instants):
        raise ValueError(
            f"unit_labels and instants must be the same length "
            f"(got {len(unit_labels)} vs {len(instants)})"
        )
    n = len(instants)
    if n == 0:
        return {
            "no_signal": True,
            "n_entries": 0,
            "n_distinct_instants": 0,
            "top_instant": None,
            "top_instant_count": 0,
            "max_instant_share": 0.0,
            "entries_per_distinct_instant": 0.0,
            "flag_share": flag_share,
            "concentrated": False,
            "single_instant": False,
            "n_units": None if unit_labels is None else 0,
            "n_units_on_top_instant": None if unit_labels is None else 0,
            "unit_share_on_top_instant": None if unit_labels is None else 0.0,
            "n_unit_instant_pairs": None if unit_labels is None else 0,
        }

    counts: Dict = {}
    for inst in instants:
        counts[inst] = counts.get(inst, 0) + 1
    # deterministic: highest count first, then str() order (never relies on dict order,
    # and never compares a datetime to a str)
    top_instant = sorted(counts, key=lambda k: (-counts[k], str(k)))[0]
    top_count = counts[top_instant]

    out = {
        "no_signal": False,
        "n_entries": n,
        "n_distinct_instants": len(counts),
        "top_instant": top_instant,
        "top_instant_count": top_count,
        "max_instant_share": top_count / n,
        "entries_per_distinct_instant": n / len(counts),
        "flag_share": flag_share,
        "concentrated": (top_count / n) >= flag_share,
        "single_instant": len(counts) == 1,
        "n_units": None,
        "n_units_on_top_instant": None,
        "unit_share_on_top_instant": None,
        "n_unit_instant_pairs": None,
    }
    if unit_labels is not None:
        units = set(unit_labels)
        units_on_top = {u for u, i in zip(unit_labels, instants) if i == top_instant}
        pairs = {(u, i) for u, i in zip(unit_labels, instants)}
        out["n_units"] = len(units)
        out["n_units_on_top_instant"] = len(units_on_top)
        out["unit_share_on_top_instant"] = (len(units_on_top) / len(units)) if units else 0.0
        out["n_unit_instant_pairs"] = len(pairs)
    return out


# --------------------------------------------------------------------------- #
# L249 — sign-bounded objective (is the bootstrap's ALIVE branch reachable at all?)
# --------------------------------------------------------------------------- #

# Magnitudes at or below this are treated as exactly zero when counting strict signs.
# Deliberately far below a 1e-9 sub-tick residue (`SUB_TICK_RESIDUE_FLOOR`): this tolerance
# exists to absorb float round-trip noise on a value that is algebraically 0.0, NOT to
# swallow economically small P&L. Echoed back in the result so a caller can never quietly
# reinterpret it.
SIGN_SUPPORT_TOL: float = 1e-12

# Below this many observations, "every observation shares one sign" is a plausible accident
# of a small sample rather than evidence of a bound, so the result carries `weak_sample=True`.
# A blunt, DOCUMENTED default (five coin flips landing the same way is unremarkable), not a
# derived threshold; overridable and always echoed.
MIN_OBS_FOR_SIGN_SUPPORT: int = 5


def sign_bounded_objective(unit_values: Dict[str, Sequence[float]], *,
                            tol: float = SIGN_SUPPORT_TOL,
                            min_obs: int = MIN_OBS_FOR_SIGN_SUPPORT,
                            admissibility: dict = None) -> dict:
    """The L249 precheck: does the object being bootstrapped have a support that could
    EVER have disagreed with the claim, or does its own entry gate guarantee the sign?

    `bootstrap_verdict_admissible` (L41) asks whether any UNIT MEAN sits on the opposite
    side of zero. That gate cannot tell two very different failures apart, and Q49/S68
    (2026-08-01) hit both at once:

      * `below_min_units` — an ADEQUACY statement. More units would fix it. The verdict is
        "not measured yet".
      * `no_opposing_unit` on an object whose RAW OBSERVATIONS never cross zero — a
        DEFINITIONAL statement. Q49's entry gate ("yes-spread >= two maker fees") combined
        with `best_yes_ask == 1 - best_no_bid` by collector construction
        (`collection/normalize.py`) makes every double-fill's gross capture >= the two fees
        BY ARITHMETIC, so net P&L cannot be negative. No resample, and no quantity of
        additional data collected under the same gate, can ever produce an opposing-sign
        cluster. Reporting that cut's `admissible=False` as a kill is reporting a property
        of the gate as if it were news about the strategy.

    This function measures the discriminator the L41 gate is blind to: the sign support of
    the OBSERVATIONS, not of the unit means. If no observation is strictly positive while
    another is strictly negative, the bootstrap's opposing branch is structurally
    unreachable and the cut is a DIAGNOSTIC, never a verdict.

    Pass the `bootstrap_verdict_admissible(...)` dict as `admissibility` and the result also
    carries `inadmissibility_is_definitional`: True when that gate failed for
    `no_opposing_unit` AND the support is one-sided (the Q49 both-fill object: reasons
    `['below_min_units', 'no_opposing_unit']`, all 11 double-fills exactly $0.0000), False
    when the only complaint was adequacy (the Q49 strategy-level object, which includes the
    unhedged single-side legs, straddles -0.58..+0.73 and is the cut the verdict must rest
    on). None when no admissibility dict is supplied.

    Honest limits, stated so no caller over-reads the flag:

      1. It sees the SYMPTOM (a one-sided support), never the algebra. It cannot PROVE an
         entry gate bounds the sign — reading the gate math stays a human/protocol step
         (`.claude/agents/edge-prober.md`, `.claude/agents/verifier.md`, L249). What it does
         is refuse to let that reading be skipped silently.
      2. A one-sided support can be luck on a small sample; `weak_sample` flags
         `n_obs < min_obs` for exactly that reason. One-sidedness is a REASON TO CHECK the
         gate, not a finding on its own.
      3. `verdict_bearing=True` is NOT a verdict and NOT admissibility — it says only that
         the object COULD have disagreed. It never replaces `bootstrap_verdict_admissible`
         or `clears_tick_magnitude`; it explains why one of them failed.

    Empty input returns `no_signal=True` with zeroed counts rather than raising or implying
    a clean object — the repo's no_signal-vs-False discipline: "nothing was measured" is
    never reported as "nothing is wrong".
    """
    values = [float(v) for seq in unit_values.values() for v in seq]
    unit_means = {k: sum(v) / len(v) for k, v in unit_values.items() if len(v) > 0}
    n_obs = len(values)
    if n_obs == 0:
        return {
            "no_signal": True,
            "n_units": len(unit_means),
            "n_obs": 0,
            "n_positive": 0, "n_negative": 0, "n_zero": 0,
            "one_sided_support": False,
            "support_sign": None,
            "all_zero_support": False,
            "verdict_bearing": False,
            "unit_means_one_sided": False,
            "observation_level_straddle_only": False,
            "weak_sample": True,
            "min_value": None, "max_value": None,
            "tol": tol, "min_obs": min_obs,
            "inadmissibility_is_definitional": None,
            "reasons": ["empty"],
        }

    n_pos = sum(1 for v in values if v > tol)
    n_neg = sum(1 for v in values if v < -tol)
    n_zero = n_obs - n_pos - n_neg
    one_sided = not (n_pos > 0 and n_neg > 0)
    all_zero = (n_pos == 0 and n_neg == 0)
    if all_zero:
        support_sign = 0
    elif n_neg == 0:
        support_sign = 1
    elif n_pos == 0:
        support_sign = -1
    else:
        support_sign = None

    mean_pos = sum(1 for m in unit_means.values() if m > tol)
    mean_neg = sum(1 for m in unit_means.values() if m < -tol)
    unit_means_one_sided = not (mean_pos > 0 and mean_neg > 0)

    reasons = []
    if one_sided:
        reasons.append("one_sided_support")
    if all_zero:
        reasons.append("all_zero_support")
    if n_obs < min_obs:
        reasons.append("weak_sample")

    definitional = None
    if admissibility is not None:
        definitional = bool(
            admissibility.get("admissible") is False
            and "no_opposing_unit" in (admissibility.get("reasons") or [])
            and one_sided
        )

    return {
        "no_signal": False,
        "n_units": len(unit_means),
        "n_obs": n_obs,
        "n_positive": n_pos, "n_negative": n_neg, "n_zero": n_zero,
        "one_sided_support": one_sided,
        "support_sign": support_sign,
        "all_zero_support": all_zero,
        "verdict_bearing": not one_sided,
        "unit_means_one_sided": unit_means_one_sided,
        # unit means all point one way but the raw observations DO cross zero: the L41 gate
        # is then making an adequacy claim, not a definitional one — more units could flip it
        "observation_level_straddle_only": unit_means_one_sided and not one_sided,
        "weak_sample": n_obs < min_obs,
        "min_value": min(values), "max_value": max(values),
        "tol": tol, "min_obs": min_obs,
        "inadmissibility_is_definitional": definitional,
        "reasons": reasons,
    }


# --------------------------------------------------------------------------- #
# L250 — turnover-rule saturation (does a LOOSE fill proxy's high fill rate mean
#         anything at all, in either direction?)
# --------------------------------------------------------------------------- #

# Cumulative observed departures at or above this multiple of the queue ahead of us make the
# loose rule's fill decision a foregone conclusion: whatever our queue position was, the
# counter cleared it many times over. A DOCUMENTED, blunt threshold (not fitted to data) —
# Q49's `unrestricted` turnover cut sits ~900x (YES) / ~218x (NO) above it — always echoed
# back in the result so a caller cannot quietly reinterpret it.
TURNOVER_SATURATION_RATIO: float = 10.0

# At or above this fill rate the loose rule has essentially no variation left to carry
# information: it fills nearly everything it is shown.
TURNOVER_SATURATION_FILL_RATE: float = 0.95

# "A hold window longer than ~a few snapshots" (L250's own wording) made concrete. Below
# this many snapshots per unit the saturation call is withheld (`long_hold=False`) rather
# than asserted, because a short window genuinely cannot accumulate migration.
MIN_SNAPSHOTS_FOR_SATURATION: int = 8

# The only rule allowed to carry a fill-rate HEADLINE (L250 / Q49 precedent). The loose
# turnover rule is a labeled diagnostic, never the headline.
PRIMARY_FILL_RULE: str = "touch"
DIAGNOSTIC_FILL_RULE: str = "turnover"


def turnover_rule_saturation(loose_filled: Sequence[bool], strict_filled: Sequence[bool], *,
                             departures: Sequence[float], queue_ahead: Sequence[float],
                             snapshots_held: Sequence = None,
                             ratio_floor: float = TURNOVER_SATURATION_RATIO,
                             fill_rate_floor: float = TURNOVER_SATURATION_FILL_RATE,
                             min_snapshots: int = MIN_SNAPSHOTS_FOR_SATURATION) -> dict:
    """The L250 precheck: over a multi-snapshot hold, does the LOOSE (Q27/S19 "turnover")
    queue-departure fill rule still measure anything — or has it saturated?

    L48 established that a turnover proxy (departures at ANY level at/above our resting
    price) can rule a population OUT (too thin to fill), never IN. L250 is the corollary
    L48 did not state: over a hold long enough for the book to migrate away from a stale
    resting price, EVERY size reduction anywhere at/above that price is counted as advancing
    us, so the cumulative counter runs to tens of thousands against a queue of tens and the
    rule fills essentially everything. At that point a HIGH fill rate is not weak evidence
    of fillability — it is no evidence in EITHER direction, because the statistic has no
    variation left. Q49/S68 (2026-08-01) is the measured case: on the same 445 candidates,
    the loose rule read 97.98% both-sides-filled while the strict `touch` rule (departures at
    OUR OWN price level, only while we are at the touch) read 42.47%.

    Inputs are per-unit and must align element-wise (one entry per rested order / candidate):

      * `loose_filled` / `strict_filled` — each rule's fill outcome for the SAME unit.
      * `departures` — cumulative observed departures the loose rule accumulated.
      * `queue_ahead` — the resting size ahead of us at entry (the counter's target).
      * `snapshots_held` — optional; snapshots the order was held across. Supplied, it gates
        the `long_hold` half of the saturation call; omitted, `long_hold` is None and the
        call rests on the ratio + fill-rate halves alone (stated in `reasons`).

    `saturated` is True only when all supplied halves agree: the loose rule fills at or above
    `fill_rate_floor`, the MEDIAN departures-to-queue ratio is at or above `ratio_floor`, and
    (when snapshots are given) the median hold clears `min_snapshots`. A unit whose
    `queue_ahead` is 0 (front of queue) has an undefined ratio and is excluded from the ratio
    median rather than treated as infinite or as zero — it is counted in
    `n_units_zero_queue` so the exclusion is visible.

    What this CANNOT do, stated so no caller over-reads it:

      1. It does not validate the strict rule. `touch` is itself generous — a depth tape with
         no trade field cannot distinguish a cancel at our price from a fill (L68/L106) — so
         a low `strict_fill_rate` is still an upper bound, not a measured fill rate.
      2. `saturated=False` is NOT a license to headline the loose rule. The L48 direction
         holds unconditionally: a turnover proxy rules a population OUT, never IN. That is
         why `headline_fill_rate` refuses the loose rule outright on a saturated report and
         why `loose_rule_direction` never returns "IN".
      3. Which rule is "primary" for a given probe, and how long a hold is too long, remain
         per-design judgments (`.claude/agents/edge-prober.md`, L250). This function reports
         the statistic and names its own thresholds; it does not choose the probe's design.

    Empty input returns `no_signal=True` with zeroed counts rather than raising or implying a
    clean population — the repo's no_signal-vs-False discipline: "nothing was measured" is
    never reported as "nothing is wrong".
    """
    n = len(loose_filled)
    for name, seq in (("strict_filled", strict_filled), ("departures", departures),
                      ("queue_ahead", queue_ahead)):
        if len(seq) != n:
            raise ValueError(f"{name} ({len(seq)}) must align with loose_filled ({n})")
    if snapshots_held is not None and len(snapshots_held) != n:
        raise ValueError(f"snapshots_held ({len(snapshots_held)}) must align with "
                         f"loose_filled ({n})")

    if n == 0:
        return {
            "no_signal": True,
            "n_units": 0,
            "loose_rule": DIAGNOSTIC_FILL_RULE, "strict_rule": PRIMARY_FILL_RULE,
            "loose_fill_rate": None, "strict_fill_rate": None, "fill_rate_gap": None,
            "n_units_with_ratio": 0, "n_units_zero_queue": 0,
            "median_departure_queue_ratio": None, "frac_units_above_ratio_floor": None,
            "median_snapshots_held": None, "long_hold": None,
            "loose_rule_discriminates": False, "saturated": False,
            "loose_rule_direction": "none",
            "ratio_floor": ratio_floor, "fill_rate_floor": fill_rate_floor,
            "min_snapshots": min_snapshots,
            "reasons": ["empty"],
        }

    n_loose = sum(1 for f in loose_filled if f)
    n_strict = sum(1 for f in strict_filled if f)
    loose_rate = n_loose / n
    strict_rate = n_strict / n

    ratios: List[float] = []
    n_zero_queue = 0
    for d, q in zip(departures, queue_ahead):
        q = float(q)
        if q <= 0.0:
            n_zero_queue += 1
            continue
        ratios.append(float(d) / q)
    med_ratio = _median_of(ratios)
    frac_above = (sum(1 for r in ratios if r >= ratio_floor) / len(ratios)) if ratios else None

    med_snaps = None
    long_hold = None
    if snapshots_held is not None:
        med_snaps = _median_of([float(s) for s in snapshots_held])
        long_hold = med_snaps is not None and med_snaps >= min_snapshots

    discriminates = 0 < n_loose < n

    reasons: List[str] = []
    rate_hit = loose_rate >= fill_rate_floor
    ratio_hit = med_ratio is not None and med_ratio >= ratio_floor
    if rate_hit:
        reasons.append("loose_fill_rate_at_or_above_floor")
    if ratio_hit:
        reasons.append("median_departures_swamp_queue")
    if not discriminates:
        reasons.append("loose_rule_has_no_variation")
    if snapshots_held is None:
        reasons.append("no_snapshot_counts_supplied")
    elif long_hold:
        reasons.append("long_hold")
    if not ratios:
        reasons.append("no_unit_with_a_positive_queue_ahead")

    saturated = bool(rate_hit and ratio_hit and (long_hold is not False))

    return {
        "no_signal": False,
        "n_units": n,
        "loose_rule": DIAGNOSTIC_FILL_RULE, "strict_rule": PRIMARY_FILL_RULE,
        "loose_fill_rate": loose_rate, "strict_fill_rate": strict_rate,
        "fill_rate_gap": loose_rate - strict_rate,
        "n_units_with_ratio": len(ratios), "n_units_zero_queue": n_zero_queue,
        "median_departure_queue_ratio": med_ratio,
        "frac_units_above_ratio_floor": frac_above,
        "median_snapshots_held": med_snaps, "long_hold": long_hold,
        "loose_rule_discriminates": discriminates,
        "saturated": saturated,
        # L48 unconditionally + L250's corollary: a saturated loose rule points NOWHERE.
        "loose_rule_direction": "none" if saturated else "OUT_only",
        "ratio_floor": ratio_floor, "fill_rate_floor": fill_rate_floor,
        "min_snapshots": min_snapshots,
        "reasons": reasons,
    }


def headline_fill_rate(saturation: dict, rule: str) -> float:
    """The operative half of L250: return the fill rate a probe may HEADLINE, refusing the
    loose rule outright.

    A probe that wants to publish a fill-rate headline routes it through here. Asking for the
    loose (`turnover`) rule raises — always, saturated or not, because L48's "rules a
    population OUT, never IN" already forbids a loose-proxy fill rate from carrying an
    affirmative headline, and L250 removes even the OUT reading once the rule has saturated.
    Asking for the strict (`touch`) rule returns its rate. A `no_signal` report raises rather
    than returning 0.0 — "nothing was measured" is never a headline.

    This can only REMOVE a headline, never award one: the returned number is still just a
    fill rate, and a strict-rule fill rate is itself an upper bound (L68/L106 — a depth tape
    cannot tell a cancel at our price from a fill).
    """
    if not isinstance(saturation, dict):
        raise TypeError("saturation must be the dict returned by turnover_rule_saturation")
    if saturation.get("no_signal"):
        raise ValueError("no_signal report carries no headline fill rate (L250)")
    loose = saturation.get("loose_rule", DIAGNOSTIC_FILL_RULE)
    strict = saturation.get("strict_rule", PRIMARY_FILL_RULE)
    if rule == loose:
        raise ValueError(
            f"the loose `{loose}` queue-departure rule may not carry a fill-rate headline "
            f"(L48: it rules a population OUT, never IN; L250: saturated="
            f"{saturation.get('saturated')} — over a long hold it fills everything and points "
            f"nowhere). Headline the strict `{strict}` rule and label `{loose}` a diagnostic.")
    if rule != strict:
        raise ValueError(f"unknown fill rule {rule!r} (expected {strict!r} or {loose!r})")
    return float(saturation["strict_fill_rate"])


def _median_of(xs: Sequence[float]):
    vals = sorted(float(x) for x in xs)
    if not vals:
        return None
    m = len(vals) // 2
    return vals[m] if len(vals) % 2 else (vals[m - 1] + vals[m]) / 2.0
