#!/usr/bin/env python3
"""EMOS demo — runnable proof for kb/quant-finance/01-weather-forecasting-alpha.md

The note's core claim (Theme 5, first principles): a raw ensemble is UNDERDISPERSED —
its spread is too small, so the fraction-of-members-in-a-bracket estimate is overconfident
and biased. You cannot read a tradable probability off it. EMOS (Ensemble Model Output
Statistics; Gneiting, Raftery, Westveld & Goldman 2005, *Monthly Weather Review* 133) fixes
this by fitting a parametric predictive distribution whose mean is a bias-corrected affine
function of the ensemble mean and whose VARIANCE is an affine function of the ensemble
spread, with the coefficients chosen to MINIMIZE CRPS over a training set.

This script demonstrates, on a deterministic toy ensemble, that the calibrated EMOS Gaussian
scores strictly lower mean CRPS on held-out data than the raw ensemble — i.e. post-processing
beats the underdispersed raw forecast — and then prices one temperature bracket by integrating
the fitted Gaussian. STDLIB ONLY (math, statistics, random): no numpy/scipy, fully seeded and
reproducible. Re-running prints identical numbers.

Closed-form Gaussian CRPS (Gneiting & Raftery 2007, *JASA* 102): for a Normal(mu, sigma)
predictive distribution and observation y, with z = (y - mu) / sigma,

    CRPS(N(mu, sigma), y) = sigma * [ z*(2*Phi(z) - 1) + 2*phi(z) - 1/sqrt(pi) ]

where Phi is the standard-normal CDF and phi the standard-normal PDF. CRPS is a strictly
proper scoring rule, so minimizing it yields the best full-distribution forecast — exactly the
profit-optimal probability source for threshold (bracket) contracts. Phi is implemented via
math.erf; no scipy.
"""
from __future__ import annotations

import math
import random
import statistics
from typing import List, Sequence, Tuple

SEED = 20260618          # fixed seed -> deterministic toy ensemble, identical reruns
N_TRAIN = 400            # training (ensemble, observed) pairs
N_TEST = 200             # held-out pairs for the honest CRPS comparison
N_MEMBERS = 12           # ensemble members per day
SQRT_PI = math.sqrt(math.pi)


# ─── Standard normal, stdlib only (Hard: no scipy) ────────────────────────────

