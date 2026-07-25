#!/usr/bin/env python3
"""q42_funding_estimate_path_inference.py — Q42 part-1 residual: is the FINALIZED
Kalshi perp funding print a deterministic clamp/threshold function of Kalshi's own
published forward `funding_estimate` path?  (READ-ONLY, OFFLINE, NO NETWORK)

VERDICT (corrected 2026-07-24 after an independent verifier REFUTED the first pass):
**H1 is UNDECIDABLE at current tape density** — this tape cannot decide it in either
direction. The first pass called H1 FALSIFIED off a class overlap in |g_last|; the
verifier showed that overlap is MONOTONE IN PATH DENSITY (it vanishes, and inverts into
a HARD GAP, once windows with >=8 samples or a last sample <=0.75h before close are
kept), so the overlap is a capture-STALENESS artifact, not evidence of nondeterminism.
The dense subsets do not establish H1 either (n=11 with ONE nonzero-finalized window;
post-hoc cuts). See `density_stratified_separation()` below — the stratification is now
a FIRST-CLASS OUTPUT of this script, not a footnote.

ROUND-2 CORRECTION (2026-07-24, a SECOND independent verifier — verdict UNCHANGED, but
four things in round 1 were wrong or unshipped):
  * `gap_is_monotone_in_density` is a TAUTOLOGY for nested subsets (min can only rise,
    max can only fall) — round 1's docstring claimed the opposite. It carries ZERO
    information; `random_subset_hard_gap_rate()` is the replacement statistic that does
    (P(hard gap | random 11-of-42) ~ 0.205, | random 14-of-42 ~ 0.104 — so neither dense
    cut beats an arbitrary same-size cut).
  * the leave-one-out claim was QUOTED in the finding but had no shipped code —
    `leave_one_out_gap_scan()` now performs all 67 drops (7 discriminating tickers + 18
    discriminating funding_times + 42 windows; round 1's finding mis-decomposed 67 as
    "13 + 22 + 42", which sums to 77).
  * the failures-vs-successes contrast is supported on LEAD (one-sided permutation
    p ~ 0.0011) but NOT on SAMPLE COUNT (p ~ 0.283) — round 1 headlined both.
  * every p read off these strata is post-hoc over >= 9 searched cuts; `bonferroni()`
    makes the correction explicit (0.0110 x 9 = 0.0989, 0.0909 x 9 = 0.818).

The DENSITY-INDEPENDENT result stands untouched and is the honest headline:
**Kalshi's published forward estimate is ITSELF +/-1bp clamped** (1,274 samples, 93.49%
exactly zero, min |nonzero| 1.0026e-04, ZERO nonzeros in the open interval (0, 1e-4)) —
the regressor is PRE-CLAMPED, so sub-band information is destroyed at the source and the
FORMULA question may be structurally unanswerable from the `funding_estimate` endpoint at
ANY capture density.

LOOP-QUEUE.md Q42, part-1 residual. Part 1 (`scripts/q42_funding_clamp_probe.py`,
`findings/2026-07-17-q42-funding-clamp-characterization.md`) established a GENUINE
+/-1 basis-point (1e-4) dead-band clamp on the FINALIZED 8h funding prints. The open
thread is the FORMULA.

H1 (the hypothesis under test): there exists a summary statistic g(estimate_path) and
a threshold theta such that

      finalized == 0   iff   |g(estimate_path)| < theta
      finalized ~= g                                    on the non-clamped branch.

Note that H1 is EXISTENTIALLY QUANTIFIED over theta. Accuracy at part 1's borrowed 1bp
constant (`mis_1bp`) therefore tests "part 1's untuned constant transfers to the estimate
path", NOT H1 itself. H1's own quantity is the HARD-GAP test. The two are reported
separately and must not be conflated (the first pass headlined `mis_1bp = 10/42` as if it
bore on H1).

Candidate g's tested (all computed from the venue-published forward estimates only):
  (a) g_last          — LAST estimate strictly before funding_time
  (b) g_mean          — simple (unweighted) mean of the path
  (c) g_twap          — time-weighted mean: piecewise-constant forward-fill, each
                        sample holding from its own computed_time to the next
                        sample's computed_time (last sample holds to funding_time)
  (d) g_maxabs        — the estimate with the largest |.| on the path
  (e) g_last_nonzero  — LAST NONZERO estimate (labeled diagnostic; many paths carry
                        trailing exact-zeros because the ESTIMATE is itself clamped)

THIS IS NOT A P&L VERDICT. There is no fill price anywhere in this file, no fee math,
no bootstrap CI, no registry change. Every funding number — estimate and finalized
print alike — is `broker_truth` (venue-computed) and is NEVER a fillable price.

SCHEMA TRAP THIS FILE EXISTS TO AVOID (the research-lead hit it):
`record_type == "funding_rates"` is a NESTED ENVELOPE (`mode`, `n_prints`, `prints[]`),
NOT a flat row. Its per-print `market_ticker` / `funding_time` / `funding_rate` live
inside `prints[]`. A naive TOP-LEVEL `(ticker, funding_time)` join against these records
silently returns ~ZERO joined rows instead of erroring. `naive_toplevel_print_index()`
below reproduces the trap on purpose so a test can pin it at 0 and it cannot silently
return. Per lesson L137 we read BOTH `mode` values (`backfill` AND `recent`) and dedupe
on `(market_ticker, funding_time)` — reading only `backfill` is the exact L137 bug.
Non-funding `record_type`s (`markets`, `orderbook`) are filtered out (L96-class
conflation guard).

All ISO timestamps go through `core.timeutil.parse_iso_utc` (L136/L138 — Python 3.9's
`datetime.fromisoformat` rejects bare-'Z' and short-fraction timestamps; this file makes
no raw `fromisoformat` call).

CLUSTERING (L6): the 286 joined windows are NOT 286 independent observations — they are
13 tickers x 22 funding_times. The naive Fisher 2x2 p treats them as independent and is
therefore PSEUDO-REPLICATED. `cluster_permutation_p()` below recomputes the same
association with labels permuted WITHIN ticker (and, separately, within funding_time).
Both p-values are reported; the naive one is never quoted alone.

Run:
    python3 scripts/q42_funding_estimate_path_inference.py
    python3 scripts/q42_funding_estimate_path_inference.py --json-out /tmp/q42pathinf.json
    python3 scripts/q42_funding_estimate_path_inference.py --n-perm 20000   # faster
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import random
import statistics
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.stats import MIN_MEMBERS, safe_pstdev  # noqa: E402  (Hard Rule #2 — no bare pstdev)
from core.timeutil import parse_iso_utc  # noqa: E402

DEFAULT_TAPE_GLOB = "tape/perp_tape/dt=*.jsonl"

# Every funding number in this family is venue-computed, never a fill.
PRICE_SOURCE_TAG = "broker_truth"

# Part 1's established finalized-print dead band (+/-1 basis point).
DEAD_BAND = 1e-4

# Capture-density advisory floor for the perp_tape family (captures/day). The family's
# healthy rate is ~30/day; below this a per-window estimate PATH is too coarse to be a
# path at all. Advisory only — reported, never used to silently drop data.
DENSITY_ADVISORY_FLOOR_PER_DAY = 10.0

# Density strata for the stratified separation table (the correction's load-bearing
# output). Windows are kept if `n_samples >= k` / if the LAST sample landed within
# `lead` hours of funding_time. These are POST-HOC cuts — reported as a confound
# diagnostic, never as a tuned result.
MIN_SAMPLE_STRATA: Tuple[int, ...] = (1, 2, 3, 4, 5, 8)
MAX_LEAD_STRATA_HOURS: Tuple[float, ...] = (0.75, 1.0, 2.0)

# Cluster-robust permutation defaults (L6). Seeded => deterministic and test-pinnable.
N_PERMUTATIONS = 200_000
PERMUTATION_SEED = 20260724

# Draws for the matched-cardinality random-subset baseline (post-verifier round 2): how
# often does an ARBITRARY subset of the same size show a hard gap? Seeded.
N_RANDOM_SUBSET_DRAWS = 20_000

# POST-HOC SEARCH SIZE (round 2): the strata above are a searched family. The number of
# cuts examined is len(MIN_SAMPLE_STRATA) + len(MAX_LEAD_STRATA_HOURS) = 9, and any
# p-value quoted off a cut chosen after seeing the data must be multiplied by it before
# being read as significance. The effective family is LARGER than 9 — the specific values
# 8 and 0.75 were themselves picked after looking — so 9 is a FLOOR, not the true count.
N_POSTHOC_CUTS_SEARCHED = len(MIN_SAMPLE_STRATA) + len(MAX_LEAD_STRATA_HOURS)


def bonferroni(p: Optional[float], n_cuts: int = N_POSTHOC_CUTS_SEARCHED) -> Optional[float]:
    """`min(1, p * n_cuts)` — the multiplicity correction for a p-value read off one of
    `n_cuts` post-hoc strata. On the committed tape: lead<=0.75h 0.010989 * 9 = 0.0989 and
    n>=8 0.090909 * 9 = 0.818, i.e. NEITHER dense cut is significant at 0.05 once the
    search is accounted for. That STRENGTHENS the UNDECIDABLE verdict (these p's exist
    only to show H1 cannot be CONFIRMED here)."""
    if p is None:
        return None
    return min(1.0, p * n_cuts)

# The research-lead's pre-measured population. The loader must reproduce these EXACTLY
# before any inference is reported (same discipline part 2 used reproducing part 1).
EXPECTED_INTEGRITY: Dict[str, int] = {
    "n_estimate_groups": 299,
    "n_finalized_prints_dedup": 1746,
    "n_joined_windows": 286,
    "n_joined_tickers": 13,
    "n_joined_funding_times": 22,
    "n_joined_ge3_samples": 130,
    "n_discriminating": 42,
    "n_discriminating_finalized_zero": 28,
}


# --------------------------------------------------------------------------- #
# loading — injectable so tests are fully offline (path/glob OR a record list)
# --------------------------------------------------------------------------- #
def load_records(source: Any) -> List[Dict[str, Any]]:
    """Flat list of JSONL records from `source`: an already-parsed list/tuple of dicts
    (returned as-is), or a str/Path naming one .jsonl file or a glob. Pure, read-only,
    no network. A pattern matching nothing yields []."""
    if isinstance(source, (list, tuple)):
        return list(source)
    pattern = str(source)
    paths = sorted(glob.glob(pattern)) if any(c in pattern for c in "*?[") else [pattern]
    records: List[Dict[str, Any]] = []
    for p in paths:
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    return records


def collect_funding_estimates(records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Every `record_type == "funding_estimate"` row (a FLAT per-ticker row).

    The rate field is `funding_rate_estimate` (NOT `funding_estimate`, NOT
    `funding_rate`). Rows missing ticker / next_funding_time / computed_time / the
    estimate are DROPPED and counted by the caller — never defaulted to 0.0, because a
    missing estimate is not a zero estimate (that conflation is what the whole dead-band
    question turns on).

    Non-funding_estimate record_types (`funding_rates`, `markets`, `orderbook`) are
    filtered out here — an L96-class family-conflation guard.
    """
    out: List[Dict[str, Any]] = []
    for r in records:
        if r.get("record_type") != "funding_estimate":
            continue
        ticker = r.get("ticker")
        nft = r.get("next_funding_time")
        ct = r.get("computed_time") or r.get("captured_at")
        est = r.get("funding_rate_estimate")
        if not ticker or not nft or not ct or est is None:
            continue
        out.append({
            "ticker": ticker,
            "next_funding_time": nft,
            "funding_rate_estimate": float(est),
            "computed_time": ct,
            "mark_price": r.get("mark_price"),
            "captured_at": r.get("captured_at"),
            "capture_id": r.get("capture_id"),
            "price_source_tag": r.get("price_source_tag") or PRICE_SOURCE_TAG,
        })
    return out


def collect_finalized_prints(records: Sequence[Dict[str, Any]]
                             ) -> Tuple[Dict[Tuple[str, str], Dict[str, Any]], Dict[str, Any]]:
    """FLATTEN the nested `prints[]` out of every `funding_rates` envelope, BOTH modes,
    deduped on `(market_ticker, funding_time)` (first occurrence wins).

    Returns (index, meta). L137: reading only `mode == "backfill"` silently drops the
    ongoing `recent`-mode captures — that is the documented bug, so both modes are read.
    """
    index: Dict[Tuple[str, str], Dict[str, Any]] = {}
    modes: Dict[str, int] = {}
    n_envelopes = 0
    n_prints_read = 0
    n_dupes = 0
    tags: set = set()
    for r in records:
        if r.get("record_type") != "funding_rates":
            continue
        n_envelopes += 1
        mode = r.get("mode")
        modes[str(mode)] = modes.get(str(mode), 0) + 1
        tags.add(r.get("price_source_tag"))
        for pr in (r.get("prints") or []):
            mt = pr.get("market_ticker")
            ft = pr.get("funding_time")
            if not mt or not ft:
                continue
            n_prints_read += 1
            key = (mt, ft)
            if key in index:
                n_dupes += 1
                continue
            index[key] = {
                "market_ticker": mt,
                "funding_time": ft,
                "funding_rate": pr.get("funding_rate"),
                "mark_price": pr.get("mark_price"),
                "mode": mode,
            }
    meta = {
        "n_envelopes": n_envelopes,
        "modes_seen": dict(sorted(modes.items())),
        "n_prints_read": n_prints_read,
        "n_prints_dedup": len(index),
        "n_dupes_dropped": n_dupes,
        "source_tags_seen": sorted(t for t in tags if t is not None),
    }
    return index, meta


def naive_toplevel_print_index(records: Sequence[Dict[str, Any]]
                               ) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """THE TRAP, reproduced deliberately so a regression test can pin it at 0.

    Keys `funding_rates` records by their TOP-LEVEL `(ticker, funding_time)` — fields
    that do not exist at the envelope level (they live inside `prints[]`). This returns
    an EMPTY index on real tape: a join built on it silently yields ~zero rows instead
    of raising. Never use it for analysis.
    """
    index: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for r in records:
        if r.get("record_type") != "funding_rates":
            continue
        mt = r.get("ticker")
        ft = r.get("funding_time")
        if not mt or not ft:
            continue
        index[(mt, ft)] = r
    return index


# --------------------------------------------------------------------------- #
# window construction
# --------------------------------------------------------------------------- #
@dataclass
class Window:
    """One (ticker, funding_time) 8h funding window: the published forward estimate
    path plus the finalized print that closed it. All values `broker_truth`."""
    ticker: str
    funding_time: str
    funding_time_dt: datetime
    # (computed_time_dt, estimate) sorted ascending by computed_time, strictly pre-close
    path: List[Tuple[datetime, float]] = field(default_factory=list)
    finalized: float = 0.0
    n_dropped_non_pre_close: int = 0

    @property
    def n_samples(self) -> int:
        return len(self.path)

    @property
    def values(self) -> List[float]:
        return [v for _, v in self.path]

    @property
    def last_lead_hours(self) -> Optional[float]:
        if not self.path:
            return None
        return (self.funding_time_dt - self.path[-1][0]).total_seconds() / 3600.0

    @property
    def first_lead_hours(self) -> Optional[float]:
        if not self.path:
            return None
        return (self.funding_time_dt - self.path[0][0]).total_seconds() / 3600.0

    @property
    def has_nonzero_estimate(self) -> bool:
        return any(v != 0.0 for v in self.values)

    @property
    def finalized_is_zero(self) -> bool:
        return self.finalized == 0.0


def group_estimates(estimates: Sequence[Dict[str, Any]]
                    ) -> Dict[Tuple[str, str], List[Dict[str, Any]]]:
    """Group estimate rows on `(ticker, next_funding_time)` — the estimate-path key."""
    groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for e in estimates:
        groups.setdefault((e["ticker"], e["next_funding_time"]), []).append(e)
    return groups


def build_windows(est_groups: Dict[Tuple[str, str], List[Dict[str, Any]]],
                  print_index: Dict[Tuple[str, str], Dict[str, Any]]
                  ) -> Tuple[List[Window], Dict[str, Any]]:
    """Inner-join estimate groups against finalized prints on `(ticker, funding_time)`.

    A group with no finalized print is EXCLUDED and counted (the window has not settled
    in the committed tape yet) — never imputed. A print whose `funding_rate` is None is
    also excluded: a missing rate is not a zero rate.
    """
    windows: List[Window] = []
    n_no_print = 0
    n_none_rate = 0
    n_dropped_samples = 0
    for key, rows in sorted(est_groups.items()):
        pr = print_index.get(key)
        if pr is None:
            n_no_print += 1
            continue
        rate = pr.get("funding_rate")
        if rate is None:
            n_none_rate += 1
            continue
        ft_dt = parse_iso_utc(key[1])
        path: List[Tuple[datetime, float]] = []
        dropped = 0
        for r in rows:
            ct = parse_iso_utc(r["computed_time"])
            if ct >= ft_dt:  # strictly before funding_time, by construction of g_last
                dropped += 1
                continue
            path.append((ct, float(r["funding_rate_estimate"])))
        path.sort(key=lambda t: t[0])
        n_dropped_samples += dropped
        if not path:
            continue
        windows.append(Window(ticker=key[0], funding_time=key[1], funding_time_dt=ft_dt,
                              path=path, finalized=float(rate),
                              n_dropped_non_pre_close=dropped))
    meta = {
        "n_estimate_groups": len(est_groups),
        "n_groups_without_print": n_no_print,
        "n_groups_print_rate_none": n_none_rate,
        "n_samples_dropped_not_pre_close": n_dropped_samples,
        "n_windows": len(windows),
    }
    return windows, meta


# --------------------------------------------------------------------------- #
# candidate summary statistics g(estimate_path)
# --------------------------------------------------------------------------- #
def g_last(w: Window) -> Optional[float]:
    """(a) LAST estimate strictly before funding_time."""
    return w.values[-1] if w.path else None


def g_mean(w: Window) -> Optional[float]:
    """(b) simple unweighted mean of the path."""
    return statistics.fmean(w.values) if w.path else None


def g_twap(w: Window) -> Optional[float]:
    """(c) time-weighted mean, piecewise-constant forward-fill.

    Sample i holds from its own computed_time until sample i+1's computed_time; the last
    sample holds until funding_time. Weights are those durations. Degenerate case (all
    weights zero — identical timestamps) falls back to the simple mean rather than
    dividing by zero.
    """
    if not w.path:
        return None
    times = [t for t, _ in w.path] + [w.funding_time_dt]
    weights = [(times[i + 1] - times[i]).total_seconds() for i in range(len(w.path))]
    total = sum(weights)
    if total <= 0:
        return statistics.fmean(w.values)
    return sum(v * wt for (_, v), wt in zip(w.path, weights)) / total


def g_maxabs(w: Window) -> Optional[float]:
    """(d) the estimate with the largest |.| on the path (ties -> first)."""
    if not w.path:
        return None
    return max(w.values, key=lambda v: (abs(v),))


def g_last_nonzero(w: Window) -> Optional[float]:
    """(e) LAST NONZERO estimate; 0.0 if the whole path is zero (labeled diagnostic).

    Motivated by the fact — measured below — that the PUBLISHED ESTIMATE is itself
    dead-band clamped, so trailing exact-zeros on a path may be clamped observations
    rather than genuine zero-funding readings.
    """
    if not w.path:
        return None
    for v in reversed(w.values):
        if v != 0.0:
            return v
    return 0.0


CANDIDATE_GS: Dict[str, Callable[[Window], Optional[float]]] = {
    "g_last": g_last,
    "g_mean": g_mean,
    "g_twap": g_twap,
    "g_maxabs": g_maxabs,
    "g_last_nonzero": g_last_nonzero,
}