def _phi(x: float) -> float:
    """Standard-normal PDF."""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _Phi(x: float) -> float:
    """Standard-normal CDF via math.erf (no scipy)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


# ─── Closed-form Gaussian CRPS (Gneiting & Raftery 2007) ──────────────────────

def crps_gaussian(mu: float, sigma: float, y: float) -> float:
    """CRPS of a Normal(mu, sigma) predictive distribution against observation y.

    Smaller is better. sigma must be > 0 (a degenerate point forecast has no CRPS here).
    """
    if sigma <= 0:
        raise ValueError(f"sigma must be > 0, got {sigma!r}")
    z = (y - mu) / sigma
    return sigma * (z * (2.0 * _Phi(z) - 1.0) + 2.0 * _phi(z) - 1.0 / SQRT_PI)


# ─── Toy ensemble: a true Tmax with a deterministic, UNDERDISPERSED ensemble ──

def _ensemble_mean(members: Sequence[float]) -> float:
    return statistics.fmean(members)


def _ensemble_spread(members: Sequence[float]) -> float:
    """Sample standard deviation of the members — the ensemble's claimed spread.

    Uses statistics.stdev (sample sd, n-1). Deliberately NOT pstdev: Hard Rule #2 reserves
    population-stdev to core.stats.safe_pstdev (the >=4-member guard); the toy spread here is
    a plain sample sd of a fixed 12-member array and never feeds that path.
    """
    return statistics.stdev(members)


def make_dataset(n: int, rng: random.Random) -> List[Tuple[List[float], float]]:
    """Build `n` (ensemble_members, observed_Tmax) pairs.

    Generative truth: each day has a true Tmax ~ a seasonal-ish spread around 75F with real
    day-to-day uncertainty of TRUE_SD. The ensemble is drawn around a BIASED proxy for the
    truth (cold bias of BIAS degrees) with too-small member spread (ENS_SD << the spread the
    members *should* have) — this is the underdispersion the note describes. The observation
    is the true Tmax plus small observation noise. So the raw ensemble is both biased and
    overconfident; EMOS has bias + spread to correct.
    """
    TRUE_SD = 9.0          # real day-to-day uncertainty of Tmax
    BIAS = 2.5             # systematic cold bias baked into the ensemble's center
    ENS_SD = 3.0           # member spread — far too small vs TRUE_SD (underdispersion)
    OBS_NOISE_SD = 1.0     # measurement noise on the observed Tmax

    data: List[Tuple[List[float], float]] = []
    for _ in range(n):
        true_tmax = 75.0 + rng.gauss(0.0, TRUE_SD)
        ens_center = true_tmax - BIAS                      # ensemble is cold-biased
        members = [ens_center + rng.gauss(0.0, ENS_SD) for _ in range(N_MEMBERS)]
        observed = true_tmax + rng.gauss(0.0, OBS_NOISE_SD)
        data.append((members, observed))
    return data


# ─── EMOS fit: minimize mean training CRPS over (a, b) spread coefficients ─────
# Predictive mean:     mu      = ens_mean + mean_bias     (affine: slope fixed at 1, learn
#                                                          intercept = bias correction)
# Predictive variance: sigma^2 = a + b * ens_var          (affine in ensemble variance)
# We fit mean_bias in closed form (CRPS-optimal location is the mean correction here), then
# search (a, b) >= 0 on a grid + coordinate descent to minimize mean training CRPS.

def _mean_crps_for_coeffs(
    data: Sequence[Tuple[List[float], float]],
    mean_bias: float,
    a: float,
    b: float,
) -> float:
    """Mean CRPS over `data` for predictive N(ens_mean + mean_bias, sqrt(a + b*ens_var))."""
    total = 0.0
    for members, observed in data:
        em = _ensemble_mean(members)
        ev = _ensemble_spread(members) ** 2                # ensemble variance
        var = a + b * ev
        if var <= 0.0:
            return math.inf                                # invalid spread model
        total += crps_gaussian(em + mean_bias, math.sqrt(var), observed)
    return total / len(data)


def fit_emos(data: Sequence[Tuple[List[float], float]]) -> Tuple[float, float, float]:
    """Return (mean_bias, a, b) minimizing mean training CRPS.

    mean_bias is the average (observed - ens_mean) residual (the CRPS-optimal location shift
    for a Gaussian is the bias correction of the mean). (a, b) are found by a deterministic
    grid seed followed by coordinate descent with shrinking step — a simple, dependency-free
    minimizer that lands on the same point every run.
    """
    mean_bias = statistics.fmean(observed - _ensemble_mean(members)
                                 for members, observed in data)

    # Deterministic grid seed for (a, b) over plausible ranges.
    best = (1.0, 1.0)
    best_score = math.inf
    for ai in range(0, 121, 4):                  # a in [0, 120]
        a = float(ai)
        for bi in range(0, 81, 4):               # b in [0, 80] (variance inflation factor)
            b = float(bi)
            s = _mean_crps_for_coeffs(data, mean_bias, a, b)
            if s < best_score:
                best_score, best = s, (a, b)

    # Coordinate descent with shrinking step to refine the grid winner.
    a, b = best
    step = 4.0
    while step > 1e-3:
        improved = False
        for da, db in ((step, 0.0), (-step, 0.0), (0.0, step), (0.0, -step)):
            na, nb = max(0.0, a + da), max(0.0, b + db)
            s = _mean_crps_for_coeffs(data, mean_bias, na, nb)
            if s < best_score - 1e-12:
                best_score, a, b, improved = s, na, nb, True
        if not improved:
            step /= 2.0
    return mean_bias, a, b


# ─── Raw-ensemble CRPS baseline (the underdispersed forecast, no post-processing) ──

def mean_crps_raw(data: Sequence[Tuple[List[float], float]]) -> float:
    """Mean CRPS treating the raw ensemble as N(ens_mean, ens_spread) — no calibration.

    This is the honest 'naive ensemble' baseline: take the members at face value (their own
    mean and their own too-small spread). It is biased AND overconfident; EMOS should beat it.
    """
    total = 0.0
    for members, observed in data:
        em = _ensemble_mean(members)
        sd = _ensemble_spread(members)
        total += crps_gaussian(em, sd, observed)
    return total / len(data)


def mean_crps_emos(
    data: Sequence[Tuple[List[float], float]],
    mean_bias: float,
    a: float,
    b: float,
) -> float:
    """Mean CRPS of the fitted EMOS Gaussian on `data`."""
    return _mean_crps_for_coeffs(data, mean_bias, a, b)


# ─── Bracket pricing: integrate the fitted Gaussian over [lo, hi) ─────────────

def bracket_prob(mu: float, sigma: float, lo: float, hi: float) -> float:
    """P(lo <= Tmax < hi) under the predictive Normal(mu, sigma) = Phi(hi) - Phi(lo).

    This is the per-bracket probability the note calls for (recipe step 4): integrate the
    calibrated distribution between the bracket thresholds. It is NOT a tradable price until
    compared to the market's overround-normalized ask (core.pricing.normalized_ask) and the
    fee bar (scripts/fee_breakeven.py) — see Hard Rule #3 and the note's caveats.
    """
    return _Phi((hi - mu) / sigma) - _Phi((lo - mu) / sigma)


# ─── Demo ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    rng = random.Random(SEED)
    train = make_dataset(N_TRAIN, rng)
    test = make_dataset(N_TEST, rng)

    mean_bias, a, b = fit_emos(train)

    crps_raw = mean_crps_raw(test)
    crps_emos = mean_crps_emos(test, mean_bias, a, b)

    print("EMOS demo — calibrated post-processing beats the raw underdispersed ensemble")
    print(f"  seed={SEED}  train={N_TRAIN}  test={N_TEST}  members/day={N_MEMBERS}\n")

    print("Fitted EMOS Gaussian (CRPS-minimizing):")
    print(f"  predictive mean     mu      = ens_mean + {mean_bias:+.4f}   (bias correction)")
    print(f"  predictive variance sigma^2 = {a:.4f} + {b:.4f} * ens_var   (spread inflation)\n")

    print("Held-out mean CRPS (lower is better):")
    print(f"  CRPS_raw  (naive ensemble)     = {crps_raw:.6f}")
    print(f"  CRPS_emos (calibrated EMOS)    = {crps_emos:.6f}")
    print(f"  improvement                    = {crps_raw - crps_emos:.6f} "
          f"({100.0 * (crps_raw - crps_emos) / crps_raw:.2f}% lower)")
    assert crps_emos < crps_raw, "EMOS must beat the raw ensemble — underdispersion uncorrected"
    print("  -> EMOS strictly lower. Post-processing fixes the underdispersion.\n")

    # Price one temperature bracket P(74 <= Tmax < 78) using the fitted distribution on a
    # representative test day (the first held-out day's ensemble).
    members0, _ = test[0]
    mu0 = _ensemble_mean(members0) + mean_bias
    sigma0 = math.sqrt(a + b * _ensemble_spread(members0) ** 2)
    lo, hi = 74.0, 78.0
    p_bracket = bracket_prob(mu0, sigma0, lo, hi)
    print(f"Bracket price on test day 0  (mu={mu0:.4f}, sigma={sigma0:.4f}):")
    print(f"  P({lo:.0f} <= Tmax < {hi:.0f}) = {p_bracket:.6f}")
    print("  (Compare to market normalized_ask + fee bar before treating as tradable — "
          "Hard Rule #3.)")