# --------------------------------------------------------------------------- #
# threshold / separation machinery
# --------------------------------------------------------------------------- #
def best_threshold(abs_g: Sequence[float], finalized_is_zero: Sequence[bool],
                   *, untuned_theta: float = DEAD_BAND) -> Dict[str, Any]:
    """Find theta minimizing misclassification of the rule `predict finalized==0 iff
    |g| < theta`, and report whether a HARD GAP exists.

    Hard gap (part 1's decisive evidence shape): a nonzero-width interval of theta
    containing NO observation on the wrong side, i.e.

        max(|g| over finalized==0)  <  min(|g| over finalized!=0)

    Any theta strictly inside that interval classifies every observation correctly. If
    the two groups overlap there is no such theta at ANY threshold and the rule is
    falsified as a deterministic clamp regardless of tuning.

    Candidate thetas are the observed |g| values and their midpoints plus the extremes,
    so the exact optimum on this sample is reached (no grid resolution artifact).

    `untuned_theta` (default: part 1's own +/-1bp dead band) is scored alongside the
    tuned optimum. The tuned theta is fit on the same 42-window sample it is scored on
    — it is an IN-SAMPLE upper bound on the rule's accuracy, not an out-of-sample one —
    so the untuned figure is the honest comparison and both are reported.
    """
    n = len(abs_g)
    if n == 0 or len(finalized_is_zero) != n:
        # Full key set even on the empty branch: a density stratum CAN be empty, and a
        # caller iterating rows must not KeyError on the stratum that vanished.
        return {"n": n, "n_finalized_zero": 0, "n_finalized_nonzero": 0, "theta": None,
                "n_misclassified": None, "n_false_zero": None, "n_false_nonzero": None,
                "misclassification_rate": None, "untuned_theta": untuned_theta,
                "n_misclassified_untuned": None, "misclassification_rate_untuned": None,
                "max_absg_finalized_zero": None, "min_absg_finalized_nonzero": None,
                "gap_width": None, "hard_gap": None, "note": "empty or mismatched input"}
    zero_g = sorted(a for a, z in zip(abs_g, finalized_is_zero) if z)
    nonzero_g = sorted(a for a, z in zip(abs_g, finalized_is_zero) if not z)

    vals = sorted(set(abs_g))
    cands = [0.0]
    for i, v in enumerate(vals):
        cands.append(v)
        if i + 1 < len(vals):
            cands.append((v + vals[i + 1]) / 2.0)
    cands.append(vals[-1] * 2.0 + 1.0)

    best = None
    for th in sorted(set(cands)):
        fp = sum(1 for a, z in zip(abs_g, finalized_is_zero) if a < th and not z)   # said 0, wasn't
        fn = sum(1 for a, z in zip(abs_g, finalized_is_zero) if a >= th and z)      # said !=0, was 0
        tot = fp + fn
        if best is None or tot < best[0]:
            best = (tot, th, fp, fn)
    tot, th, fp, fn = best

    max_zero = max(zero_g) if zero_g else None
    min_nonzero = min(nonzero_g) if nonzero_g else None
    if max_zero is None or min_nonzero is None:
        hard_gap = None
        gap_width = None
    else:
        gap_width = min_nonzero - max_zero
        hard_gap = gap_width > 0.0

    ufp = sum(1 for a, z in zip(abs_g, finalized_is_zero) if a < untuned_theta and not z)
    ufn = sum(1 for a, z in zip(abs_g, finalized_is_zero) if a >= untuned_theta and z)

    return {
        "n": n,
        "n_finalized_zero": len(zero_g),
        "n_finalized_nonzero": len(nonzero_g),
        "theta": th,
        "n_misclassified": tot,
        "n_false_zero": fp,       # |g| < theta but finalized was NONZERO
        "n_false_nonzero": fn,    # |g| >= theta but finalized was ZERO
        "misclassification_rate": (tot / n) if n else None,
        "untuned_theta": untuned_theta,
        "n_misclassified_untuned": ufp + ufn,
        "misclassification_rate_untuned": ((ufp + ufn) / n) if n else None,
        "max_absg_finalized_zero": max_zero,
        "min_absg_finalized_nonzero": min_nonzero,
        "gap_width": gap_width,
        "hard_gap": hard_gap,
    }


# --------------------------------------------------------------------------- #
# DENSITY STRATIFICATION — the correction's load-bearing output
# --------------------------------------------------------------------------- #
def hard_gap_exact_permutation_p(n: int, n_nonzero: int) -> Optional[float]:
    """Exact one-sided p for an OBSERVED HARD GAP under random labeling.

    A hard gap means every finalized-NONZERO window out-ranks every finalized-ZERO window
    on |g|. Under the null (labels assigned at random to the n windows) exactly ONE of the
    C(n, k) label assignments produces that, so p = 1 / C(n, k).

    This is the honest counterweight to a hard gap appearing on a dense stratum: with
    n = 11 and k = 1, p = 1/11 = 0.0909 — VACUOUS. A hard gap is only as impressive as the
    number of nonzero-finalized windows it separates. Returns None if the counts are
    degenerate (k == 0 or k == n: nothing to separate).
    """
    if n <= 0 or n_nonzero <= 0 or n_nonzero >= n:
        return None
    return 1.0 / math.comb(n, n_nonzero)


def density_stratified_separation(windows: Sequence[Window],
                                  gfn: Callable[[Window], Optional[float]],
                                  *,
                                  untuned_theta: float = DEAD_BAND,
                                  min_sample_strata: Sequence[int] = MIN_SAMPLE_STRATA,
                                  max_lead_strata: Sequence[float] = MAX_LEAD_STRATA_HOURS,
                                  ) -> List[Dict[str, Any]]:
    """Re-run the separation / hard-gap test on progressively DENSER subsets of windows.

    WHY THIS EXISTS (the refutation the first pass missed): the pooled populations mix
    12-sample paths whose last estimate lands 30 minutes before close with 2-sample
    "paths" whose last estimate lands 5 HOURS before close. A stale last sample is a
    different quantity from a fresh one, so pooling them manufactures class overlap. If
    the gap is MONOTONE in density — negative when sparse windows are included, positive
    once they are excluded — then the overlap is a CAPTURE-STALENESS ARTIFACT and the
    pooled "no hard gap" result cannot falsify H1. It is exactly the same confound the
    identity-fit leg already measures as r(|residual|, lead) > 0; this function propagates
    it into the THRESHOLD leg, which is where it bites.

    Two independent stratifiers, because they are not the same cut:
      * `min_samples`  — path length (how much of the window was observed at all)
      * `max_lead_h`   — recency of the LAST sample (how close to close we ever looked)

    These are POST-HOC cuts on n = 42. A hard gap appearing in a dense stratum is a
    CONFOUND DIAGNOSTIC (it kills the pooled falsification), NOT evidence for H1 — a
    stratum with one nonzero-finalized window cannot separate anything. The row's
    `n_finalized_nonzero` is reported precisely so that vacuity is visible.
    """
    rows: List[Dict[str, Any]] = []

    def _row(kind: str, label: str, value: float, pop: Sequence[Window]) -> Dict[str, Any]:
        keep = [(gfn(w), w) for w in pop]
        keep = [(g, w) for g, w in keep if g is not None]
        sep = best_threshold([abs(g) for g, _ in keep],
                             [w.finalized_is_zero for _, w in keep],
                             untuned_theta=untuned_theta)
        samples = [w.n_samples for _, w in keep]
        leads = [w.last_lead_hours for _, w in keep if w.last_lead_hours is not None]
        sep.update({
            "stratifier": kind,
            "filter": label,
            "value": value,
            "median_samples": statistics.median(samples) if samples else None,
            "median_last_lead_hours": statistics.median(leads) if leads else None,
            # only meaningful when a hard gap actually exists (else None)
            "exact_p_if_hard_gap": (
                hard_gap_exact_permutation_p(sep["n"], sep["n_finalized_nonzero"])
                if sep.get("hard_gap") is True else None),
        })
        # ROUND-2 CORRECTION: these strata are a SEARCHED family (9 cuts declared in the
        # module constants). A p read off one of them without the multiplicity correction
        # overstates it; both are emitted so neither can be quoted bare.
        sep["exact_p_bonferroni_%d_cuts" % N_POSTHOC_CUTS_SEARCHED] = \
            bonferroni(sep["exact_p_if_hard_gap"])
        sep["n_posthoc_cuts_searched"] = N_POSTHOC_CUTS_SEARCHED
        return sep

    for k in min_sample_strata:
        rows.append(_row("min_samples", f"n>={k}", float(k),
                         [w for w in windows if w.n_samples >= k]))
    for lh in max_lead_strata:
        rows.append(_row("max_lead_hours", f"lead<={lh:g}h", float(lh),
                         [w for w in windows
                          if w.last_lead_hours is not None and w.last_lead_hours <= lh]))
    return rows


def gap_is_monotone_in_density(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Summarize a `density_stratified_separation()` table: does any dense stratum reach a
    hard gap, and (for the record only) is the gap monotone along the `min_samples` chain?

    *** `monotone_nondecreasing_in_density` IS A TAUTOLOGY — IT CARRIES ZERO INFORMATION.
    *** (2026-07-24 post-verifier round 2; the first correction pass asserted the OPPOSITE
    here — "a nested chain of subsets, so a monotone trend there is meaningful" — which is
    backwards.)  Write the statistic out:

        gap(S) = min{|g(w)| : w in S, fin != 0}  -  max{|g(w)| : w in S, fin == 0}

    For any nested S' subset of S the min over a SMALLER set can only RISE and the max
    over a smaller set can only FALL, so `gap(S') >= gap(S)` UNCONDITIONALLY, for any
    data whatsoever. The `min_samples` strata are exactly a nested chain
    (n>=1 ⊇ n>=2 ⊇ ... ⊇ n>=8), so `True` here is guaranteed by construction and is
    evidence of nothing. It is kept only because the first correction pass published it
    and removing it silently would hide that error. `monotone_is_tautological_for_nested_
    chains` is emitted alongside so no downstream reader can mistake it for a finding.

    `pooled_overlap_is_density_confounded` is therefore INERT in its `and mono` conjunct:
    since `mono` is True whenever the chain has >1 comparable row, the flag reduces to
    `bool(hard)`. It is left as-is for output compatibility; do not read the conjunct as
    a second, independent condition.

    THE STATISTIC THAT DOES CARRY INFORMATION is `random_subset_hard_gap_rate()` below —
    how often an ARBITRARY subset of the same cardinality shows a hard gap. On the
    committed tape that baseline is ~0.20 at n=11 and ~0.10 at n=14, i.e. neither dense
    cut's hard gap beats a same-size random cut.
    """
    ms = [r for r in rows if r["stratifier"] == "min_samples" and r.get("gap_width") is not None]
    ms_sorted = sorted(ms, key=lambda r: r["value"])
    gaps = [r["gap_width"] for r in ms_sorted]
    mono = all(b >= a - 1e-18 for a, b in zip(gaps, gaps[1:])) if len(gaps) > 1 else None
    hard = [r["filter"] for r in rows if r.get("hard_gap") is True]
    return {
        "min_samples_gap_sequence": [(r["filter"], r["gap_width"]) for r in ms_sorted],
        "monotone_nondecreasing_in_density": mono,
        # nested subsets => min can only rise, max can only fall => monotone ALWAYS.
        "monotone_is_tautological_for_nested_chains": True,
        "strata_with_hard_gap": hard,
        "n_strata_with_hard_gap": len(hard),
        # NOTE: the `and bool(mono)` conjunct is INERT (mono is tautologically True on a
        # nested chain); this flag is effectively `bool(hard)`.
        "pooled_overlap_is_density_confounded": bool(hard) and bool(mono),
        "density_confound_flag_is_effectively_bool_hard": True,
    }


# --------------------------------------------------------------------------- #
# INFLUENCE + MATCHED-SIZE BASELINE (2026-07-24 post-verifier ROUND 2)
#
# Round 1 of the correction QUOTED a leave-one-out result and a "gap is monotone in
# density" flag in the finding without either being re-runnable/informative from the
# shipped artifact:
#   * the leave-one-out numbers existed only in a throwaway session (CLAUDE.md's trust
#     default: no claim enters the KB without a re-runnable script) -> leave_one_out_gap_scan
#   * the monotonicity flag is a tautology (see above) -> random_subset_hard_gap_rate is
#     the replacement statistic that actually discriminates.
# --------------------------------------------------------------------------- #
def _gap_width(pop: Sequence[Window], gfn: Callable[[Window], Optional[float]]
               ) -> Optional[float]:
    """`min(|g| | fin != 0) - max(|g| | fin == 0)` over `pop`; None if either class is
    absent (nothing to separate, so a 'gap' is undefined rather than 0)."""
    zero: List[float] = []
    nonzero: List[float] = []
    for w in pop:
        g = gfn(w)
        if g is None:
            continue
        (zero if w.finalized_is_zero else nonzero).append(abs(g))
    if not zero or not nonzero:
        return None
    return min(nonzero) - max(zero)


def leave_one_out_gap_scan(windows: Sequence[Window],
                           gfn: Callable[[Window], Optional[float]]) -> Dict[str, Any]:
    """INFLUENCE CHECK: does the pooled 'no hard gap' result survive dropping any single
    ticker, any single funding_time, or any single window?

    Three drop families, all over the population as PASSED IN (the discriminating windows
    when called from `analyze()`):

      * one per DISCRIMINATING ticker       (on the committed tape: 7, not the full 13 —
                                             only 7 tickers contribute a discriminating
                                             window at all)
      * one per DISCRIMINATING funding_time (18, not the full 22, for the same reason)
      * one per individual window           (42)
                                            -> 7 + 18 + 42 = 67 drops

    Reported: the max/min gap over all drops and how many drops RESTORE a hard gap
    (gap > 0). Zero restorations means the pooled overlap is not an outlier artifact —
    which is the point: it is a DENSITY artifact instead, and an influence check alone
    would never have found that. (This is why round 1's leave-one-out "PASSES" line was
    never evidence FOR the pooled falsification.)

    Drops whose remaining population has only one class leave `gap = None` and are counted
    in `n_drops_gap_undefined` rather than being silently scored as a restoration.
    """
    pop = list(windows)
    tickers = sorted({w.ticker for w in pop})
    ftimes = sorted({w.funding_time for w in pop})
    drops: List[Dict[str, Any]] = []
    for t in tickers:
        drops.append({"kind": "ticker", "dropped": t,
                      "gap_width": _gap_width([w for w in pop if w.ticker != t], gfn)})
    for ft in ftimes:
        drops.append({"kind": "funding_time", "dropped": ft,
                      "gap_width": _gap_width([w for w in pop if w.funding_time != ft], gfn)})
    for i, w0 in enumerate(pop):
        drops.append({"kind": "window", "dropped": f"{w0.ticker}|{w0.funding_time}",
                      "gap_width": _gap_width([w for j, w in enumerate(pop) if j != i], gfn)})
    gaps = [d["gap_width"] for d in drops if d["gap_width"] is not None]
    restorers = [d for d in drops if d["gap_width"] is not None and d["gap_width"] > 0.0]
    argmax = max((d for d in drops if d["gap_width"] is not None),
                 key=lambda d: d["gap_width"], default=None)
    return {
        "n_windows": len(pop),
        "n_drops": len(drops),
        "n_tickers_dropped": len(tickers),
        "n_funding_times_dropped": len(ftimes),
        "n_windows_dropped": len(pop),
        "pooled_gap_width": _gap_width(pop, gfn),
        "max_gap_width_over_drops": max(gaps) if gaps else None,
        "min_gap_width_over_drops": min(gaps) if gaps else None,
        "n_drops_restoring_hard_gap": len(restorers),
        "n_drops_gap_undefined": len(drops) - len(gaps),
        "restoring_drops": [{"kind": d["kind"], "dropped": d["dropped"],
                             "gap_width": d["gap_width"]} for d in restorers],
        "argmax_drop": argmax,
    }


def random_subset_hard_gap_rate(windows: Sequence[Window],
                                gfn: Callable[[Window], Optional[float]],
                                *, size: int, n_draws: int = 20_000,
                                seed: int = PERMUTATION_SEED) -> Dict[str, Any]:
    """MATCHED-CARDINALITY BASELINE: how often does an ARBITRARY subset of `size` windows,
    drawn uniformly from the same population, show a hard gap?

    This is the statistic `gap_is_monotone_in_density` only looked like. A hard gap on a
    dense stratum of 11 windows is only interesting if 11 windows drawn at RANDOM rarely
    produce one. On the committed tape they produce one ~20% of the time at size 11 and
    ~10% at size 14 — so neither post-hoc dense cut beats an arbitrary same-size cut, and
    the "gap crosses zero at n>=8" observation is not itself evidence.

    Seeded and therefore reproducible; `size` is passed by the caller from the OBSERVED
    hard-gap strata (never hardcoded). Draws whose subset lands in a single class leave
    the gap undefined and are counted separately, never scored as a hard gap.
    """
    pairs = [(abs(g), w.finalized_is_zero)
             for g, w in ((gfn(w), w) for w in windows) if g is not None]
    if size <= 0 or size > len(pairs) or n_draws <= 0:
        return {"size": size, "n_draws": n_draws, "seed": seed, "n_population": len(pairs),
                "p_hard_gap": None, "note": "size out of range for population"}
    rng = random.Random(seed)
    hits = 0
    undefined = 0
    for _ in range(n_draws):
        sub = rng.sample(pairs, size)
        zero = [a for a, iz in sub if iz]
        nonzero = [a for a, iz in sub if not iz]
        if not zero or not nonzero:
            undefined += 1
            continue
        if min(nonzero) - max(zero) > 0.0:
            hits += 1
    return {
        "size": size,
        "n_draws": n_draws,
        "seed": seed,
        "n_population": len(pairs),
        "n_hard_gap": hits,
        "n_single_class_draws": undefined,
        "p_hard_gap": hits / n_draws,
    }


def permutation_mean_diff_p(a: Sequence[float], b: Sequence[float], *,
                            n_perm: int = N_PERMUTATIONS, seed: int = PERMUTATION_SEED
                            ) -> Dict[str, Any]:
    """Label-permutation test for `mean(a) - mean(b)` (a two-sample difference of means).

    Used for the failures-vs-successes contrast: are the rule's failures genuinely staler
    (last-sample LEAD) and/or genuinely sparser (SAMPLE COUNT) than its successes? Round 1
    of the correction headlined both halves as if both were supported; on the committed
    tape only the LEAD half is (one-sided p ~ 0.0011 vs ~0.283 for the sample count).

    Both the one-sided p (in the OBSERVED direction — declared post-hoc, so it is the
    weaker of the two readings) and the two-sided p are returned; quote whichever, but
    say which. Add-one estimator, so p is never 0 and its floor is 1/(n_perm+1).

    L33 does not apply: this is a label-permutation null test, not a bootstrap CI and not
    an edge statistic; `core.bootstrap` has no permutation helper to reuse.

    Implementation note: `mean(a) - mean(b)` is a strictly increasing function of
    `sum(a)` at fixed total, so each draw only needs one `sample()` + `sum()`.
    """
    na, nb = len(a), len(b)
    if na == 0 or nb == 0:
        return {"n_a": na, "n_b": nb, "observed_diff": None, "p_one_sided": None,
                "p_two_sided": None, "note": "empty group"}
    pool = [float(v) for v in a] + [float(v) for v in b]
    total = sum(pool)
    obs = statistics.fmean(a) - statistics.fmean(b)
    rng = random.Random(seed)
    tol = 1e-12
    ge_dir = 0
    ge_abs = 0
    for _ in range(n_perm):
        sa = sum(rng.sample(pool, na))
        d = sa / na - (total - sa) / nb
        if (d >= obs - tol) if obs >= 0 else (d <= obs + tol):
            ge_dir += 1
        if abs(d) >= abs(obs) - tol:
            ge_abs += 1
    return {
        "n_a": na,
        "n_b": nb,
        "mean_a": statistics.fmean(a),
        "mean_b": statistics.fmean(b),
        "observed_diff": obs,
        "n_perm": n_perm,
        "seed": seed,
        "p_one_sided": (ge_dir + 1) / (n_perm + 1),
        "p_two_sided": (ge_abs + 1) / (n_perm + 1),
        "mc_resolution": 1.0 / (n_perm + 1),
    }


def failure_density_permutation(windows: Sequence[Window],
                                gfn: Callable[[Window], Optional[float]],
                                *, theta: float = DEAD_BAND,
                                n_perm: int = N_PERMUTATIONS,
                                seed: int = PERMUTATION_SEED) -> Dict[str, Any]:
    """Permutation p's for the failures-vs-successes density contrast, on BOTH axes,
    reported SEPARATELY because they do NOT agree on this tape:

      * `last_lead_hours` — failures' last sample is materially staler (SUPPORTED)
      * `n_samples`       — failures are nominally sparser, but not significantly so
                            (NOT SUPPORTED; the 'median 2.0 samples' line round 1
                            headlined beside the lead figure is a descriptive cut only)
    """
    wrong: List[Window] = []
    right: List[Window] = []
    for w in windows:
        g = gfn(w)
        if g is None:
            continue
        (right if ((abs(g) < theta) == w.finalized_is_zero) else wrong).append(w)
    lead_w = [w.last_lead_hours for w in wrong if w.last_lead_hours is not None]
    lead_r = [w.last_lead_hours for w in right if w.last_lead_hours is not None]
    return {
        "theta": theta,
        "n_failures": len(wrong),
        "n_successes": len(right),
        "last_lead_hours": permutation_mean_diff_p(lead_w, lead_r, n_perm=n_perm, seed=seed),
        "n_samples": permutation_mean_diff_p([float(w.n_samples) for w in wrong],
                                             [float(w.n_samples) for w in right],
                                             n_perm=n_perm, seed=seed),
    }


def misclassification_density_contrast(windows: Sequence[Window],
                                       gfn: Callable[[Window], Optional[float]],
                                       *, theta: float = DEAD_BAND) -> Dict[str, Any]:
    """Are the rule's FAILURES the sparse windows? Contrast path density between the
    windows the `|g| < theta` rule gets wrong and the ones it gets right.

    If failures are systematically sparser / staler than successes, the misclassification
    count is measuring capture cadence, not the venue's formula."""
    wrong: List[Window] = []
    right: List[Window] = []
    for w in windows:
        g = gfn(w)
        if g is None:
            continue
        (right if ((abs(g) < theta) == w.finalized_is_zero) else wrong).append(w)

    def _block(pop: Sequence[Window]) -> Dict[str, Any]:
        samples = [w.n_samples for w in pop]
        leads = [w.last_lead_hours for w in pop if w.last_lead_hours is not None]
        return {
            "n": len(pop),
            "median_samples": statistics.median(samples) if samples else None,
            "mean_samples": statistics.fmean(samples) if samples else None,
            "n_with_2_or_fewer_samples": sum(1 for s in samples if s <= 2),
            "median_last_lead_hours": statistics.median(leads) if leads else None,
            "max_last_lead_hours": max(leads) if leads else None,
        }

    return {
        "theta": theta,
        "misclassified": _block(wrong),
        "correct": _block(right),
        "misclassified_detail": [
            {"ticker": w.ticker, "funding_time": w.funding_time, "n_samples": w.n_samples,
             "last_lead_hours": w.last_lead_hours, "g": gfn(w), "finalized": w.finalized}
            for w in sorted(wrong, key=lambda w: (w.ticker, w.funding_time))
        ],
    }


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    """Pearson r, or None when n < 4 or either series is constant (r undefined, not 0).

    Dispersion goes through `core.stats.safe_pstdev` — Hard Rule #2, no bare `pstdev` —
    which also supplies the n>=4 floor rather than reporting a confident-looking r off
    three points.
    """
    n = len(xs)
    if n < MIN_MEMBERS or len(ys) != n:
        return None
    xsd, ysd = safe_pstdev(xs), safe_pstdev(ys)
    if xsd <= 0 or ysd <= 0:
        return None
    xm, ym = statistics.fmean(xs), statistics.fmean(ys)
    cov = sum((x - xm) * (y - ym) for x, y in zip(xs, ys)) / n
    return cov / (xsd * ysd)


def identity_fit(g_values: Sequence[float], finalized: Sequence[float],
                 lead_hours: Optional[Sequence[Optional[float]]] = None) -> Dict[str, Any]:
    """H1's second leg on the NON-CLAMPED branch: is finalized ~= g (identity)?

    Reports Pearson correlation, mean/median absolute residual, mean signed residual,
    sign agreement, and the residual scaled by the typical |finalized| — so a "correlated
    but badly-scaled" fit cannot masquerade as identity. n < 4 leaves the correlation
    None rather than reporting a degenerate value (Hard Rule #2's floor, via
    `core.stats.safe_pstdev`).

    RESIDUAL STRUCTURE (not just size): if `lead_hours` is supplied (how long before
    funding_time the path's last sample landed), the correlation of |residual| with lead
    time is reported. Under H1's identity leg the residual should be unstructured noise;
    a residual that grows with staleness is structure — the path is being read too early,
    not the formula being wrong.
    """
    n = len(g_values)
    if n == 0 or len(finalized) != n:
        return {"n": n, "note": "empty or mismatched input"}
    resid = [f - g for g, f in zip(g_values, finalized)]
    abs_resid = [abs(r) for r in resid]
    med_abs_fin = statistics.median([abs(f) for f in finalized])
    corr = _pearson(list(g_values), list(finalized))
    r_resid_lead = None
    n_lead = 0
    if lead_hours is not None and len(lead_hours) == n:
        pairs = [(lh, ar) for lh, ar in zip(lead_hours, abs_resid) if lh is not None]
        n_lead = len(pairs)
        r_resid_lead = _pearson([p[0] for p in pairs], [p[1] for p in pairs])
    n_sign_agree = sum(1 for g, f in zip(g_values, finalized)
                       if (g > 0 and f > 0) or (g < 0 and f < 0))
    return {
        "n": n,
        "pearson_r": corr,
        "r_absresidual_vs_last_sample_lead_hours": r_resid_lead,
        "n_with_lead": n_lead,
        "mean_abs_residual": statistics.fmean(abs_resid),
        "median_abs_residual": statistics.median(abs_resid),
        "mean_signed_residual": statistics.fmean(resid),
        "max_abs_residual": max(abs_resid),
        "median_abs_finalized": med_abs_fin,
        "mean_abs_residual_over_median_abs_finalized":
            (statistics.fmean(abs_resid) / med_abs_fin) if med_abs_fin else None,
        "n_sign_agree": n_sign_agree,
        "sign_agreement_fraction": n_sign_agree / n,
    }


# --------------------------------------------------------------------------- #
# exact independence test (analytic — NOT a bootstrap, NOT a resample loop)
# --------------------------------------------------------------------------- #
def fisher_exact_2x2(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact p for the 2x2 table [[a, b], [c, d]].

    Computed analytically from the hypergeometric distribution (`math.comb`) — there is
    NO resampling here, so L33's "never hand-roll a resample loop" does not apply; it
    also means the p-value is exact rather than Monte-Carlo. Used ONLY to falsify (or
    fail to falsify) the null "finalized is independent of the estimate path". It is
    not, and cannot be, an edge statistic.
    """
    n = a + b + c + d
    if n == 0:
        return 1.0
    row1, col1 = a + b, a + c

    def prob(x: int) -> float:
        return (math.comb(row1, x) * math.comb(n - row1, col1 - x)) / math.comb(n, col1)

    lo = max(0, col1 - (n - row1))
    hi = min(row1, col1)
    p_obs = prob(a)
    tol = 1e-12
    return min(1.0, sum(prob(x) for x in range(lo, hi + 1) if prob(x) <= p_obs + tol))


def cluster_permutation_p(strata: Sequence[Any], x: Sequence[bool], y: Sequence[bool],
                          *, n_perm: int = N_PERMUTATIONS, seed: int = PERMUTATION_SEED
                          ) -> Dict[str, Any]:
    """CLUSTER-ROBUST one-sided permutation p for the same 2x2 association (L6).

    The naive Fisher p above treats every window as an independent observation. They are
    not: 286 windows are 13 tickers x 22 funding_times, and a ticker whose funding regime
    is persistently nonzero contributes many correlated rows. That is L6's exact failure
    mode ("bootstrap the independent unit, never the row") applied to a p-value instead of
    a CI, and it inflates significance — here by roughly FIVE ORDERS OF MAGNITUDE.

    Fix: hold the cluster structure FIXED and permute the finalized labels only WITHIN
    each stratum. The statistic is the concordant count a = #{x AND y}; the reported p is
    the one-sided (1 + #{perm >= obs}) / (n_perm + 1) — an add-one estimator, so it is
    never 0 and its floor is the Monte-Carlo resolution 1/(n_perm+1).

    L33 does NOT apply: this is not a bootstrap CI and not an edge statistic — it is a
    label-permutation null test, and `core.bootstrap` has no permutation helper to reuse.
    It is seeded and therefore exactly reproducible; a DIFFERENT seed moves the estimate
    by the Monte-Carlo noise of a ~1e-5 tail (observed spread across seeds: ~2.5e-05 to
    ~4.0e-05 at n_perm = 200,000), which is why `mc_resolution` is reported alongside.

    Sampling shortcut (exactly equivalent, ~15x faster than shuffling the full label
    vector): within a stratum of size n_s with k_s x-true rows and m_s y-true labels, the
    permuted overlap is hypergeometric — draw which m_s of the n_s positions carry the
    label and count how many land in the k_s x-true positions. Strata with k_s == 0 or
    m_s == 0 contribute 0 deterministically; strata with k_s == n_s or m_s == n_s
    contribute a constant. Those are folded into `fixed` rather than resampled.
    """
    n = len(x)
    if n == 0 or len(y) != n or len(strata) != n:
        return {"n": n, "p_one_sided": None, "note": "empty or mismatched input"}
    groups: Dict[Any, List[int]] = {}
    for i, s in enumerate(strata):
        groups.setdefault(s, []).append(i)
    obs = sum(1 for xi, yi in zip(x, y) if xi and yi)

    cells: List[Tuple[int, int, int]] = []
    fixed = 0
    for _s, ids in sorted(groups.items(), key=lambda kv: str(kv[0])):
        n_s = len(ids)
        k_s = sum(1 for i in ids if x[i])
        m_s = sum(1 for i in ids if y[i])
        if k_s == 0 or m_s == 0:
            continue
        if k_s == n_s:
            fixed += m_s
            continue
        if m_s == n_s:
            fixed += k_s
            continue
        cells.append((n_s, k_s, m_s))

    rng = random.Random(seed)
    ge = 0
    for _ in range(n_perm):
        stat = fixed
        for n_s, k_s, m_s in cells:
            stat += sum(1 for pos in rng.sample(range(n_s), m_s) if pos < k_s)
        if stat >= obs:
            ge += 1
    return {
        "n": n,
        "n_clusters": len(groups),
        "n_variable_clusters": len(cells),
        "observed_concordant": obs,
        "n_perm": n_perm,
        "seed": seed,
        "n_perm_ge_observed": ge,
        "p_one_sided": (ge + 1) / (n_perm + 1),
        "mc_resolution": 1.0 / (n_perm + 1),
    }


def per_cluster_tables(windows: Sequence[Window], key: Callable[[Window], str]
                       ) -> List[Dict[str, Any]]:
    """Per-cluster 2x2 tables + exact Fisher p — WHERE the pooled association lives.

    A pooled p carried by 3 of 13 clusters is a different (weaker) claim than the same p
    reproduced across clusters. Reported so a reader can see the concentration."""
    by: Dict[str, List[Window]] = {}
    for w in windows:
        by.setdefault(key(w), []).append(w)
    rows: List[Dict[str, Any]] = []
    for k, pop in sorted(by.items()):
        a = sum(1 for w in pop if w.has_nonzero_estimate and not w.finalized_is_zero)
        b = sum(1 for w in pop if w.has_nonzero_estimate and w.finalized_is_zero)
        c = sum(1 for w in pop if not w.has_nonzero_estimate and not w.finalized_is_zero)
        d = sum(1 for w in pop if not w.has_nonzero_estimate and w.finalized_is_zero)
        rows.append({"cluster": k, "n": len(pop), "a": a, "b": b, "c": c, "d": d,
                     "n_discriminating": a + b,
                     "p_fisher_two_sided": fisher_exact_2x2(a, b, c, d)})
    return rows


# --------------------------------------------------------------------------- #
# descriptive characterizations
# --------------------------------------------------------------------------- #
def estimate_clamp_summary(estimates: Sequence[Dict[str, Any]],
                           dead_band: float = DEAD_BAND) -> Dict[str, Any]:
    """Does the PUBLISHED FORWARD ESTIMATE carry the same +/-1bp dead band part 1 found
    on the finalized prints? Same discriminator shape: exact-zero fraction, smallest
    nonzero magnitude, and the count of nonzeros inside the open interval (0, band)."""
    vals = [e["funding_rate_estimate"] for e in estimates]
    nz = [abs(v) for v in vals if v != 0.0]
    return {
        "n": len(vals),
        "n_zero": sum(1 for v in vals if v == 0.0),
        "zero_fraction": (sum(1 for v in vals if v == 0.0) / len(vals)) if vals else None,
        "n_nonzero": len(nz),
        "min_abs_nonzero": min(nz) if nz else None,
        "n_nonzero_inside_band": sum(1 for a in nz if a < dead_band),
        "dead_band": dead_band,
        "price_source_tag": PRICE_SOURCE_TAG,
    }


def density_summary(estimates: Sequence[Dict[str, Any]],
                    windows: Sequence[Window]) -> Dict[str, Any]:
    """Capture density (distinct capture_id per UTC day) + estimate samples per window.

    Density is the binding data-adequacy fact for this milestone: a "path" sampled 2-3
    times over an 8h window is not a path.
    """
    by_day: Dict[str, set] = {}
    for e in estimates:
        ts = e.get("captured_at") or e.get("computed_time")
        if not ts:
            continue
        day = parse_iso_utc(ts).date().isoformat()
        by_day.setdefault(day, set()).add(e.get("capture_id") or ts)
    per_day = {d: len(s) for d, s in sorted(by_day.items())}
    samples = [w.n_samples for w in windows]
    leads = [w.last_lead_hours for w in windows if w.last_lead_hours is not None]
    return {
        "captures_per_day": per_day,
        "n_days": len(per_day),
        "n_days_below_advisory_floor": sum(1 for v in per_day.values()
                                           if v < DENSITY_ADVISORY_FLOOR_PER_DAY),
        "advisory_floor_per_day": DENSITY_ADVISORY_FLOOR_PER_DAY,
        "median_samples_per_window": statistics.median(samples) if samples else None,
        "mean_samples_per_window": statistics.fmean(samples) if samples else None,
        "min_samples_per_window": min(samples) if samples else None,
        "max_samples_per_window": max(samples) if samples else None,
        "median_last_sample_lead_hours": statistics.median(leads) if leads else None,
        "max_last_sample_lead_hours": max(leads) if leads else None,
    }


def class_wide_falsifier(windows: Sequence[Window]) -> Dict[str, Any]:
    """The class-wide falsification check, run BEFORE any theta tuning.

    Every candidate g in CANDIDATE_GS returns exactly 0.0 on an all-zero estimate path.
    So if any all-zero-path window finalizes NONZERO while others finalize ZERO, then no
    threshold theta on ANY of these g's can be error-free — the whole candidate class is
    falsified independently of tuning. This is the determinism argument, not a fit.

    CORRECTION (2026-07-24, post-verifier) — READ `counterexamples_all_sparse` BEFORE
    reading `class_falsified`. An "all-zero path" observed ONCE, hours before close, is
    not an observation that the path WAS all-zero; it is an observation that we never
    looked again. On the committed tape every counterexample is a 1- or 2-sample window,
    so `class_falsified` here is CONFOUNDED WITH CAPTURE DENSITY and does NOT establish
    nondeterminism. `n_counterexamples_dense` (>=3 samples) is the only version of this
    argument that would carry; it is currently 0.
    """
    allzero = [w for w in windows if not w.has_nonzero_estimate]
    nonzero_fin = [w for w in allzero if not w.finalized_is_zero]
    dense_ce = [w for w in nonzero_fin if w.n_samples >= 3]
    return {
        "n_allzero_path_windows": len(allzero),
        "n_allzero_path_finalized_zero": len(allzero) - len(nonzero_fin),
        "n_allzero_path_finalized_nonzero": len(nonzero_fin),
        "class_falsified": len(nonzero_fin) > 0 and (len(allzero) - len(nonzero_fin)) > 0,
        "max_counterexample_samples": max((w.n_samples for w in nonzero_fin), default=None),
        "n_counterexamples_dense_ge3_samples": len(dense_ce),
        "counterexamples_all_sparse": bool(nonzero_fin) and not dense_ce,
        "counterexamples": [
            {"ticker": w.ticker, "funding_time": w.funding_time,
             "n_samples": w.n_samples, "last_lead_hours": w.last_lead_hours,
             "finalized": w.finalized}
            for w in nonzero_fin
        ],
    }


# --------------------------------------------------------------------------- #
# end-to-end analysis
# --------------------------------------------------------------------------- #
def analyze(records: Sequence[Dict[str, Any]], *, n_perm: int = N_PERMUTATIONS,
            seed: int = PERMUTATION_SEED,
            n_subset_draws: int = N_RANDOM_SUBSET_DRAWS) -> Dict[str, Any]:
    estimates = collect_funding_estimates(records)
    print_index, print_meta = collect_finalized_prints(records)
    est_groups = group_estimates(estimates)
    windows, win_meta = build_windows(est_groups, print_index)

    disc = [w for w in windows if w.has_nonzero_estimate]
    integrity = {
        "n_estimate_groups": len(est_groups),
        "n_finalized_prints_dedup": print_meta["n_prints_dedup"],
        "n_joined_windows": len(windows),
        "n_joined_tickers": len(set(w.ticker for w in windows)),
        "n_joined_funding_times": len(set(w.funding_time for w in windows)),
        "n_joined_ge3_samples": sum(1 for w in windows if w.n_samples >= 3),
        "n_discriminating": len(disc),
        "n_discriminating_finalized_zero": sum(1 for w in disc if w.finalized_is_zero),
    }
    integrity_ok = all(integrity.get(k) == v for k, v in EXPECTED_INTEGRITY.items())

    # populations: the full join, and the discriminating subset (>=1 nonzero estimate)
    populations = {"joined_all": list(windows), "discriminating": disc}

    per_g: Dict[str, Any] = {}
    for gname, gfn in CANDIDATE_GS.items():
        block: Dict[str, Any] = {}
        for pname, pop in populations.items():
            gv = [gfn(w) for w in pop]
            keep = [(g, w) for g, w in zip(gv, pop) if g is not None]
            gs = [g for g, _ in keep]
            ws = [w for _, w in keep]
            sep = best_threshold([abs(g) for g in gs], [w.finalized_is_zero for w in ws])
            branch = [(g, w) for g, w in keep if not w.finalized_is_zero]
            fit = identity_fit([g for g, _ in branch], [w.finalized for _, w in branch],
                               [w.last_lead_hours for _, w in branch])
            block[pname] = {"separation": sep, "identity_fit_nonclamped_branch": fit}
        # FIRST-CLASS OUTPUT (the 2026-07-24 correction): is the pooled overlap just a
        # capture-staleness artifact? Stratify the same test by path density.
        strat = density_stratified_separation(disc, gfn)
        block["density_stratified_discriminating"] = strat
        block["density_monotonicity"] = gap_is_monotone_in_density(strat)
        block["misclassification_density_contrast"] = \
            misclassification_density_contrast(disc, gfn)
        # ROUND-2 CORRECTION: the influence check the round-1 finding QUOTED but never
        # shipped, now a first-class output (67 drops on the committed tape).
        block["leave_one_out"] = leave_one_out_gap_scan(disc, gfn)
        # ROUND-2 CORRECTION: matched-cardinality random-subset baseline, sized from the
        # OBSERVED hard-gap strata (never hardcoded). Replaces the tautological
        # monotonicity flag as the statistic that actually discriminates.
        block["matched_size_random_subset_baseline"] = [
            random_subset_hard_gap_rate(disc, gfn, size=s, n_draws=n_subset_draws, seed=seed)
            for s in sorted({r["n"] for r in strat if r.get("hard_gap") is True})
        ]
        per_g[gname] = block

    # Failures-vs-successes density contrast, permutation-tested. Computed for g_last
    # only (the headline g) to keep runtime bounded; the two axes are reported SEPARATELY
    # because only the LEAD axis is supported.
    failure_density = failure_density_permutation(disc, g_last, n_perm=n_perm, seed=seed)

    # exact independence test on the full join: does having ANY nonzero estimate on the
    # path associate with a nonzero finalized print?
    a = sum(1 for w in disc if not w.finalized_is_zero)     # path nonzero & finalized nonzero
    b = sum(1 for w in disc if w.finalized_is_zero)         # path nonzero & finalized zero
    az = [w for w in windows if not w.has_nonzero_estimate]
    c = sum(1 for w in az if not w.finalized_is_zero)       # path all-zero & finalized nonzero
    d = sum(1 for w in az if w.finalized_is_zero)           # path all-zero & finalized zero
    xs = [w.has_nonzero_estimate for w in windows]
    ys = [not w.finalized_is_zero for w in windows]
    independence = {
        "table": {"path_nonzero_final_nonzero": a, "path_nonzero_final_zero": b,
                  "path_allzero_final_nonzero": c, "path_allzero_final_zero": d},
        "p_fisher_two_sided_NAIVE_pseudoreplicated": fisher_exact_2x2(a, b, c, d),
        # L6: the naive p above is NEVER quoted alone — these are the honest ones.
        "cluster_permutation_by_ticker": cluster_permutation_p(
            [w.ticker for w in windows], xs, ys, n_perm=n_perm, seed=seed),
        "cluster_permutation_by_funding_time": cluster_permutation_p(
            [w.funding_time for w in windows], xs, ys, n_perm=n_perm, seed=seed),
        "per_ticker_tables": per_cluster_tables(windows, lambda w: w.ticker),
        "rate_final_nonzero_given_path_nonzero": (a / (a + b)) if (a + b) else None,
        "rate_final_nonzero_given_path_allzero": (c / (c + d)) if (c + d) else None,
    }

    return {
        "price_source_tag": PRICE_SOURCE_TAG,
        "is_pnl_claim": False,
        "load": {
            "n_records": len(records),
            "n_estimate_rows": len(estimates),
            "finalized_prints": print_meta,
        },
        "window_build": win_meta,
        "integrity": {"observed": integrity, "expected": EXPECTED_INTEGRITY,
                      "reproduced": integrity_ok},
        "estimate_path_clamp": estimate_clamp_summary(estimates),
        "class_wide_falsifier": class_wide_falsifier(windows),
        "density": density_summary(estimates, windows),
        "failure_density_permutation_g_last": failure_density,
        "n_posthoc_cuts_searched": N_POSTHOC_CUTS_SEARCHED,
        "per_g": per_g,
        "independence": independence,
        "windows_detail": [
            {"ticker": w.ticker, "funding_time": w.funding_time, "n_samples": w.n_samples,
             "finalized": w.finalized, "path": [v for v in w.values],
             "last_lead_hours": w.last_lead_hours}
            for w in disc
        ],
    }


# --------------------------------------------------------------------------- #
# reporting
# --------------------------------------------------------------------------- #
def _e(v: Optional[float], nd: int = 4) -> str:
    return "None" if v is None else f"{v:.{nd}e}"


def _f(v: Optional[float], nd: int = 4) -> str:
    return "None" if v is None else f"{v:.{nd}f}"


def _print_report(rep: Dict[str, Any]) -> None:
    W = 104
    print("=" * W)
    print("Q42 part-1 residual — IS THE FINALIZED FUNDING PRINT A CLAMP OF THE PUBLISHED")
    print("ESTIMATE PATH?  (read-only, offline)   source_tag=%s   NOT a P&L claim"
          % rep["price_source_tag"])
    print("VERDICT: H1 is UNDECIDABLE at current tape density (corrected 2026-07-24 after")
    print("an independent verifier refuted the first pass's FALSIFIED call — see the")
    print("DENSITY-STRATIFIED block: the pooled class overlap inverts to a hard gap once")
    print("2-sample / multi-hour-stale windows are dropped, and a `g_last` computed off an")
    print("estimate published up to 4.99h before close is not a measurement of 'the last")
    print("estimate before funding_time' at all. That is a MEASUREMENT-VALIDITY objection,")
    print("not an inference from the strata — the strata themselves prove little, since a")
    print("random same-size subset shows a hard gap ~20% of the time.)")
    print("=" * W)

    ig = rep["integrity"]
    print("INTEGRITY GATE (must reproduce the pre-measured population exactly):")
    for k, exp in ig["expected"].items():
        obs = ig["observed"].get(k)
        print(f"  {k:<36} observed={obs:<8} expected={exp:<8} "
              f"{'OK' if obs == exp else '*** MISMATCH ***'}")
    print(f"  -> integrity reproduced: {ig['reproduced']}")
    if not ig["reproduced"]:
        print("  *** POPULATION MISMATCH — do NOT read the inference below as the scoped "
              "milestone. ***")
    ld = rep["load"]
    fp = ld["finalized_prints"]
    print(f"  records={ld['n_records']}  estimate_rows={ld['n_estimate_rows']}  "
          f"funding_rates_envelopes={fp['n_envelopes']}  modes={fp['modes_seen']}  "
          f"prints_read={fp['n_prints_read']}  dedup={fp['n_prints_dedup']}  "
          f"dupes_dropped={fp['n_dupes_dropped']}  tags={fp['source_tags_seen']}")
    wb = rep["window_build"]
    print(f"  groups_without_print={wb['n_groups_without_print']}  "
          f"print_rate_none={wb['n_groups_print_rate_none']}  "
          f"samples_dropped_not_pre_close={wb['n_samples_dropped_not_pre_close']}")
    print("-" * W)

    ec = rep["estimate_path_clamp"]
    print("HEADLINE RESULT (density-INDEPENDENT — survives the correction untouched):")
    print("IS THE PUBLISHED FORWARD ESTIMATE ITSELF CLAMPED? (broker_truth)")
    print(f"  estimate samples n={ec['n']}  exact-zero={ec['n_zero']} "
          f"(frac={_f(ec['zero_fraction'])})  nonzero={ec['n_nonzero']}")
    print(f"  min |nonzero estimate| = {_e(ec['min_abs_nonzero'])}   "
          f"nonzeros inside (0, {_e(ec['dead_band'],1)}) = {ec['n_nonzero_inside_band']}")
    if ec["n_nonzero_inside_band"] == 0 and ec["n_nonzero"] > 0:
        print("  -> the FORWARD ESTIMATE carries the SAME hard +/-1bp dead band part 1 found on")
        print("     the finalized prints: the regressor is pre-clamped, so sub-band information")
        print("     is destroyed AT THE SOURCE before any g can see it.")
    print("-" * W)

    cf = rep["class_wide_falsifier"]
    print("CLASS-WIDE FALSIFIER (run before any theta tuning — every candidate g returns 0")
    print("on an all-zero path, so an all-zero path with a NONZERO finalized print breaks")
    print("determinism for the WHOLE class at ANY theta):")
    print(f"  all-zero-estimate-path windows = {cf['n_allzero_path_windows']}  "
          f"-> finalized ZERO {cf['n_allzero_path_finalized_zero']}  "
          f"/ finalized NONZERO {cf['n_allzero_path_finalized_nonzero']}")
    for ce in cf["counterexamples"]:
        print(f"    counterexample: {ce['ticker']:<12} {ce['funding_time']}  "
              f"n_est={ce['n_samples']}  lead_h={_f(ce.get('last_lead_hours'),2)}  "
              f"finalized={_e(ce['finalized'])}")
    print(f"  -> raw class_falsified flag: {cf['class_falsified']}")
    print(f"  -> counterexamples with >=3 samples: {cf['n_counterexamples_dense_ge3_samples']}"
          f"   (max samples on any counterexample: {cf['max_counterexample_samples']})")
    if cf.get("counterexamples_all_sparse"):
        print("  *** DENSITY-CONFOUNDED: every counterexample is a 1-2-sample window. An")
        print("      'all-zero path' seen once, hours before close, is not evidence the path")
        print("      was all-zero — it is evidence we never looked again. This argument does")
        print("      NOT establish nondeterminism on this tape. ***")
    print("-" * W)

    print("PER-g SEPARATION (rule: predict finalized==0 iff |g| < theta).  'mis_tuned' uses the")
    print("IN-SAMPLE optimal theta (an upper bound on accuracy); 'mis_1bp' uses part 1's untuned")
    print("+/-1bp dead band.  NOTE: H1 is EXISTENTIAL over theta, so mis_1bp tests whether part")
    print("1's borrowed constant transfers — it is NOT a test of H1. H1's quantity is hard_gap.")
    for pname in ("joined_all", "discriminating"):
        print(f"  population = {pname}")
        print(f"    {'g':<16}{'n':>5}{'zeros':>7}{'nonz':>6}{'theta':>12}{'mis_tuned':>10}"
              f"{'rate':>8}{'mis_1bp':>9}{'maxG|fin=0':>13}{'minG|fin!=0':>13}{'gap':>12}  hard_gap")
        for gname in CANDIDATE_GS:
            s = rep["per_g"][gname][pname]["separation"]
            print(f"    {gname:<16}{s['n']:>5}{s['n_finalized_zero']:>7}"
                  f"{s['n_finalized_nonzero']:>6}{_e(s['theta'],3):>12}"
                  f"{s['n_misclassified']:>10}{_f(s['misclassification_rate'],3):>8}"
                  f"{s['n_misclassified_untuned']:>9}"
                  f"{_e(s['max_absg_finalized_zero'],3):>13}"
                  f"{_e(s['min_absg_finalized_nonzero'],3):>13}"
                  f"{_e(s['gap_width'],3):>12}  {s['hard_gap']}")
    print("-" * W)

    print("*** DENSITY-STRATIFIED SEPARATION (the 2026-07-24 correction's load-bearing output).")
    print("Same hard-gap test, run on progressively DENSER subsets of the 42 discriminating")
    print("windows. READ THE THREE DIAGNOSTICS UNDER EACH TABLE, NOT THE TABLE ALONE:")
    print("  * `monotone in density` is a TAUTOLOGY on a nested chain — ignore it;")
    print("  * the matched-size RANDOM-SUBSET baseline is what says whether a dense cut's")
    print("    hard gap beats an arbitrary cut of the same size (on this tape it does not);")
    print("  * `exact_p x N cuts` is the Bonferroni-corrected p over the SEARCHED family.")
    print("These are POST-HOC cuts: a hard gap here does NOT establish H1 (watch `nonz` — a")
    print("stratum with 1 nonzero-finalized window separates nothing).")
    for gname in CANDIDATE_GS:
        blk = rep["per_g"][gname]
        mono = blk["density_monotonicity"]
        print(f"  g = {gname}")
        print(f"    {'filter':<14}{'n':>5}{'zeros':>7}{'nonz':>6}{'medN':>6}{'medLead_h':>11}"
              f"{'mis_1bp':>9}{'mis_tuned':>11}{'gap':>13}  {'hard_gap':<9}"
              f"{'exact_p':<9}exact_p x%d cuts" % N_POSTHOC_CUTS_SEARCHED)
        for r in blk["density_stratified_discriminating"]:
            print(f"    {r['filter']:<14}{r['n']:>5}{r['n_finalized_zero']:>7}"
                  f"{r['n_finalized_nonzero']:>6}{_f(r['median_samples'],1):>6}"
                  f"{_f(r['median_last_lead_hours'],2):>11}"
                  f"{str(r['n_misclassified_untuned']):>9}{str(r['n_misclassified']):>11}"
                  f"{_e(r['gap_width'],4):>13}  {str(r['hard_gap']):<9}"
                  f"{_f(r['exact_p_if_hard_gap'],4):<9}"
                  f"{_f(r.get('exact_p_bonferroni_%d_cuts' % N_POSTHOC_CUTS_SEARCHED),4)}")
        print(f"    -> gap monotone non-decreasing in density: "
              f"{mono['monotone_nondecreasing_in_density']}  *** TAUTOLOGY — nested subsets"
              f" => min can only rise / max can only fall; carries NO information ***")
        print(f"       strata reaching a HARD GAP: {mono['strata_with_hard_gap'] or 'none'}"
              f"   (the `and mono` conjunct in pooled_overlap_is_density_confounded is INERT)")
        base = blk.get("matched_size_random_subset_baseline") or []
        if base:
            print("       MATCHED-SIZE RANDOM-SUBSET BASELINE (the statistic that DOES carry")
            print("       information — how often an ARBITRARY same-size subset shows a hard gap):")
            for bl in base:
                print(f"         random {bl['size']}-of-{bl['n_population']}: "
                      f"P(hard gap) = {_f(bl['p_hard_gap'],4)}  "
                      f"({bl['n_hard_gap']}/{bl['n_draws']} draws, seed={bl['seed']}, "
                      f"single-class draws={bl['n_single_class_draws']})")
            print("         -> a dense cut's hard gap only counts if it BEATS this baseline.")
        loo = blk.get("leave_one_out") or {}
        if loo:
            am = loo.get("argmax_drop") or {}
            print(f"       LEAVE-ONE-OUT influence scan: {loo['n_drops']} drops "
                  f"({loo['n_tickers_dropped']} discriminating tickers + "
                  f"{loo['n_funding_times_dropped']} discriminating funding_times + "
                  f"{loo['n_windows_dropped']} windows)")
            print(f"         drops restoring a HARD GAP: {loo['n_drops_restoring_hard_gap']}"
                  f"   max gap over all drops = {_e(loo['max_gap_width_over_drops'])}"
                  f"   (pooled {_e(loo['pooled_gap_width'])})")
            if am:
                print(f"         least-negative drop: {am.get('kind')} "
                      f"{am.get('dropped')} -> {_e(am.get('gap_width'))}")
            print("         -> no single row drives the pooled overlap; an influence check"
                  " alone could never")
            print("            have found the DENSITY confound, which is the actual reason"
                  " it is undecidable.")
        if mono["pooled_overlap_is_density_confounded"]:
            print("    *** POOLED OVERLAP IS DENSITY-CONFOUNDED for this g — the pooled "
                  "'no hard gap' result")
            print("        cannot be read as a falsification of H1. ***")
            print("        ...and `exact_p` (= 1/C(n, nonz), the chance a RANDOM labeling "
                  "produces that")
            print("        same hard gap) shows the dense strata do not establish H1 either.")
        mc = blk["misclassification_density_contrast"]
        print(f"    failures at the 1bp band: n={mc['misclassified']['n']}  "
              f"median_samples={mc['misclassified']['median_samples']}  "
              f"(<=2 samples: {mc['misclassified']['n_with_2_or_fewer_samples']})  "
              f"median_lead_h={_f(mc['misclassified']['median_last_lead_hours'],2)}")
        print(f"    correct  at the 1bp band: n={mc['correct']['n']}  "
              f"median_samples={mc['correct']['median_samples']}  "
              f"(<=2 samples: {mc['correct']['n_with_2_or_fewer_samples']})  "
              f"median_lead_h={_f(mc['correct']['median_last_lead_hours'],2)}")
        fd = rep.get("failure_density_permutation_g_last")
        if gname == "g_last" and fd:
            print("    PERMUTATION TEST of that contrast (round-2 correction — the two axes do")
            print("    NOT agree, and round 1 headlined them as if both were supported):")
            for axis, label, verdict in (("last_lead_hours", "last-sample LEAD (h)", "SUPPORTED"),
                                         ("n_samples", "path SAMPLE COUNT", "NOT SUPPORTED")):
                pr_ = fd[axis]
                print(f"      {label:<22} mean(fail)-mean(ok) = {_f(pr_['observed_diff'],4)}"
                      f"  p(one-sided)={_f(pr_['p_one_sided'],6)}"
                      f"  p(two-sided)={_f(pr_['p_two_sided'],6)}"
                      f"  [{verdict}]")
            print("      -> the failures are genuinely STALER; they are NOT significantly"
                  " sparser.")
    print("-" * W)

    print("PER-g IDENTITY FIT ON THE NON-CLAMPED BRANCH (finalized != 0); H1 wants finalized ~= g")
    for pname in ("joined_all", "discriminating"):
        print(f"  population = {pname}")
        print(f"    {'g':<16}{'n':>5}{'pearson_r':>12}{'MAE':>12}{'medAE':>12}"
              f"{'signed':>12}{'MAE/med|fin|':>14}{'sign_agree':>12}{'r(|res|,lead_h)':>17}")
        for gname in CANDIDATE_GS:
            fit = rep["per_g"][gname][pname]["identity_fit_nonclamped_branch"]
            print(f"    {gname:<16}{fit.get('n', 0):>5}"
                  f"{(_f(fit.get('pearson_r'), 4)):>12}"
                  f"{_e(fit.get('mean_abs_residual'),3):>12}"
                  f"{_e(fit.get('median_abs_residual'),3):>12}"
                  f"{_e(fit.get('mean_signed_residual'),3):>12}"
                  f"{_f(fit.get('mean_abs_residual_over_median_abs_finalized'),3):>14}"
                  f"{_f(fit.get('sign_agreement_fraction'),3):>12}"
                  f"{_f(fit.get('r_absresidual_vs_last_sample_lead_hours'),4):>17}")
    print("  (MAE/med|fin| is the residual as a FRACTION of the typical finalized magnitude —")
    print("   H1's identity leg wants ~0; r(|res|,lead_h) > 0 means the miss is staleness, i.e.")
    print("   the path's last sample landed too early, which denser tape could fix.)")
    print("-" * W)

    ind = rep["independence"]
    t = ind["table"]
    print("NULL: 'finalized is INDEPENDENT of the estimate path' (exact Fisher 2x2, analytic —")
    print("not a bootstrap, not a P&L statistic):")
    print(f"                        finalized!=0   finalized==0")
    print(f"    path has nonzero    {t['path_nonzero_final_nonzero']:>12}   "
          f"{t['path_nonzero_final_zero']:>12}")
    print(f"    path all-zero       {t['path_allzero_final_nonzero']:>12}   "
          f"{t['path_allzero_final_zero']:>12}")
    print(f"    P(finalized!=0 | path has nonzero) = "
          f"{_f(ind['rate_final_nonzero_given_path_nonzero'],4)}")
    print(f"    P(finalized!=0 | path all-zero)    = "
          f"{_f(ind['rate_final_nonzero_given_path_allzero'],4)}")
    pn = ind["p_fisher_two_sided_NAIVE_pseudoreplicated"]
    print(f"    NAIVE two-sided Fisher exact p = {pn:.3e}   <-- PSEUDO-REPLICATED (L6):")
    print("      it treats 286 windows as independent; they are 13 tickers x 22 funding_times.")
    print("      NEVER quote this number alone.")
    for label, key in (("within TICKER      ", "cluster_permutation_by_ticker"),
                       ("within FUNDING_TIME", "cluster_permutation_by_funding_time")):
        cp = ind[key]
        print(f"    cluster-robust permutation {label} p(one-sided) = "
              f"{cp['p_one_sided']:.3e}  "
              f"(n_perm={cp['n_perm']}, seed={cp['seed']}, "
              f"exceedances={cp['n_perm_ge_observed']}, MC floor={cp['mc_resolution']:.1e})")
    ct = ind["cluster_permutation_by_ticker"]
    print(f"    -> direction SURVIVES clustering ({'REJECT' if ct['p_one_sided'] < 0.05 else 'CANNOT REJECT'}"
          " independence), but the naive p overstated it by ~5 orders of magnitude.")
    sig = [r for r in ind["per_ticker_tables"] if r["p_fisher_two_sided"] < 0.05]
    print(f"    per-ticker concentration: {len(sig)} of {len(ind['per_ticker_tables'])} tickers "
          f"individually below 0.05 — but these {len(ind['per_ticker_tables'])} p's carry NO")
    print("      multiplicity correction (ZEC 0.0124 x 13 = 0.16), and a table whose whole")
    print("      discriminating count is 1 window (HYPE: p = 1/22 = 0.0455) is DEGENERATE,")
    print("      not a carrier. Real carriers on this tape: 2 (ZEC, SUI).")
    for r in sorted(ind["per_ticker_tables"], key=lambda r: r["p_fisher_two_sided"])[:4]:
        print(f"      {r['cluster']:<14} n={r['n']:>3}  a={r['a']} b={r['b']} c={r['c']} "
              f"d={r['d']}  disc={r['n_discriminating']:>2}  fisher_p={r['p_fisher_two_sided']:.4g}")
    print("-" * W)

    d = rep["density"]
    print("DATA ADEQUACY (this is a characterization + data-adequacy verdict, not a CI):")
    print(f"  captures/day (distinct capture_id, funding_estimate rows): {d['captures_per_day']}")
    print(f"  days below the {d['advisory_floor_per_day']:.0f}/day advisory floor: "
          f"{d['n_days_below_advisory_floor']} of {d['n_days']}")
    print(f"  estimate samples per joined window: median={d['median_samples_per_window']}  "
          f"mean={_f(d['mean_samples_per_window'],2)}  min={d['min_samples_per_window']}  "
          f"max={d['max_samples_per_window']}")
    print(f"  last-sample lead before funding_time (h): median="
          f"{_f(d['median_last_sample_lead_hours'],2)}  max={_f(d['max_last_sample_lead_hours'],2)}")
    print("-" * W)

    print("VERDICT — H1 is UNDECIDABLE at current tape density.")
    print("  CAN say (density-independent): the published forward ESTIMATE is itself +/-1bp")
    print("    clamped, so the regressor is PRE-CLAMPED and sub-band information is destroyed")
    print("    at the source; part 1's untuned 1bp constant does NOT transfer to the estimate")
    print("    path; the path/print association is real but CLUSTERED — carried by 2 of 13")
    print("    tickers (ZEC p=0.0124, SUI p=0.0364; HYPE's 0.0455 is 1/22 off a single")
    print("    degenerate 1-window table and is NOT a carrier), and those 13 per-ticker")
    print("    Fisher p's carry NO multiplicity correction (ZEC 0.0124 x 13 = 0.16).")
    print("  CANNOT say: whether some (g, theta) satisfies H1. The pooled overlap that the")
    print("    first pass called a falsification inverts to a hard gap on the dense subsets;")
    print("    those dense subsets are too small (1-2 nonzero-finalized windows) and too")
    print("    post-hoc to establish H1 either — over %d searched cuts, Bonferroni gives"
          % N_POSTHOC_CUTS_SEARCHED)
    print("    lead<=0.75h 0.0110 x %d = 0.0989 and n>=8 0.0909 x %d = 0.818, neither"
          % (N_POSTHOC_CUTS_SEARCHED, N_POSTHOC_CUTS_SEARCHED))
    print("    significant at 0.05 (and the effective family is larger than %d, since the"
          % N_POSTHOC_CUTS_SEARCHED)
    print("    values 8 and 0.75 were themselves chosen after seeing the data).")
    print("  REOPEN CONDITION: a sample inside the final ~5 minutes before funding_time PLUS")
    print("    >=8 samples per window (~30 captures/day sustained). Caveat: the pre-clamp on")
    print("    the estimate means even that may not suffice — the FORMULA question may be")
    print("    structurally unanswerable from the funding_estimate endpoint at ANY density.")
    print("=" * W)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Q42 part-1 residual: estimate-path -> finalized-print clamp-formula "
                    "inference (offline, read-only, NOT a P&L claim)")
    ap.add_argument("--tape", default=DEFAULT_TAPE_GLOB,
                    help="tape path or glob (default: %(default)s)")
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--n-perm", type=int, default=N_PERMUTATIONS,
                    help="cluster-robust permutation draws (default: %(default)s)")
    ap.add_argument("--n-subset-draws", type=int, default=N_RANDOM_SUBSET_DRAWS,
                    help="matched-size random-subset baseline draws (default: %(default)s)")
    ap.add_argument("--seed", type=int, default=PERMUTATION_SEED,
                    help="permutation seed — the run is deterministic given it "
                         "(default: %(default)s)")
    args = ap.parse_args(argv)

    records = load_records(args.tape)
    rep = analyze(records, n_perm=args.n_perm, seed=args.seed,
                  n_subset_draws=args.n_subset_draws)
    _print_report(rep)

    if args.json_out:
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "price_source_tag": PRICE_SOURCE_TAG,
            "is_pnl_claim": False,
            "tape": args.tape,
            "dead_band": DEAD_BAND,
            "report": rep,
        }
        Path(args.json_out).write_text(json.dumps(payload, indent=2, default=str))
        print(f"[q42-pathinf] wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
