#!/usr/bin/env python3
"""q48_s55_fomc_lag_probe.py — Q48 / S55: post-release SINGLE-LEG Kalshi-lag taker on FOMC
(read-only, PREP infrastructure — NOT a verdict).

LOOP-QUEUE.md Q48 (added 2026-07-26 by the Q21 idea-gen round; `findings/2026-07-26-q21-idea-
gen-round.md`; `kb/strategies/00-index.md` S55, status **collect-and-revisit**, n=0).

── THE SEMANTICS ────────────────────────────────────────────────────────────────────────────────
In the seconds-to-minutes after the 18:00Z FOMC statement, Kalshi's thin `KXFEDDECISION-*` book
is hypothesised to reprice SLOWER than Polymarket/CME. S55 uses Polymarket's post-release implied
probability as a **free exogenous SIGNAL** and takers the stale Kalshi side toward it. Polymarket
is NOT a traded leg here — that is the whole point of S55 versus the two-fee-dead S34/S51 — so
exactly ONE Kalshi **taker** fee is charged, in the direction of a COST subtracted from the edge
(`core.pricing.fee_per_contract(price)`, whose default rate is `TAKER_FEE_RATE` = the conservative
taker schedule; never a hand-rolled literal, `scripts/invariants.py::no_handrolled_fee_rate`).
No Polymarket fee is charged and none should be: we never send an order there. The corollary is
that a Polymarket price in this probe is a SIGNAL, never a fill — it can never be quoted as
realizable P&L.

── STATUS: PROBE-PREP, NOT A VERDICT (idle-run policy (b), mirrors q43/q37/q36/q32) ─────────────
Q48 is BURST-GATED: it unblocks only when the one-shot trigger `kalshi-burst-fomc-0729` (fires
2026-07-29T17:40Z, `fed,econ,crypto @90s`) actually commits burst tape SPANNING the 18:00Z
release into `tape/polymarket_macro_pairs/`. The burst `fed` family runs
`collection/polymarket_pairs.py::run_fed_decision()` (`collection/burst_capture.py::FAMILY_REGISTRY`)
— the SAME family the recurring hourly pass writes, so burst lines are distinguishable ONLY by
`captured_at`/`capture_id` DENSITY, never by a separate path. This script is built + offline-tested
now so it fires the day the gate opens. Below the gate it prints an honest INSUFFICIENT DATA
object (with the specific counts) and exits 0 — it NEVER fabricates a bootstrap / CI / verdict,
writes NO findings/ entry, and touches NO registry.

Per L25 the gate is judged by FILE SHAPE and RECORD CONTENT, never path existence: a `dt=<date>`
entry that is a DIRECTORY (the 2026-07-08 main-rewind regression) is counted and skipped, and a
"burst window" is defined by observed inter-pass intervals in the records themselves.

── DATA-ADEQUACY GATE, RUN FIRST, BEFORE ANY STATISTIC (L28/L53 discipline) ─────────────────────
1. Group records by `capture_id` -> a PASS. Sort passes by capture instant.
2. A **burst window** is a maximal run of consecutive passes whose inter-pass interval is
   <= `BURST_MAX_INTERVAL_S` (default 300s — the trigger runs @90s) and which contains at
   least `MIN_PASSES_PER_BURST_WINDOW` passes.
   RECURRING-LEG CADENCE, CORRECTED 2026-07-26 (the earlier "~2 captures/day" in this
   docstring was wrong by 5-15x and contradicted its own parenthetical; the CONCLUSION it
   supported survives, the number did not): over the committed tape the recurring leg runs
   **600 passes across 20.65 days = 29.05 passes/day**, median inter-pass gap **1,856.3s
   (~31 min)**; restricted to since-2026-07-19 it is **72 passes = 9.44/day**, median gap
   **10,777.7s (2.99h)**, with only **2 of 71** gaps <= 300s. Command that produced these
   (2026-07-26, this repo, committed tape):
       python3 -c "import sys,statistics; sys.path.insert(0,'.'); \
         from scripts.q48_s55_fomc_lag_probe import load_family_records, pass_times, \
         DEFAULT_TAPE_DIR; r,_=load_family_records(DEFAULT_TAPE_DIR); t,_=pass_times(r); \
         ts=sorted(t.values()); g=[(b-a).total_seconds() for a,b in zip(ts,ts[1:])]; \
         print(len(ts), (ts[-1]-ts[0]).total_seconds()/86400, statistics.median(g))"
   A ~31-min (let alone 3.0h) recurring cadence still cannot see a seconds-to-minutes reprice
   — the S9 wall holds, which is why the burst trigger exists at all — but 300s is NOT
   "comfortably between two regimes": 2 recurring gaps in the last week alone fall under it,
   and 7 of the 8 burst windows detected in the committed tape are exactly such coincidences.
   Hence step 2b.
2b. **Cadence qualification (advisory, reported, NOT a gate).** A detected window is
   `cadence_qualified` only at >= `BURST_CADENCE_MIN_PASSES` passes AND
   >= `BURST_CADENCE_MIN_DURATION_S` wall-clock seconds. On the committed tape this cleanly
   separates the ONE real burst (`20260714T120723Z`: 101 passes, 5,871.7s, median gap 60.09s
   — the June-CPI burst leg) from the SEVEN recurring-cadence coincidences (2-5 passes,
   57.5-288.5s duration, median gaps 57.5/78.4/85.8/98.7/99.6/154.0/286.2s — the last a
   two-pass pair 13.8s under the 300s threshold). The report emits
   `n_burst_windows_cadence_qualified` / `n_burst_windows_marginal` beside the raw
   `n_burst_windows` so no run can write "8 burst windows" into a log entry as if they were
   eight bursts. The thresholds are read off that observed separation and named as constants;
   they do NOT change which windows enter the analysis (see H/`MIN_BURSTS_FOR_CI`).
3. A burst window **covers** the release instant iff it has >= 1 pass strictly BEFORE and >= 1
   pass strictly AFTER it.
4. Zero covering burst windows **OR zero surviving priced observations** ->
   `status = "INSUFFICIENT DATA"`, counts printed (`n_fed_records`, `n_passes`,
   `n_burst_windows`, `n_observations`, `max_pass_density_per_hour`), exit 0, NO edge/CI claim
   of any kind. That is the EXPECTED result until 2026-07-29. The `n_observations > 0` half is
   load-bearing: a tape whose every record is tagged `midpoint` (or otherwise fails the
   `real_ask` gate) leaves ZERO observations, and without this clause the probe would still
   reach `status="ANALYSIS"` with a vacuous `no_persistent_stale_window=True` and a
   `bootstrap.mean=null` "BOOTSTRAPPED" verdict.

── REFUSAL TO VERDICT ON THIN DATA (ADVISORY, NOT STRUCTURAL — corrected 2026-07-26) ────────────
`MIN_BURSTS_FOR_CI = 3`. Only ONE maximal burst run can straddle a given instant, so n_bursts=3
requires 3 DIFFERENT instants in a comma-separated `--release-ts`. It does NOT follow — and this
docstring previously claimed twice that it did, "by construction" — that those are 3 real FOMC
statements. NOTHING in this probe validates that a supplied instant is a real event, and at
`MIN_PASSES_PER_BURST_WINDOW = 2` against a 300s threshold an ordinary recurring-cadence PAIR
qualifies as a "burst window". A verifier demonstrated the hole on the committed tape
(2026-07-26) with ONE `--release-ts` string of seven fabricated instants, each chosen to fall
between two ordinary recurring captures: the probe printed `verdict = "BOOTSTRAPPED
(n_bursts=7)"` with a strictly POSITIVE `ci95`. The refusal floor is therefore ADVISORY on an
operator-supplied instant list. What guarded that output was NOT the floor but the gates
reported beside the CI: `bootstrap_verdict_admissible.admissible = False` (below `min_units`,
and no opposing unit) and, in the verifier's own run, `clears_tick_magnitude = False`.
BE PRECISE ABOUT THE SECOND ONE: that run's population still contained sub-tick float-dust
"trades"; with the `MIN_ENTRY_EDGE` gate now in place a re-run of the same attack shape (7
fabricated instants, 9 surviving fired edges, mean +1.42c) reports
`clears_tick_magnitude = True`. The tick-magnitude gate is therefore NOT a reliable guard
against a fabricated instant list — only `admissible = False`, the per-window
`cadence_qualified` flag and the `bootstrap_cadence_warning` (emitted whenever a bootstrap is
built on covering windows that are not burst cadence) are. A CI from this probe is never a
verdict on its own; read the gates, and check that the releases were real.
One FOMC burst is n=1: descriptive only, never a verdict (Q48's own honesty gate — a
block-bootstrap-by-burst is admissible only at several settled meetings, ~8/yr). Below the floor
the probe emits `verdict = "DESCRIPTIVE ONLY (n_bursts=<n> < MIN_BURSTS_FOR_CI=3)"` and does NOT
run or print a bootstrap CI. At or above it, `core.bootstrap.block_bootstrap` resamples **BY
BURST WINDOW** — the independent unit (L6: observations inside one release are one correlated
shock; NEVER resample by capture, bucket, or ticker, which would fake n by ~15x/pass) — and the
report carries `bootstrap_verdict_admissible` (L41 degeneracy/min-unit gate) and
`clears_tick_magnitude` (L27 economic-significance gate) beside the CI. Note MIN_BURSTS_FOR_CI (3)
is far BELOW L41's default `min_units=10`, so an n=3 CI will report `admissible=False` — that is
the intended, honest outcome, not a bug.

── HARD RULE #3: `KXFEDDECISION-*` IS A BRACKET LADDER ──────────────────────────────────────────
Each `meeting` is a 5-bucket partition {cut_50plus, cut_25, no_change, hike_25, hike_50plus}
(census over the committed tape, 2026-07-26: 3 meetings x 5 buckets x 600 passes = 9,000 records,
one `family` value `fed_decision`, one `schema_version` `polymarket_macro_pairs.v1`). A raw
`yes_ask` is NOT a probability. Per (meeting, capture_id) this probe computes the Kalshi
`bracket_sum` across the buckets present via `core.pricing.bracket_sum`, and the Polymarket ladder
sum the same way when ALL of that meeting's buckets are present in the pass; probabilities come
from `core.pricing.normalized_ask` only.

WHICH GAP IS THE TRADE SIGNAL, AND WHY — both are reported, and they answer different questions:
  * NORMALIZED gap (`normalized_ask(kalshi) - normalized_ask(polymarket)`) is the **disagreement
    signal**. Only a bracket_sum-normalized ask is a probability (Hard Rule #3); a raw ask carries
    each venue's own overround, so a raw gap partly measures a difference in OVERROUND rather than
    a difference in BELIEF. Direction must be taken from the normalized gap.
  * RAW ask gap net of the single Kalshi taker fee is the **executable quantity** — the dollars
    actually paid and received. You cannot fill at a normalized price (that would be the pt1
    synthetic-price-as-fillable mistake).
  A trade is only counted when BOTH agree: the normalized gap points the trade's way AND the raw
  entry edge net of the Kalshi taker fee clears ONE TICK (`MIN_ENTRY_EDGE = PRICE_TICK`, not a
  bare `> 0`: a floating-point residue of 8.67e-18 is not a trade, and 9 of the 24 "fired trades"
  on the 2026-07-14 CPI dry-run were exactly that before this gate existed). Sub-tick candidates
  are COUNTED (`n_subtick_candidates_dropped`), never silently discarded. An observation whose
  bracket sums are unavailable is NORMALIZATION-UNMEASURABLE and is EXCLUDED (counted, never
  assumed tradeable).

── THE KILL STATISTIC Q48 NAMES (computed, not asserted) ────────────────────────────────────────
Per (burst window, meeting, bucket) unit, all off `real_ask` quotes:
  * the post-release trajectory of the Kalshi taker price vs the Polymarket signal;
  * `max_abs_gap_net_fee` — max post-release |raw gap| minus the Kalshi taker fee, REPORTED
    BESIDE `pre_release_max_abs_gap_net_fee` and their difference `excess_max_abs_gap_net_fee`
    (see the baselining note below);
  * `captures_until_first_kalshi_move` — how many post-release captures until Kalshi's `real_ask`
    first differs from its last PRE-release value (None = never moved in the window). This
    statistic is MAGNITUDE-BLIND by construction (any move > 1e-12 counts, so Kalshi ticking
    0.70 -> 0.71 against a 10c Polymarket shock scores 1, identical to full convergence). Its
    bias is toward the KILL (it makes Kalshi look faster than it is), which is the safe
    direction for a probe whose job is to falsify a lag thesis — but it must never be read as
    "Kalshi caught up". The magnitude-qualified companion
    `captures_until_kalshi_closed_half_of_polymarket_move` is reported beside it: the first
    post-release capture at which Kalshi has moved, in the Polymarket move's own direction, at
    least half as far as Polymarket did versus the same pre-release baseline. It is None (not 0)
    when Polymarket itself never moved >= one tick — there is then no move to close, and the
    statistic is UNMEASURABLE rather than trivially satisfied.
  * `stale_window_seconds` — WALL-CLOCK duration (L76 discipline, via
    `core.bootstrap.collapse_duration_gated_runs`, never a snapshot COUNT) of any run where
    (|gap| - fee) > 0; a run counts as persistent only at >= `STALE_WINDOW_MIN_SECONDS`. This is
    an ABSOLUTE number and is kept, clearly labelled, as
    `has_persistent_stale_window_absolute_unbaselined`.

  BASELINING THE STALE WINDOW AGAINST THE UNIT'S OWN PRE-RELEASE STATE (extends L76 from
  "count vs wall-clock" to "absolute vs baselined"). An absolute (|gap| - fee) > 0 run measures a
  PERMANENT cross-venue overround just as happily as a release lag. On the real 2026-07-14 CPI
  burst, 7 of the 12 units flagged persistent by the absolute rule had (|gap| - fee) > 0 on
  **100% of their PRE-release captures**: their 4,502.0s "stale windows" were simply the full
  post-release span of a standing overround on illiquid far-dated buckets. `2026-10|hike_25`'s
  headline `max_abs_gap_net_fee = 0.19` sat on a PRE-release max of 0.15 — the release
  contributed 4c of a 19c "dislocation". So each unit now carries its own pre-release baseline
  (`pre_release_frac_gap_net_fee_positive`, `pre_release_max_abs_gap_net_fee`, `n_pre_captures`),
  and the flag the kill condition consumes, `has_persistent_stale_window`, requires an EXCESS
  over that baseline: the absolute run must clear `STALE_WINDOW_MIN_SECONDS`, AND the
  post-release fraction of >fee captures must exceed the unit's own pre-release fraction, AND
  the post-release max must exceed the pre-release max by MORE THAN
  `STALE_WINDOW_MIN_EXCESS_DOLLARS` (one tick — a sub-tick "excess" is not a fillable
  difference, L27). The comparison is `excess_max >= STALE_WINDOW_MIN_EXCESS_DOLLARS +
  STALE_WINDOW_EXCESS_EPSILON`, and since BOTH legs quote on a 1c grid the on-grid consequence
  is simply: an excess of EXACTLY one tick does NOT clear; two ticks does. That is a DELIBERATE
  TIGHTENING of the originally documented ">= 1 tick" rule (see the constants block for the
  measured consequence and the rejected alternative) — it is NOT a de-dusting of a float
  residue, and the one unit it drops on the 2026-07-14 CPI dry-run carried an excess of exactly
  one tick in exact arithmetic, not dust (L180 closure). All three components plus the raw
  absolutes are emitted separately so a reader can disagree with the conjunction. A unit with NO
  pre-release capture has an UNMEASURABLE baseline: its `has_persistent_stale_window` is None
  (never True, never False), it is counted in `n_units_stale_window_baseline_unmeasurable`, and
  it does not contribute to `no_persistent_stale_window` — which biases toward the kill, stated
  rather than hidden.

  THE BASELINE NEEDS ITS OWN n-ADEQUACY GUARD (L180). Differencing against a pre-event period
  does not remove vacuity if the pre-period can be n=1: with one pre-capture
  `pre_release_frac_gap_net_fee_positive` is confined to {0, 1} and
  `pre_release_max_abs_gap_net_fee` is a single draw, so ONE momentarily-tight pre-capture
  turns a PERMANENT standing cross-venue overround back into a "release-caused
  dislocation" — the exact failure the
  baseline exists to prevent (identical fixture, identical post-release rows: `n_pre=1` ->
  True, `n_pre=23` -> False). A unit with `1 <= n_pre < MIN_PRE_CAPTURES_FOR_BASELINE` is
  therefore THIN-BASELINED: it carries `thin_baseline = True`, its `has_persistent_stale_window`
  is None (the SAME unmeasurable-class convention as a zero-pre-capture unit — never True,
  never False), it is counted in `n_units_with_thin_stale_window_baseline` (reported beside
  `n_units_stale_window_baseline_unmeasurable`, which keeps its original zero-pre-capture
  meaning, so the two counts partition the None flags without double-counting), and it can
  never CREATE a `n_units_with_persistent_stale_window` count. Same kill-biased direction as
  the unmeasurable case, stated rather than hidden.

Q48's kill condition, emitted as the named field `kill_condition_met`: True iff NO unit showed a
BASELINED persistent positive gap-net-of-fee window AND the median captures-until-first-move is
<= `KILL_MAX_CAPTURES_TO_REPRICE` (1) — i.e. Kalshi reprices within one capture of the release
and there is no stale window wide enough to lift. Its two components are printed separately so a
reader can disagree with the conjunction. With ZERO units in scope both
`no_persistent_stale_window` and `kill_condition_met` are None, never a vacuous boolean: "no
unit showed a stale window" is not a finding when there were no units.

THE SAME GUARD RUNS ON THE COUNT OF **MEASURABLE** UNITS, NOT THE COUNT OF UNITS. An n-adequacy
FLOOR does not remove vacuity, it RELOCATES it: raising `MIN_PRE_CAPTURES_FOR_BASELINE` from 1 to
5 converts thin-baselined units into None-flagged units, and a population in which EVERY unit is
None would otherwise satisfy `n_persistent == 0` and fire a hard "S55 is dead" off zero
measurable evidence. So `no_persistent_stale_window` — and therefore `kill_condition_met` — is
None whenever `n_units_with_measurable_stale_window_baseline == 0`, the same
None-means-unmeasurable convention this file uses everywhere else. This is LIVE, not
hypothetical: at the burst's 90s cadence any window that opens < 7.5 min before the 18:00Z
statement leaves every unit below the floor, and the chunked-commit recipe for
`kalshi-burst-fomc-0729` (`ops/ROUTINES.md`) is prepared but not yet applied, so a truncated
window on 2026-07-29 is a real possibility.

── L28 PRECHECK, AND WHAT L32 DOES *NOT* APPLY TO HERE ──────────────────────────────────────────
`core.bootstrap.floor_pinned_fraction` runs on the EARLIEST (pre-release) Kalshi asks before the
trajectory pipeline: a bucket already pinned at the 1c YES floor has no room below it to be
"stale cheap", so a population that is mostly floor-pinned has no measurable window regardless of
what the gap statistics say.

L32's frozen-pair rule (a consecutive snapshot pair with no movement is a NO-FILL) is a MAKER
concern and is deliberately NOT applied: S55 is a TAKER lift of a resting offer, for which a
frozen quote is the TARGET, not a non-fill. The binding honesty limit here is different and
worse — `polymarket_macro_pairs.v1` carries NO size/depth fields on either leg (L57 already
flagged this family as size-blind), so at-touch depth is UNMEASURABLE. `DEPTH_UNMEASURABLE = True`
travels with every report: any positive edge this probe ever finds is depth-unmeasurable and can
NEVER graduate on this tape alone.

── STEADY-STATE BASELINE (`--baseline`, also in the default summary) ────────────────────────────
Over every NON-burst pass in the committed tape: n, mean signed raw gap, mean |raw gap|, and the
same in normalized terms, with the `price_source_tag` observed on BOTH legs (both `real_ask`).
Q48 quotes a steady-state gap of ~=0.6c; this probe reproduces the number from tape with its own
code path and reports what it ACTUALLY gets, all-meetings and front-meeting-only (the front
meeting is the one whose `meeting` key matches the release month — the ladder the release
actually decides). The exact re-run command is printed as `rerun_command`.
ONE FIELD IN THIS SECTION IS VACUOUS AND MUST NEVER BE QUOTED: `baseline.*.normalized_gap.mean`
(i.e. `baseline.all_meetings.normalized_gap.mean` and
`baseline.front_meeting_only.normalized_gap.mean`). Both ladders are normalized over the SAME
bucket set, so a complete pass's normalized gaps sum to exactly 0 and the pooled mean is ~0 by
construction (the committed tape's -1.13e-17 is that identity, not agreement between venues).
Every OTHER field here — including `normalized_gap.mean_abs` / `median_abs` / `median` and the
whole `raw_gap` block — is informative; the `normalized_gap` MEAN alone is the one that is
arithmetic rather than evidence. The same warning ships in-band as `normalized_gap_note`.

READ-ONLY OVER TAPE. NO NETWORK, NO CREDENTIALS, NO ORDERS, NO `execution/` IMPORTS.
Timestamps parse through `core.timeutil` only (L136/L138/L141/L150 — never raw
`datetime.fromisoformat`), reusing `scripts.s17_leadlag_probe.parse_capture_time` rather than
re-deriving it (L36).

Run:
    python scripts/q48_s55_fomc_lag_probe.py
    python scripts/q48_s55_fomc_lag_probe.py --baseline
    python scripts/q48_s55_fomc_lag_probe.py --release-ts 2026-07-29T18:00:00Z --json
    # several accumulated meetings (the only way to reach the CI path — see parse_releases):
    python scripts/q48_s55_fomc_lag_probe.py \
        --release-ts 2026-07-29T18:00:00Z,2026-09-16T18:00:00Z,2026-10-28T18:00:00Z
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.bootstrap import (  # noqa: E402
    block_bootstrap,
    bootstrap_verdict_admissible,
    clears_tick_magnitude,
    collapse_duration_gated_runs,
    floor_pinned_fraction,
)
from core.io import REPO_ROOT  # noqa: E402
from core.pricing import (  # noqa: E402
    TAKER_FEE_RATE,
    bracket_sum as bracket_sum_fn,
    fee_per_contract,
    normalized_ask,
)
from core.timeutil import parse_iso_utc  # noqa: E402
# Reused, never re-derived (L36): the family's own capture-instant parser, which already routes
# through core.timeutil.parse_iso_utc and falls back to the compact capture_id grammar.
from scripts.s17_leadlag_probe import _as_float, parse_capture_time  # noqa: E402

DEFAULT_TAPE_DIR = REPO_ROOT / "tape" / "polymarket_macro_pairs"

# ── the family the burst `fed` leg writes (collection/burst_capture.py::FAMILY_REGISTRY ->
# polymarket_pairs.run_fed_decision). Confirmed as the ONLY family value in the committed tape.
DEFAULT_FAMILY = "fed_decision"
SCHEMA_VERSION = "polymarket_macro_pairs.v1"

# ── the 18:00Z FOMC statement the `kalshi-burst-fomc-0729` trigger brackets (17:40 -> 19:45Z).
DEFAULT_RELEASE_TS = "2026-07-29T18:00:00Z"

# ── burst detection. The trigger runs @90s; the RECURRING leg runs 600 passes over 20.65 days
# = 29.05 passes/day, median observed inter-pass gap 1,856.3s (since 2026-07-19: 72 passes,
# 9.44/day, median 10,777.7s, 2 of 71 gaps <= 300s) — see the docstring for the exact command.
# 300s therefore does NOT cleanly separate the regimes on its own: recurring pairs do slip under
# it. The threshold is UNCHANGED (it is what the detection contract was verified against); the
# separation is instead reported per window via the advisory cadence qualification below.
BURST_MAX_INTERVAL_S = 300.0
MIN_PASSES_PER_BURST_WINDOW = 2
DENSITY_WINDOW_SECONDS = 3600.0

# ── advisory cadence qualification, read off the observed separation in the committed tape
# (2026-07-26): the ONE real burst window is 101 passes / 5,871.7s; the seven recurring-cadence
# coincidences are 2-5 passes / 57.5-288.5s. These thresholds sit in that gap. They are REPORTED,
# never used to include or exclude a window from the analysis.
BURST_CADENCE_MIN_PASSES = 10
BURST_CADENCE_MIN_DURATION_S = 600.0

# ── the refusal-to-verdict floor: a block-bootstrap BY BURST needs several settled meetings.
MIN_BURSTS_FOR_CI = 3
N_BOOT = 10000
BOOTSTRAP_SEED = 42

# ── kill-condition parameters (Q48's own wording, made computable).
STALE_WINDOW_MIN_SECONDS = 60.0     # a >fee gap must persist this long to be "persistent"
KILL_MAX_CAPTURES_TO_REPRICE = 1    # "reprices within one capture of the release"

PRICE_TICK = 0.01                   # Kalshi's minimum tick — the L27 magnitude yardstick
YES_FLOOR_PRICE = 0.01              # the 1c YES floor for the L28 floor-pinned precheck

# ── a fired trade must clear one tick, not a float residue (`> 0` admitted 8.67e-18 "edges").
MIN_ENTRY_EDGE = PRICE_TICK
# ── the post-release stale window must EXCEED the unit's own pre-release baseline, by a full
# tick of max gap and by a strictly larger fraction of >fee captures. A permanent cross-venue
# overround is not a release lag.
STALE_WINDOW_MIN_EXCESS_DOLLARS = PRICE_TICK
# ── ...and that comparison carries an EPSILON on the THRESHOLD side, in the family of
# `MIN_ENTRY_EDGE` on the entry side (L176/L179/L180). READ WHAT IT ACTUALLY DOES, NOT WHAT AN
# EPSILON USUALLY DOES: because both legs quote on a 1c grid, an on-grid excess is a multiple of
# 0.01 in intent, and adding 1e-9 to a 0.01 threshold changes exactly ONE outcome — an excess of
# EXACTLY one tick no longer clears. This is a DELIBERATE TIGHTENING of the rule from ">= 1 tick"
# to "> 1 tick". It is NOT de-dusting: no float residue is removed by it, because the residues
# this arithmetic produces (~1e-17..1e-18) never came within 7 orders of magnitude of deciding a
# 0.01 comparison in the first place.
# THE ONE UNIT IT DROPS, MEASURED RATHER THAN INHERITED (correcting the "ulp accident" claim this
# comment carried on 2026-07-27, which propagated through three artifacts unre-measured — the
# L177 citation-chain failure applied to a float-fragility claim). `2026-10|cut_25` of the
# 2026-07-14 CPI dry-run has pre-release kalshi 0.11 / poly 0.12 -> |gap| = 0.01 and
# fee_per_contract(0.11) = 0.01, so its pre-release max is 0.00 and its excess is
# Decimal('0.01') - Decimal('0.00') = 0.01 EXACTLY — one full tick in exact arithmetic. In float
# it lands at post_max - pre_max = 0.010000000000000009 (post_max = 0.010000000000000004,
# pre_max = -5.204170427930421e-18), which carries 5.0 ulps of margin over 0.01; forcing pre_max
# to exactly 0.0 STILL clears one tick, with 2.0 ulps to spare. It was therefore never one ulp
# from the boundary and is NOT dust: it is dropped BY THE NEW RULE, not by de-dusting.
#   python3 -c "import math;u=math.ulp(0.01);post=0.010000000000000004;\
#     pre=-5.204170427930421e-18;print(round(((post-pre)-0.01)/u,2),'ulps');\
#     print(post-0.0>=0.01, round((post-0.01)/u,2))"   -> `5.0 ulps` / `True 2.0`
# WHY THE TIGHTENING IS THE RIGHT DIRECTION — SAY IT OUT LOUD, IT IS A REAL CHOICE.
# `has_persistent_stale_window = True` is the ALIVE-favouring outcome (it blocks Q48's kill
# condition), an excess of exactly one tick is one grid step of quantization apart from no excess
# at all on either leg, and every other conservative choice in this statistic already biases
# toward the KILL (unmeasurable baseline -> None, thin baseline -> None, magnitude-blind first
# move). The REJECTED alternative was a tolerant epsilon (`>= threshold - eps`), which keeps the
# documented ">= 1 tick" semantics and is ulp-invariant, but snaps the boundary case to the ALIVE
# side. Measured consequence on the 2026-07-14 CPI dry-run, published so the choice can be
# overruled with full information: strict (this code) gives n_units_with_persistent_stale_window
# = 3; the documented ">= 1 tick" rule — whether spelled as a bare `>=` or as a tolerant epsilon
# — gives 4. The 4th unit is `2026-10|cut_25`, and under the ">= 1 tick" rule its inclusion was
# and remains CORRECT; this code deliberately asks for more than that rule did.
# WHY 1e-9 (dollars = 1e-7 cents) rather than some other small number: it is 7 orders BELOW one
# tick, so it can never filter an economically real excess, and it is the tolerance
# `core.bootstrap.floor_pinned_fraction`/`clears_tick_magnitude` already use for dollar-price
# comparisons, so this probe does not invent a new convention.
STALE_WINDOW_EXCESS_EPSILON = 1e-9
# ── the baseline's own n-adequacy floor (L180). At n_pre = 1 the pre-release fraction is
# confined to {0, 1} and the pre-release MAX is a single draw, so a lone momentarily-tight
# pre-capture manufactures a "release-caused" excess out of a permanent overround. WHY 5:
# (i) the max of n draws estimates about the n/(n+1) quantile of the unit's quiet-state gap
# distribution — n=1 is the median, n=3 the ~75th, n=4 the ~80th, n=5 the ~83rd percentile, so 5
# is the first value at which the baseline max is a genuinely upper-tail statistic rather than a
# coin flip; (ii) it gives the fraction a resolution of 0.20 instead of 1.00 (n=1) or 0.33 (n=3);
# (iii) it is REACHABLE BY DESIGN in the burst it gates — `kalshi-burst-fomc-0729` opens at
# 17:40Z at 90s cadence against an 18:00Z statement, so ~13 pre-release passes are expected
# (2.6x the floor), and the 2026-07-14 CPI dry-run carries n_pre = 23 on all 15 units (4.6x) —
# so this floor cannot silently disqualify the very run it exists to protect. It is a floor on
# ADEQUACY, not on truth: a thin baseline is reported as unmeasurable-class (None), never as a
# False that would license the opposite claim.
MIN_PRE_CAPTURES_FOR_BASELINE = 5
# ── the magnitude-qualified first-move companion: Kalshi must close >= this share of the
# Polymarket move, and Polymarket must itself have moved >= one tick for the statistic to exist.
KALSHI_CATCHUP_FRACTION = 0.5
MIN_POLYMARKET_MOVE = PRICE_TICK

# ── structural limit of this tape family, carried in every report (L57: macro_pairs is
# size-blind). No `yes_ask_size`/`best_ask_size` exists on either leg, so at-touch depth cannot
# be measured and no edge found here may be called fillable on this tape alone.
DEPTH_UNMEASURABLE = True

REQUIRED_TAG = "real_ask"


# --------------------------------------------------------------------------- #
# loading (read-only; L25 file-shape aware)
# --------------------------------------------------------------------------- #
def load_family_records(tape_dir: Path, family: str = DEFAULT_FAMILY
                        ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Every `dt=*.jsonl` record of `family` under `tape_dir`, with an honest skip ledger.

    L25: judged by FILE SHAPE, not path existence — a `dt=<date>` entry that is a DIRECTORY
    (the 2026-07-08 main-rewind regression shape) is counted in `n_nonfile_dt_entries` and
    skipped rather than silently miscounted as a readable day. Malformed lines and records of
    another family are counted, never silently dropped.
    """
    skips: Dict[str, Any] = {
        "n_lines_total": 0,
        "n_bad_json": 0,
        "n_other_family": 0,
        "n_other_schema": 0,
        "n_nonfile_dt_entries": 0,
        "n_day_files": 0,
    }
    records: List[Dict[str, Any]] = []
    tape_dir = Path(tape_dir)
    if not tape_dir.is_dir():
        return records, skips
    for entry in sorted(tape_dir.iterdir()):
        if entry.name.startswith("dt=") and entry.is_dir():
            skips["n_nonfile_dt_entries"] += 1
            continue
        if entry.suffix != ".jsonl" or not entry.is_file():
            continue
        skips["n_day_files"] += 1
        try:
            text = entry.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            skips["n_lines_total"] += 1
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                skips["n_bad_json"] += 1
                continue
            if not isinstance(rec, dict):
                skips["n_bad_json"] += 1
                continue
            if rec.get("family") != family:
                skips["n_other_family"] += 1
                continue
            if rec.get("schema_version") not in (None, SCHEMA_VERSION):
                skips["n_other_schema"] += 1
                continue
            records.append(rec)
    return records, skips


# --------------------------------------------------------------------------- #
# passes + burst-window detection (the data-adequacy gate)
# --------------------------------------------------------------------------- #
def pass_times(records: Sequence[Dict[str, Any]]) -> Tuple[Dict[str, datetime], int]:
    """`{capture_id: capture instant}` (earliest parsed instant wins within a pass) plus the
    count of records whose instant could not be parsed at all. Parsing routes through
    `scripts.s17_leadlag_probe.parse_capture_time` -> `core.timeutil.parse_iso_utc` (L136/L141:
    never raw `datetime.fromisoformat`)."""
    times: Dict[str, datetime] = {}
    n_no_time = 0
    for rec in records:
        cid = rec.get("capture_id")
        when = parse_capture_time(rec)
        if cid is None or when is None:
            n_no_time += 1
            continue
        cid = str(cid)
        prev = times.get(cid)
        if prev is None or when < prev:
            times[cid] = when
    return times, n_no_time


def detect_burst_windows(times: Dict[str, datetime], *,
                         max_interval_s: float = BURST_MAX_INTERVAL_S,
                         min_passes: int = MIN_PASSES_PER_BURST_WINDOW) -> List[Dict[str, Any]]:
    """Maximal runs of consecutive passes whose inter-pass interval is <= `max_interval_s`,
    keeping only runs of at least `min_passes` passes. Each window carries its ordered
    `capture_ids`, start/end instants, pass count and median inter-pass gap — the honesty
    check that a "burst" really is burst cadence and not sparse recurring tape.

    That check is now COMPUTED, not left to the reader: `cadence_qualified` is True only at
    >= `BURST_CADENCE_MIN_PASSES` passes AND >= `BURST_CADENCE_MIN_DURATION_S` wall-clock
    seconds. On the committed tape 7 of the 8 detected windows are 2-5-pass recurring-cadence
    coincidences (one of them a two-pass pair 13.8s under the 300s threshold) and only
    `20260714T120723Z` (101 passes, 5,871.7s, median gap 60.09s) is a real burst. The flag is
    ADVISORY: it changes no inclusion decision, it only stops "8 burst windows" being written
    down as if it meant eight bursts."""
    ordered = sorted(times.items(), key=lambda kv: (kv[1], kv[0]))
    if not ordered:
        return []
    runs: List[List[Tuple[str, datetime]]] = []
    cur: List[Tuple[str, datetime]] = [ordered[0]]
    for prev, nxt in zip(ordered, ordered[1:]):
        if (nxt[1] - prev[1]).total_seconds() <= max_interval_s:
            cur.append(nxt)
        else:
            runs.append(cur)
            cur = [nxt]
    runs.append(cur)

    windows: List[Dict[str, Any]] = []
    for run in runs:
        if len(run) < min_passes:
            continue
        gaps = [(b[1] - a[1]).total_seconds() for a, b in zip(run, run[1:])]
        duration_s = (run[-1][1] - run[0][1]).total_seconds()
        windows.append({
            "burst_id": run[0][0],
            "capture_ids": [cid for cid, _ in run],
            "start": run[0][1],
            "end": run[-1][1],
            "n_passes": len(run),
            "duration_s": duration_s,
            "median_gap_s": statistics.median(gaps) if gaps else None,
            "max_gap_s": max(gaps) if gaps else None,
            "cadence_qualified": bool(len(run) >= BURST_CADENCE_MIN_PASSES
                                      and duration_s >= BURST_CADENCE_MIN_DURATION_S),
        })
    return windows


def covers_release(window: Dict[str, Any], times: Dict[str, datetime],
                   release: datetime) -> bool:
    """A window covers the release iff >= 1 of its passes is strictly BEFORE it and >= 1 is
    strictly AFTER it. Straddling is the whole point — a burst that stops at 17:59 or starts at
    18:01 cannot measure a reprice lag."""
    before = any(times[cid] < release for cid in window["capture_ids"])
    after = any(times[cid] > release for cid in window["capture_ids"])
    return before and after


def parse_releases(text: str) -> List[datetime]:
    """One or more comma-separated ISO-8601 UTC release instants, sorted.

    MULTIPLE releases are the normal case once the strategy accumulates: only ONE maximal burst
    run can straddle a given instant, so reaching `MIN_BURSTS_FOR_CI` bursts requires that many
    DISTINCT instants, and a single-release invocation cannot reach the CI path.

    WHAT THIS DOES *NOT* GUARANTEE (corrected 2026-07-26; this docstring previously claimed the
    stronger thing): distinct instants are NOT necessarily distinct FOMC statements. Nothing
    here validates that an operator-supplied instant is a real event — no FOMC calendar is
    consulted, and none could be without a network call. Combined with
    `MIN_PASSES_PER_BURST_WINDOW = 2` at a 300s threshold, which lets an ordinary
    recurring-cadence PAIR register as a "burst window", a fabricated list of seven instants
    placed between ordinary recurring captures reached `verdict = "BOOTSTRAPPED (n_bursts=7)"`
    with a strictly positive CI on the committed tape. The refusal floor is ADVISORY on an
    operator-supplied list; the gates that actually held that output back are
    `bootstrap_verdict_admissible.admissible=False` and the per-window `cadence_qualified` flag
    / `bootstrap_cadence_warning` (see `detect_burst_windows`). `clears_tick_magnitude` is NOT
    one of them: it failed in the verifier's run only because that population still held
    sub-tick dust, and a re-run under the `MIN_ENTRY_EDGE` gate clears it."""
    out = [parse_iso_utc(part.strip()) for part in str(text).split(",") if part.strip()]
    return sorted(out)


def covering_release(window: Dict[str, Any], times: Dict[str, datetime],
                     releases: Sequence[datetime]) -> Optional[datetime]:
    """The earliest release instant this window straddles, or None. A window straddling two
    releases is attributed to the earlier one (and reported), never counted twice — double
    counting a single burst would fake the unit count the bootstrap depends on (L6)."""
    for release in releases:
        if covers_release(window, times, release):
            return release
    return None


def max_pass_density_per_hour(times: Dict[str, datetime],
                              window_seconds: float = DENSITY_WINDOW_SECONDS) -> int:
    """Largest number of distinct passes falling inside any `window_seconds` sliding window —
    the single number that says whether cadence anywhere in this tape could ever resolve a
    seconds-to-minutes reprice (S9 died on exactly this wall)."""
    ordered = sorted(times.values())
    best = 0
    lo = 0
    for hi in range(len(ordered)):
        while (ordered[hi] - ordered[lo]).total_seconds() > window_seconds:
            lo += 1
        best = max(best, hi - lo + 1)
    return best


# --------------------------------------------------------------------------- #
# observations (Hard Rule #3 aware)
# --------------------------------------------------------------------------- #
def _leg_tags(rec: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    kalshi = rec.get("kalshi") or {}
    poly = rec.get("polymarket") or {}
    return kalshi.get("price_source_tag"), poly.get("price_source_tag")


def ladder_sums(records: Sequence[Dict[str, Any]]
                ) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """Per (meeting, capture_id): the Kalshi `bracket_sum` across the buckets present in that
    pass and the Polymarket ladder sum across the same buckets, each with its member count, via
    `core.pricing.bracket_sum` (Hard Rule #3's sanctioned divisor site). A leg's sum is None
    when any bucket of that leg is missing a price in the pass — a partial ladder cannot
    normalize, and guessing the missing member would fabricate a probability."""
    kalshi_prices: Dict[Tuple[str, str], Dict[str, float]] = {}
    poly_prices: Dict[Tuple[str, str], Dict[str, float]] = {}
    incomplete: Dict[Tuple[str, str], set] = {}
    buckets_seen: Dict[str, set] = {}
    for rec in records:
        meeting = rec.get("meeting")
        cid = rec.get("capture_id")
        bucket = rec.get("bucket")
        if meeting is None or cid is None or bucket is None:
            continue
        key = (str(meeting), str(cid))
        buckets_seen.setdefault(str(meeting), set()).add(str(bucket))
        incomplete.setdefault(key, set())
        k_price = _as_float((rec.get("kalshi") or {}).get("yes_ask"))
        p_price = _as_float((rec.get("polymarket") or {}).get("best_ask"))
        if k_price is None:
            incomplete[key].add("kalshi")
        else:
            kalshi_prices.setdefault(key, {})[str(bucket)] = k_price
        if p_price is None or not (rec.get("polymarket") or {}).get("book_fetch_ok", True):
            incomplete[key].add("polymarket")
        else:
            poly_prices.setdefault(key, {})[str(bucket)] = p_price

    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for key in incomplete:
        meeting = key[0]
        expected = buckets_seen.get(meeting, set())
        k_members = kalshi_prices.get(key, {})
        p_members = poly_prices.get(key, {})
        k_ok = "kalshi" not in incomplete[key] and set(k_members) == expected and expected
        p_ok = "polymarket" not in incomplete[key] and set(p_members) == expected and expected
        out[key] = {
            "kalshi_bracket_sum": bracket_sum_fn(k_members.values()) if k_ok else None,
            "n_kalshi_buckets": len(k_members),
            "polymarket_bracket_sum": bracket_sum_fn(p_members.values()) if p_ok else None,
            "n_polymarket_buckets": len(p_members),
            "n_expected_buckets": len(expected),
        }
    return out


def build_observations(records: Sequence[Dict[str, Any]], times: Dict[str, datetime],
                       sums: Dict[Tuple[str, str], Dict[str, Any]]
                       ) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """One observation per (capture_id, ticker), carrying BOTH legs' real quotes, the ladder
    sums, and the raw + normalized gaps. De-dupes a repeated (capture_id, ticker) last-write-wins
    (tape is append-only; a re-emitted line is a rewrite-safe re-read, not a second observation).

    Every skip is COUNTED, never silent: a failed Polymarket book fetch, a missing leg price, an
    unparseable capture instant, or a leg whose `price_source_tag` is not `real_ask` (a synthetic
    price is never a fill — CLAUDE.md prime directive #1).
    """
    skipped = {
        "n_no_capture_time": 0,
        "n_book_fetch_failed": 0,
        "n_missing_kalshi_leg": 0,
        "n_missing_polymarket_leg": 0,
        "n_non_real_ask_tag": 0,
        "n_duplicate_capture_ticker": 0,
    }
    by_key: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for rec in records:
        cid = rec.get("capture_id")
        kalshi = rec.get("kalshi") or {}
        poly = rec.get("polymarket") or {}
        ticker = kalshi.get("ticker") or f"{rec.get('meeting')}|{rec.get('bucket')}"
        if cid is None or str(cid) not in times:
            skipped["n_no_capture_time"] += 1
            continue
        k_tag, p_tag = _leg_tags(rec)
        if k_tag != REQUIRED_TAG or p_tag != REQUIRED_TAG:
            skipped["n_non_real_ask_tag"] += 1
            continue
        if not poly.get("book_fetch_ok", True):
            skipped["n_book_fetch_failed"] += 1
            continue
        k_yes = _as_float(kalshi.get("yes_ask"))
        k_no = _as_float(kalshi.get("no_ask"))
        pm_ask = _as_float(poly.get("best_ask"))
        pm_bid = _as_float(poly.get("best_bid"))
        if k_yes is None or k_no is None:
            skipped["n_missing_kalshi_leg"] += 1
            continue
        if pm_ask is None or pm_bid is None:
            skipped["n_missing_polymarket_leg"] += 1
            continue
        key = (str(cid), str(ticker))
        if key in by_key:
            skipped["n_duplicate_capture_ticker"] += 1
        sum_key = (str(rec.get("meeting")), str(cid))
        ladder = sums.get(sum_key, {})
        k_sum = ladder.get("kalshi_bracket_sum")
        p_sum = ladder.get("polymarket_bracket_sum")
        norm_k = normalized_ask(k_yes, k_sum) if k_sum else None
        norm_p = normalized_ask(pm_ask, p_sum) if p_sum else None
        by_key[key] = {
            "capture_id": str(cid),
            "captured_at": times[str(cid)],
            "meeting": str(rec.get("meeting")),
            "bucket": str(rec.get("bucket")),
            "ticker": str(ticker),
            # Kalshi leg — the ONLY leg we would transact. real_ask / real bid-side.
            "kalshi_yes_price": k_yes,
            "kalshi_no_price": k_no,
            "kalshi_price_source_tag": k_tag,
            # Polymarket leg — exogenous SIGNAL ONLY, never a fill.
            "poly_ask_signal": pm_ask,
            "poly_bid_signal": pm_bid,
            "polymarket_price_source_tag": p_tag,
            "kalshi_bracket_sum": k_sum,
            "polymarket_bracket_sum": p_sum,
            "n_kalshi_buckets": ladder.get("n_kalshi_buckets"),
            "n_polymarket_buckets": ladder.get("n_polymarket_buckets"),
            "raw_gap": k_yes - pm_ask,
            "normalized_gap": (norm_k - norm_p) if (norm_k is not None and norm_p is not None)
            else None,
            "normalized_kalshi": norm_k,
            "normalized_polymarket": norm_p,
        }
    obs = sorted(by_key.values(), key=lambda o: (o["captured_at"], o["ticker"]))
    return obs, skipped


# --------------------------------------------------------------------------- #
# the single-leg taker edge (ONE Kalshi taker fee, charged as a cost)
# --------------------------------------------------------------------------- #
def gap_net_fee(obs: Dict[str, Any]) -> float:
    """Q48's named descriptive statistic: |raw ask-vs-ask gap| MINUS the single Kalshi taker fee
    at the Kalshi YES price. Descriptive — it is direction-blind, so it is NOT the trade edge."""
    return abs(obs["raw_gap"]) - fee_per_contract(obs["kalshi_yes_price"])


def entry_edge_candidate(obs: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The best directionally-agreeing candidate BEFORE the one-tick gate — exposed only so
    sub-tick candidates can be COUNTED rather than vanishing. Never use it as a trade: an edge
    of 8.67e-18 is floating-point residue, not a fill. See `entry_edge`."""
    norm_gap = obs.get("normalized_gap")
    if norm_gap is None:
        return None
    k_yes = obs["kalshi_yes_price"]
    k_no = obs["kalshi_no_price"]
    yes_edge = obs["poly_bid_signal"] - k_yes - fee_per_contract(k_yes)
    no_edge = (1.0 - obs["poly_ask_signal"]) - k_no - fee_per_contract(k_no)
    candidates: List[Dict[str, Any]] = []
    if norm_gap < 0 and yes_edge > 0:
        candidates.append({"direction": "BUY_YES", "price": k_yes,
                           "fee": fee_per_contract(k_yes), "edge": yes_edge})
    if norm_gap > 0 and no_edge > 0:
        candidates.append({"direction": "BUY_NO", "price": k_no,
                           "fee": fee_per_contract(k_no), "edge": no_edge})
    if not candidates:
        return None
    return max(candidates, key=lambda c: c["edge"])


def entry_edge(obs: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The executable single-leg entry edge, or None when no direction fires.

    Two directional taker trades, both at Kalshi `real_ask` prices, both charging exactly ONE
    Kalshi taker fee (`fee_per_contract`, taker default rate — Polymarket is a signal, not a
    leg, so no second fee):
      BUY_YES : edge = poly_bid_signal - kalshi_yes_price - fee(kalshi_yes_price)
      BUY_NO  : edge = (1 - poly_ask_signal) - kalshi_no_price - fee(kalshi_no_price)
    The CONSERVATIVE side of the Polymarket book is used in each direction (its bid when we need
    a lower bound on P(YES), its ask when we need an upper bound), so the signal is never read
    in the direction that flatters the trade.

    Fires only when the NORMALIZED gap (Hard Rule #3 — the only probability comparison) agrees
    with the direction AND the raw edge net of fee clears ONE TICK (`MIN_ENTRY_EDGE`), not a
    bare `> 0`: on the 2026-07-14 CPI dry-run a bare `> 0` admitted 9 of 24 "fired trades" at
    edges of 8.67e-18 / 1.73e-17 — float dust from `poly_bid - k_yes - fee` cancelling exactly,
    which then entered `unit_values` and the bootstrap. Sub-tick candidates are counted as
    `n_subtick_candidates_dropped` (see `analyze_unit`), never silently dropped. An observation
    with no normalized gap is normalization-unmeasurable -> None (excluded, never assumed
    tradeable).

    This is an ENTRY edge measured against an exogenous signal, NOT a settled P&L: settlement is
    `broker_truth` and does not exist in this tape for an undecided meeting. It may never be
    quoted as realized profit.
    """
    best = entry_edge_candidate(obs)
    if best is None or best["edge"] < MIN_ENTRY_EDGE:
        return None
    return best


# --------------------------------------------------------------------------- #
# per-burst analysis + the kill statistic
# --------------------------------------------------------------------------- #
def analyze_unit(pre_rows: Sequence[Dict[str, Any]], post: List[Dict[str, Any]],
                 release: datetime) -> Dict[str, Any]:
    """One (burst, meeting, bucket) unit: the post-release trajectory vs the signal, the max
    post-release |gap| net of the Kalshi taker fee, captures-until-Kalshi-first-moves, and the
    WALL-CLOCK duration of any (gap - fee) > 0 window (L76: never a snapshot count) — each of
    the last two now reported BOTH raw-absolute AND differenced against this unit's OWN
    pre-release baseline.

    `pre_rows` are ALL pre-release observations for this ticker inside the window, in time
    order (empty if the window has none for this ticker — then the first-move statistic AND the
    stale-window baseline are unmeasurable, reported as None, never as 0/False). The LAST of
    them is the reference quote for the first-move statistics; the whole set is the baseline
    for the stale window, because a unit that already carried a >fee cross-venue gap before the
    release has not been dislocated BY the release.
    """
    pre_rows = list(pre_rows)
    pre = pre_rows[-1] if pre_rows else None
    traj = [{
        "captured_at": o["captured_at"].isoformat(),
        "seconds_after_release": (o["captured_at"] - release).total_seconds(),
        "kalshi_yes_price": o["kalshi_yes_price"],
        "kalshi_no_price": o["kalshi_no_price"],
        "poly_ask_signal": o["poly_ask_signal"],
        "poly_bid_signal": o["poly_bid_signal"],
        "raw_gap": o["raw_gap"],
        "normalized_gap": o["normalized_gap"],
        "gap_net_fee": gap_net_fee(o),
    } for o in post]

    seconds: List[float] = []
    for idx, o in enumerate(post):
        if idx + 1 < len(post):
            seconds.append((post[idx + 1]["captured_at"] - o["captured_at"]).total_seconds())
        else:
            seconds.append(0.0)
    is_hit = [gap_net_fee(o) > 0.0 for o in post]
    runs = collapse_duration_gated_runs(is_hit, seconds,
                                        min_duration_seconds=STALE_WINDOW_MIN_SECONDS)
    stale_seconds = max([r["seconds"] for r in runs], default=0.0)
    persistent_absolute = any(r["executable"] for r in runs)

    # ── the unit's OWN pre-release baseline for the same two statistics. Without it, a permanent
    # cross-venue overround on an illiquid far-dated bucket reads as a release-caused stale
    # window (7 of 12 flagged units on the 2026-07-14 CPI burst were exactly that).
    pre_gaps = [gap_net_fee(o) for o in pre_rows]
    post_gaps = [gap_net_fee(o) for o in post]
    pre_frac_positive = (sum(1 for g in pre_gaps if g > 0.0) / len(pre_gaps)) if pre_gaps else None
    post_frac_positive = (sum(1 for g in post_gaps if g > 0.0) / len(post_gaps)
                          ) if post_gaps else None
    pre_max = max(pre_gaps) if pre_gaps else None
    post_max = max(post_gaps) if post_gaps else None
    excess_frac = (post_frac_positive - pre_frac_positive
                   if (pre_frac_positive is not None and post_frac_positive is not None) else None)
    excess_max = (post_max - pre_max
                  if (pre_max is not None and post_max is not None) else None)
    # ── THIN baseline (L180): a pre-period that exists but is too small to estimate either
    # baseline statistic. n_pre=1 confines the fraction to {0,1} and makes the max a single
    # draw, so one momentarily-tight pre-capture flips a PERMANENT overround into a
    # "release-caused" dislocation. Handled in the SAME unmeasurable class as no-pre-capture-at-
    # all (flag None, never True/False) plus its own explicit flag, so a thin baseline can never
    # CREATE a persistent-stale-window count.
    thin_baseline = bool(pre_rows) and len(pre_rows) < MIN_PRE_CAPTURES_FOR_BASELINE
    if not pre_rows or thin_baseline:
        # baseline UNMEASURABLE (absent) or INADEQUATE (thin) -> None, never a boolean. Not
        # counted as persistent anywhere, which biases toward the kill; that bias is reported,
        # not hidden.
        persistent_excess: Optional[bool] = None
    else:
        persistent_excess = bool(persistent_absolute
                                 and excess_frac is not None and excess_frac > 0.0
                                 and excess_max is not None
                                 # STRICTLY more than one tick on the 1c grid: the epsilon sits
                                 # on the THRESHOLD side, so an exactly-one-tick excess is scored
                                 # to the KILL side. A deliberate tightening of the ">= 1 tick"
                                 # rule, NOT a de-dusting — see the constants block (L180).
                                 and excess_max >= (STALE_WINDOW_MIN_EXCESS_DOLLARS
                                                    + STALE_WINDOW_EXCESS_EPSILON))

    first_move: Optional[int] = None
    if pre is not None:
        for idx, o in enumerate(post, start=1):
            if abs(o["kalshi_yes_price"] - pre["kalshi_yes_price"]) > 1e-12:
                first_move = idx
                break

    # ── the magnitude-qualified companion to `first_move` (which is magnitude-blind: a 1c tick
    # against a 10c Polymarket shock scores the same as full convergence). Measured against the
    # SAME pre-release reference quote, in the Polymarket move's own direction.
    half_move: Optional[int] = None
    poly_max_abs_move: Optional[float] = None
    if pre is not None:
        moves = [o["poly_ask_signal"] - pre["poly_ask_signal"] for o in post]
        poly_max_abs_move = max([abs(m) for m in moves], default=None)
        for idx, (o, pmove) in enumerate(zip(post, moves), start=1):
            if abs(pmove) < MIN_POLYMARKET_MOVE:
                continue            # no move to close -> this capture cannot qualify
            kmove = o["kalshi_yes_price"] - pre["kalshi_yes_price"]
            if kmove * (1.0 if pmove > 0 else -1.0) >= KALSHI_CATCHUP_FRACTION * abs(pmove):
                half_move = idx
                break

    fired = [e for e in (entry_edge(o) for o in post) if e is not None]
    cands = [c for c in (entry_edge_candidate(o) for o in post) if c is not None]
    n_subtick = sum(1 for c in cands if c["edge"] < MIN_ENTRY_EDGE)
    return {
        "n_post_captures": len(post),
        "n_pre_captures": len(pre_rows),
        "has_pre_release_observation": pre is not None,
        "pre_release_kalshi_yes_price": pre["kalshi_yes_price"] if pre else None,
        "pre_release_poly_ask_signal": pre["poly_ask_signal"] if pre else None,
        # ── ABSOLUTE (unbaselined) numbers, kept and clearly labelled
        "max_abs_gap_net_fee": post_max,
        "frac_gap_net_fee_positive": post_frac_positive,
        "stale_window_seconds": stale_seconds,
        "has_persistent_stale_window_absolute_unbaselined": persistent_absolute,
        # ── the unit's OWN pre-release baseline and the excess over it
        "pre_release_max_abs_gap_net_fee": pre_max,
        "pre_release_frac_gap_net_fee_positive": pre_frac_positive,
        "excess_max_abs_gap_net_fee": excess_max,
        "excess_frac_gap_net_fee_positive": excess_frac,
        "stale_window_baseline_measurable": bool(pre_rows),
        # ── the baseline's own n-adequacy (L180): present but too thin to difference against
        "thin_baseline": thin_baseline,
        "min_pre_captures_for_baseline": MIN_PRE_CAPTURES_FOR_BASELINE,
        "stale_window_baseline_adequate": bool(pre_rows) and not thin_baseline,
        # ── the flag the kill condition consumes: excess over baseline, None if unmeasurable
        "has_persistent_stale_window": persistent_excess,
        "captures_until_first_kalshi_move": first_move,
        "captures_until_kalshi_closed_half_of_polymarket_move": half_move,
        "polymarket_max_abs_move_vs_pre": poly_max_abs_move,
        "n_fired_trades": len(fired),
        "n_subtick_candidates_dropped": n_subtick,
        "fired_edges": [f["edge"] for f in fired],
        "fired_directions": [f["direction"] for f in fired],
        "trajectory": traj,
    }


def analyze_burst(window: Dict[str, Any], obs_by_capture: Dict[str, List[Dict[str, Any]]],
                  release: datetime) -> Dict[str, Any]:
    """All (meeting, bucket) units inside one covering burst window."""
    in_window: List[Dict[str, Any]] = []
    for cid in window["capture_ids"]:
        in_window.extend(obs_by_capture.get(cid, []))
    by_unit: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for o in in_window:
        by_unit.setdefault((o["meeting"], o["bucket"]), []).append(o)

    units: Dict[str, Any] = {}
    pre_release_prices: List[float] = []
    for (meeting, bucket), rows in sorted(by_unit.items()):
        rows.sort(key=lambda o: o["captured_at"])
        pre_rows = [o for o in rows if o["captured_at"] < release]
        post_rows = [o for o in rows if o["captured_at"] > release]
        if pre_rows:
            pre_release_prices.append(pre_rows[0]["kalshi_yes_price"])
        if not post_rows:
            continue
        units[f"{meeting}|{bucket}"] = analyze_unit(pre_rows, post_rows, release)
    return {
        "burst_id": window["burst_id"],
        "release": release.isoformat(),
        "start": window["start"].isoformat(),
        "end": window["end"].isoformat(),
        "n_passes": window["n_passes"],
        "median_gap_s": window["median_gap_s"],
        "duration_s": window["duration_s"],
        "cadence_qualified": window.get("cadence_qualified"),
        # L28 precheck on the EARLIEST (pre-release) Kalshi asks: a bucket already pinned at
        # the 1c YES floor has no room beneath it to be "stale cheap".
        "pre_release_floor_pinned_fraction": floor_pinned_fraction(pre_release_prices,
                                                                  YES_FLOOR_PRICE),
        "n_pre_release_prices": len(pre_release_prices),
        "units": units,
    }


def kill_condition(bursts: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Q48's kill condition, computed rather than asserted. DEAD-by-measurement iff Kalshi
    reprices within `KILL_MAX_CAPTURES_TO_REPRICE` captures of the release (median over the
    units that could measure it) AND no unit showed a persistent (>= STALE_WINDOW_MIN_SECONDS)
    positive gap-net-of-fee window IN EXCESS OF ITS OWN PRE-RELEASE BASELINE. Both components
    are reported separately, and the ABSOLUTE (unbaselined) persistence count is reported beside
    the baselined one so the difference between "there is a gap" and "the release opened a gap"
    is visible.

    With ZERO units, `no_persistent_stale_window` and `kill_condition_met` are None, never a
    vacuous True/False — an empty population is not evidence of anything. THE SAME APPLIES WITH
    ZERO **MEASURABLE** UNITS: an n-adequacy floor (`MIN_PRE_CAPTURES_FOR_BASELINE`) does not
    remove vacuity, it relocates it — every thin-baselined unit becomes a None flag, and a
    population that is entirely None would otherwise satisfy `n_persistent == 0` and fire a hard
    "S55 is dead" from a population in which nothing was measurable. The guard is therefore on
    `n_units_with_measurable_stale_window_baseline` (units whose flag is a real True/False), not
    on `n_units`."""
    first_moves: List[int] = []
    half_moves: List[int] = []
    n_units = 0
    n_persistent = 0
    n_persistent_absolute = 0
    n_baseline_unmeasurable = 0
    n_thin_baseline = 0
    n_never_moved = 0
    n_never_closed_half = 0
    for b in bursts:
        for unit in b["units"].values():
            n_units += 1
            if unit.get("has_persistent_stale_window_absolute_unbaselined"):
                n_persistent_absolute += 1
            flag = unit["has_persistent_stale_window"]
            if flag is None:
                # the two None causes PARTITION the None flags (a thin baseline always has
                # >= 1 pre-capture, an unmeasurable one has zero), so nothing is double-counted
                # and neither can ever land in `n_persistent`.
                if unit.get("thin_baseline"):
                    n_thin_baseline += 1
                else:
                    n_baseline_unmeasurable += 1
            elif flag:
                n_persistent += 1
            fm = unit["captures_until_first_kalshi_move"]
            if fm is None:
                if unit["has_pre_release_observation"]:
                    n_never_moved += 1
            else:
                first_moves.append(fm)
            hm = unit.get("captures_until_kalshi_closed_half_of_polymarket_move")
            if hm is None:
                if unit["has_pre_release_observation"]:
                    n_never_closed_half += 1
            else:
                half_moves.append(hm)
    median_first_move = statistics.median(first_moves) if first_moves else None
    median_half_move = statistics.median(half_moves) if half_moves else None
    reprices_fast = (median_first_move is not None
                     and median_first_move <= KILL_MAX_CAPTURES_TO_REPRICE)
    # units whose `has_persistent_stale_window` is a real True/False. `n_units` is NOT the right
    # denominator for the kill: raising MIN_PRE_CAPTURES_FOR_BASELINE moved units OUT of the
    # measurable set (into None), so gating on `n_units` would let an all-thin population report
    # `n_persistent == 0` as a hard "no stale window anywhere".
    n_measurable = n_units - n_thin_baseline - n_baseline_unmeasurable
    no_persistent = (n_persistent == 0) if n_measurable else None
    return {
        "n_units": n_units,
        "n_units_with_measurable_stale_window_baseline": n_measurable,
        "n_units_with_persistent_stale_window": n_persistent,
        "n_units_with_persistent_stale_window_absolute_unbaselined": n_persistent_absolute,
        "n_units_stale_window_baseline_unmeasurable": n_baseline_unmeasurable,
        "n_units_with_thin_stale_window_baseline": n_thin_baseline,
        "n_units_never_repriced_in_window": n_never_moved,
        "n_units_never_closed_half_of_polymarket_move": n_never_closed_half,
        "median_captures_until_first_kalshi_move": median_first_move,
        "median_captures_until_kalshi_closed_half_of_polymarket_move": median_half_move,
        "first_move_note": (
            "`captures_until_first_kalshi_move` is MAGNITUDE-BLIND (any move > 1e-12 counts, so "
            "a 1c tick against a 10c Polymarket shock scores 1, same as full convergence). Its "
            "bias is toward the KILL — it makes Kalshi look faster than it is — which is the "
            "safe direction here, but it must never be read as 'Kalshi caught up'. The "
            "magnitude-qualified companion is "
            "`median_captures_until_kalshi_closed_half_of_polymarket_move` (first capture at "
            "which Kalshi moved, in Polymarket's direction, >= half of Polymarket's own move "
            "vs the same pre-release quote; None where Polymarket never moved >= 1 tick)."),
        "stale_window_note": (
            "`n_units_with_persistent_stale_window` is BASELINED: it counts only units whose "
            "post-release >fee window EXCEEDS that unit's own pre-release fraction of >fee "
            "captures AND whose post-release max gap exceeds its pre-release max by STRICTLY "
            "MORE THAN ONE TICK. The implementation is `excess_max >= "
            f"STALE_WINDOW_MIN_EXCESS_DOLLARS ({STALE_WINDOW_MIN_EXCESS_DOLLARS}) + "
            f"STALE_WINDOW_EXCESS_EPSILON ({STALE_WINDOW_EXCESS_EPSILON})`, and because both "
            "legs quote on a 1c grid the EFFECTIVE requirement is `> 1 tick`: an excess of "
            "EXACTLY one tick is scored to the KILL side (flag False), not counted here. That "
            "is a deliberate tightening of the earlier '>= 1 tick' rule — the epsilon removes no "
            "float dust (the residues this arithmetic produces are ~1e-17, seven orders below "
            "the threshold), it moves the boundary case. On the 2026-07-14 CPI dry-run the "
            "tightening is the whole difference between 3 units (this code) and 4 (the '>= 1 "
            "tick' rule); the 4th, `2026-10|cut_25`, carried an excess of exactly one tick in "
            "exact arithmetic. The unbaselined count is reported beside this one; on that same "
            "burst the absolute rule flagged 12 units of which 7 had a >fee gap on 100% of "
            "their PRE-release captures — a standing overround, not a release lag. Units with "
            "no pre-release capture have an UNMEASURABLE baseline (flag None) and are excluded "
            "from the persistent count, which biases toward the kill. So are units with a THIN "
            f"baseline (1 <= n_pre < MIN_PRE_CAPTURES_FOR_BASELINE={MIN_PRE_CAPTURES_FOR_BASELINE}"
            "), counted separately as `n_units_with_thin_stale_window_baseline`: at n_pre=1 the "
            "pre-release fraction is confined to {0,1} and the pre-release max is a single "
            "draw, so one momentarily-tight pre-capture would turn a permanent overround into a "
            "'release-caused' dislocation (L180). A thin baseline can never CREATE a persistent "
            "count — and, symmetrically, it can never create an ABSENCE of one: "
            "`no_persistent_stale_window` (and so `kill_condition_met`) is None whenever "
            "`n_units_with_measurable_stale_window_baseline` is 0, because a floor on baseline "
            "adequacy relocates vacuity rather than removing it."),
        "reprices_within_one_capture": reprices_fast,
        "no_persistent_stale_window": no_persistent,
        "kill_condition_met": (bool(reprices_fast and no_persistent)
                               if no_persistent is not None else None),
        "stale_window_min_seconds": STALE_WINDOW_MIN_SECONDS,
        "stale_window_min_excess_dollars": STALE_WINDOW_MIN_EXCESS_DOLLARS,
        "stale_window_excess_epsilon": STALE_WINDOW_EXCESS_EPSILON,
        "min_pre_captures_for_baseline": MIN_PRE_CAPTURES_FOR_BASELINE,
        "kill_max_captures_to_reprice": KILL_MAX_CAPTURES_TO_REPRICE,
        "kalshi_catchup_fraction": KALSHI_CATCHUP_FRACTION,
    }


# --------------------------------------------------------------------------- #
# steady-state baseline (non-burst passes)
# --------------------------------------------------------------------------- #
def _stats(values: Sequence[float]) -> Dict[str, Any]:
    if not values:
        return {"n": 0, "mean": None, "median": None, "mean_abs": None, "median_abs": None}
    return {
        "n": len(values),
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "mean_abs": statistics.mean([abs(v) for v in values]),
        "median_abs": statistics.median([abs(v) for v in values]),
    }


def steady_state_baseline(observations: Sequence[Dict[str, Any]], burst_capture_ids: set,
                          front_meetings: Sequence[str]) -> Dict[str, Any]:
    """The NON-burst steady-state gap, all-meetings and front-meeting-only.

    Both legs are `real_ask` (Kalshi `yes_ask` off its own book, Polymarket `best_ask` off the
    CLOB) — the tags observed in tape are reported, not assumed. Raw and normalized (Hard Rule
    #3) are both given. This is the number Q48 quotes as ~=0.6c; whatever it actually comes out
    at is what gets reported."""
    rows = [o for o in observations if o["capture_id"] not in burst_capture_ids]
    front_set = set(front_meetings or ())
    front = [o for o in rows if o["meeting"] in front_set]
    tags = sorted({(o["kalshi_price_source_tag"], o["polymarket_price_source_tag"])
                   for o in rows})

    def cut(subset: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        raw = [o["raw_gap"] for o in subset]
        norm = [o["normalized_gap"] for o in subset if o["normalized_gap"] is not None]
        return {
            "raw_gap": _stats(raw),
            "normalized_gap": _stats(norm),
            "n_normalization_unmeasurable": len(subset) - len(norm),
            "kalshi_yes_floor_pinned_fraction": floor_pinned_fraction(
                [o["kalshi_yes_price"] for o in subset], YES_FLOOR_PRICE),
        }

    return {
        "definition": ("every observation whose pass is NOT inside a detected burst window "
                       f"(inter-pass interval <= {BURST_MAX_INTERVAL_S:.0f}s)"),
        "price_source_tags_observed": [{"kalshi": k, "polymarket": p} for k, p in tags],
        "gap_definition": ("kalshi.yes_ask MINUS polymarket.best_ask (both real_ask), in "
                           "dollars — same sign convention as the tape's own "
                           "`price_gap_yes_ask` field"),
        "normalized_gap_note": (
            "MECHANICAL IDENTITY, read the mean with care: both ladders are normalized to sum "
            "to 1.0 over the SAME bucket set, so the normalized gaps of a complete pass sum to "
            "exactly 0 and the pooled MEAN normalized gap is ~0 by construction, not by "
            "agreement (same class of trap as L51's complementary hit rates). Only the "
            "per-observation magnitude (mean_abs/median_abs) and the per-bucket sign carry "
            "information; the raw-gap mean is the one that can be non-zero, because each "
            "venue's overround is its own."),
        "all_meetings": cut(rows),
        "front_meetings": sorted(front_set),
        "front_meeting_only": cut(front),
        "n_burst_observations_excluded": len(observations) - len(rows),
    }


# --------------------------------------------------------------------------- #
# orchestration
# --------------------------------------------------------------------------- #
def front_meeting_key(release: datetime) -> str:
    """The meeting the release actually decides: `YYYY-MM` of the release instant (the tape's
    own `meeting` key format). Derived from the release timestamp, never hardcoded."""
    return f"{release.year:04d}-{release.month:02d}"


def run_probe(tape_dir: Path = DEFAULT_TAPE_DIR, *, release_ts: str = DEFAULT_RELEASE_TS,
              family: str = DEFAULT_FAMILY,
              min_bursts_for_ci: int = MIN_BURSTS_FOR_CI) -> Dict[str, Any]:
    """End-to-end, read-only. The data-adequacy gate runs FIRST: with zero burst windows
    covering the release — OR zero surviving priced observations — the report is INSUFFICIENT
    DATA and NO edge/CI claim is produced. Both halves are required: an all-`midpoint` tape
    leaves every covering window populated by ZERO observations, which without the
    `n_observations > 0` clause still reached `status="ANALYSIS"` with a vacuous
    `no_persistent_stale_window=True` and a `bootstrap.mean=null` "BOOTSTRAPPED" verdict."""
    releases = parse_releases(release_ts)
    records, skips = load_family_records(Path(tape_dir), family)
    times, n_no_time = pass_times(records)
    windows = detect_burst_windows(times)
    covering: List[Tuple[Dict[str, Any], datetime]] = []
    for w in windows:
        rel = covering_release(w, times, releases)
        if rel is not None:
            covering.append((w, rel))
    front_meetings = sorted({front_meeting_key(r) for r in releases})

    report: Dict[str, Any] = {
        "probe": "q48_s55_fomc_lag_probe",
        "queue_item": "Q48 / S55",
        "tape_dir": str(tape_dir),
        "family": family,
        "release_ts": release_ts,
        "releases": [r.isoformat() for r in releases],
        "front_meetings": front_meetings,
        "fee_model": {
            "legs_charged": 1,
            "which_leg": "Kalshi taker only (Polymarket is an exogenous signal, never traded)",
            "source": "core.pricing.fee_per_contract",
            "rate": TAKER_FEE_RATE,
            "rate_name": "TAKER_FEE_RATE",
            "direction": "charged as a COST, subtracted from every edge",
        },
        "depth_unmeasurable": DEPTH_UNMEASURABLE,
        "depth_note": ("polymarket_macro_pairs.v1 carries NO size/depth field on either leg "
                       "(L57 — this family is size-blind), so at-touch depth is UNMEASURABLE "
                       "and no edge found here may be called fillable on this tape alone."),
        "n_fed_records": len(records),
        "n_passes": len(times),
        "n_burst_windows": len(windows),
        "n_burst_windows_cadence_qualified": sum(1 for w in windows if w["cadence_qualified"]),
        "n_burst_windows_marginal": sum(1 for w in windows if not w["cadence_qualified"]),
        "n_covering_burst_windows": len(covering),
        "n_covering_burst_windows_cadence_qualified": sum(
            1 for w, _ in covering if w["cadence_qualified"]),
        "burst_cadence_note": (
            f"a detected window is `cadence_qualified` only at >= {BURST_CADENCE_MIN_PASSES} "
            f"passes AND >= {BURST_CADENCE_MIN_DURATION_S:.0f}s wall-clock. `n_burst_windows` "
            f"counts every maximal run under the {BURST_MAX_INTERVAL_S:.0f}s threshold, "
            f"INCLUDING ordinary recurring-cadence pairs — on the committed tape 7 of 8 are "
            f"such coincidences (2-5 passes, 57.5-288.5s) and only 20260714T120723Z (101 "
            f"passes, 5,871.7s) is a real burst. Never write `n_burst_windows` into a log as "
            f"if it were a burst count; quote the split."),
        "max_pass_density_per_hour": max_pass_density_per_hour(times),
        "burst_max_interval_s": BURST_MAX_INTERVAL_S,
        "min_passes_per_burst_window": MIN_PASSES_PER_BURST_WINDOW,
        "burst_cadence_min_passes": BURST_CADENCE_MIN_PASSES,
        "burst_cadence_min_duration_s": BURST_CADENCE_MIN_DURATION_S,
        "min_bursts_for_ci": min_bursts_for_ci,
        "min_entry_edge": MIN_ENTRY_EDGE,
        # the two exit-side numerical-adequacy constants, on the face of every report (L180)
        "min_pre_captures_for_baseline": MIN_PRE_CAPTURES_FOR_BASELINE,
        "stale_window_excess_epsilon": STALE_WINDOW_EXCESS_EPSILON,
        "load_skips": dict(skips, n_records_without_capture_time=n_no_time),
        "burst_windows": [{
            "burst_id": w["burst_id"], "start": w["start"].isoformat(),
            "end": w["end"].isoformat(), "n_passes": w["n_passes"],
            "median_gap_s": w["median_gap_s"], "duration_s": w["duration_s"],
            "cadence_qualified": w["cadence_qualified"],
            "covered_release": (lambda r: r.isoformat() if r else None)(
                covering_release(w, times, releases)),
        } for w in windows],
    }

    sums = ladder_sums(records)
    observations, obs_skips = build_observations(records, times, sums)
    report["n_observations"] = len(observations)
    report["observation_skips"] = obs_skips
    # Report-level provenance over ALL surviving observations (the baseline's own tag list
    # covers NON-burst passes only). Empty list == no priced observation survived the
    # `real_ask` gate; the human one-liner renders FROM this, never from a hardcoded string.
    report["price_source_tags_observed"] = [
        {"kalshi": k, "polymarket": p} for k, p in
        sorted({(o["kalshi_price_source_tag"], o["polymarket_price_source_tag"])
                for o in observations})]

    burst_capture_ids = {cid for w in windows for cid in w["capture_ids"]}
    report["baseline"] = steady_state_baseline(observations, burst_capture_ids, front_meetings)
    report["rerun_command"] = (
        f"python3 scripts/q48_s55_fomc_lag_probe.py --baseline "
        f"--tape-dir {tape_dir} --family {family} --release-ts {release_ts}")

    if not covering or not observations:
        report["status"] = "INSUFFICIENT DATA"
        reasons: List[str] = []
        if not covering:
            reasons.append(
                f"Q48 needs >= 1 burst window (consecutive passes <= "
                f"{BURST_MAX_INTERVAL_S:.0f}s apart) with at least one pass strictly BEFORE and "
                f"one strictly AFTER a release instant "
                f"({', '.join(r.isoformat() for r in releases)}); found {len(windows)} burst "
                f"window(s) ({report['n_burst_windows_cadence_qualified']} cadence-qualified), "
                f"0 covering.")
        if not observations:
            reasons.append(
                f"ZERO priced observations survived the adequacy gate out of {len(records)} "
                f"records — every observation was skipped "
                f"({json.dumps(obs_skips, sort_keys=True)}); with no `{REQUIRED_TAG}`-tagged "
                f"pair on both legs there is nothing to measure, and any kill/stale-window "
                f"statement over an empty population would be vacuous.")
        report["reason"] = (" ALSO: ".join(reasons)
                            + " Prep script — no analysis run, no edge claim, no CI, no verdict.")
        report["verdict"] = None
        return report

    obs_by_capture: Dict[str, List[Dict[str, Any]]] = {}
    for o in observations:
        obs_by_capture.setdefault(o["capture_id"], []).append(o)
    bursts = [analyze_burst(w, obs_by_capture, rel) for w, rel in covering]
    report["status"] = "ANALYSIS"
    report["bursts"] = bursts
    report["kill_condition"] = kill_condition(bursts)

    unit_values: Dict[str, List[float]] = {}
    n_subtick = 0
    for b in bursts:
        vals: List[float] = []
        for unit in b["units"].values():
            vals.extend(unit["fired_edges"])
            n_subtick += unit["n_subtick_candidates_dropped"]
        unit_values[b["burst_id"]] = vals
    n_bursts = len(unit_values)
    report["n_bursts"] = n_bursts
    report["n_fired_trades"] = sum(len(v) for v in unit_values.values())
    report["n_subtick_candidates_dropped"] = n_subtick
    report["subtick_note"] = (
        f"a directionally-agreeing candidate must clear MIN_ENTRY_EDGE={MIN_ENTRY_EDGE} (one "
        f"tick) to fire; {n_subtick} candidate(s) were dropped as sub-tick float residue and "
        f"never entered the bootstrap population.")

    if n_bursts < min_bursts_for_ci:
        report["verdict"] = (f"DESCRIPTIVE ONLY (n_bursts={n_bursts} < "
                             f"MIN_BURSTS_FOR_CI={min_bursts_for_ci})")
        report["bootstrap"] = None
        report["bootstrap_note"] = (
            "No bootstrap run: the independent unit is the BURST (L6), and a block-bootstrap "
            "by burst is admissible only across several settled FOMC meetings. Reporting a CI "
            "off one release would fake n by ~15 records/pass.")
        return report

    boot = block_bootstrap(unit_values, n_boot=N_BOOT, seed=BOOTSTRAP_SEED)
    # The label travels INSIDE the emitted object, because the emitted object is what gets
    # quoted — `entry_edge`'s docstring is not attached to a pasted JSON blob.
    boot = dict(boot, bootstrap_statistic=(
        "entry gap vs exogenous Polymarket signal (real_ask both legs), NOT settled P&L"))
    report["bootstrap"] = boot
    report["bootstrap_unit"] = "burst window (one FOMC release)"
    report["bootstrap_verdict_admissible"] = bootstrap_verdict_admissible(unit_values)
    report["clears_tick_magnitude"] = clears_tick_magnitude(boot["ci95"], tick=PRICE_TICK)
    n_marginal = sum(1 for w, _ in covering if not w["cadence_qualified"])
    report["bootstrap_cadence_warning"] = (
        None if n_marginal == 0 else
        f"{n_marginal} of {len(covering)} covering window(s) are NOT burst cadence "
        f"(< {BURST_CADENCE_MIN_PASSES} passes or < {BURST_CADENCE_MIN_DURATION_S:.0f}s): this "
        f"CI is built partly on ordinary recurring-cadence pairs that happened to straddle a "
        f"supplied instant. Nothing here validates that a supplied instant is a real release; "
        f"an operator-supplied list of fabricated instants can reach this path.")
    report["verdict"] = (
        f"BOOTSTRAPPED (n_bursts={n_bursts}) — CI and both gates reported; a live edge claim "
        f"additionally requires admissibility, the tick-magnitude gate, MEASURABLE DEPTH "
        f"(absent from this schema) and the two-agent rule.")
    return report


# --------------------------------------------------------------------------- #
# reporting
# --------------------------------------------------------------------------- #
def _c(v: Optional[float]) -> str:
    return "None" if v is None else f"{v * 100:+.3f}c"


def provenance_string(rep: Dict[str, Any]) -> str:
    """The one-liner's price-provenance bracket, rendered FROM the observed tags — never a
    hardcoded `[real_ask both legs]`.

    The one-liner is the line most likely to be pasted into `kb/00-LOG.md`, so it is exactly
    where CLAUDE.md's untagged->synthetic default must not be silently re-opened: a run with
    zero surviving observations (e.g. `--family nope`, or an all-`midpoint` tape) has an EMPTY
    tag list and must say so, not assert `real_ask`."""
    tags = rep.get("price_source_tags_observed")
    if tags is None:
        tags = (rep.get("baseline") or {}).get("price_source_tags_observed") or []
    if not tags:
        return "[no priced observations]"
    parts = sorted({f"kalshi={t.get('kalshi')}/polymarket={t.get('polymarket')}" for t in tags})
    return "[" + "; ".join(parts) + "]"


def human_one_liner(rep: Dict[str, Any]) -> str:
    base = rep["baseline"]["all_meetings"]["raw_gap"]
    front = rep["baseline"]["front_meeting_only"]["raw_gap"]
    fronts = ",".join(rep["front_meetings"]) or "none"
    prov = provenance_string(rep)
    windows = (f"{rep['n_burst_windows']} burst windows "
               f"({rep['n_burst_windows_cadence_qualified']} cadence-qualified)")
    if rep.get("status") == "INSUFFICIENT DATA":
        return (f"[q48/s55] INSUFFICIENT DATA — {rep['n_fed_records']} {rep['family']} records / "
                f"{rep['n_passes']} passes / {rep['n_observations']} observations / {windows}, "
                f"{rep['n_covering_burst_windows']} covering "
                f"{'/'.join(rep['releases'])} (max {rep['max_pass_density_per_hour']} passes/h). "
                f"Steady-state |gap| all={_c(base['mean_abs'])} "
                f"front({fronts})={_c(front['mean_abs'])} {prov}; "
                f"no edge claim, no CI.")
    kc = rep["kill_condition"]
    return (f"[q48/s55] {rep['status']} — n_bursts={rep.get('n_bursts')} "
            f"({rep['n_covering_burst_windows_cadence_qualified']} cadence-qualified), "
            f"fired={rep.get('n_fired_trades')} (sub-tick dropped="
            f"{rep.get('n_subtick_candidates_dropped')}), "
            f"persistent_stale_windows={kc['n_units_with_persistent_stale_window']}/"
            f"{kc['n_units']} (thin baseline="
            f"{kc['n_units_with_thin_stale_window_baseline']}, baseline unmeasurable="
            f"{kc['n_units_stale_window_baseline_unmeasurable']}), "
            f"kill_condition_met={kc['kill_condition_met']}, {prov}, "
            f"verdict={rep.get('verdict')}")


def print_report(rep: Dict[str, Any], *, json_only: bool = False,
                 baseline_only: bool = False) -> None:
    if json_only:
        print(json.dumps(rep, indent=2, default=str))
        return
    if baseline_only:
        print(json.dumps({"probe": rep["probe"], "queue_item": rep["queue_item"],
                          "tape_dir": rep["tape_dir"], "family": rep["family"],
                          "release_ts": rep["release_ts"],
                          "releases": rep["releases"],
                          "front_meetings": rep["front_meetings"],
                          "n_fed_records": rep["n_fed_records"],
                          "n_passes": rep["n_passes"],
                          "n_burst_windows": rep["n_burst_windows"],
                          "n_burst_windows_cadence_qualified":
                              rep["n_burst_windows_cadence_qualified"],
                          "n_observations": rep["n_observations"],
                          "observation_skips": rep["observation_skips"],
                          "price_source_tags_observed": rep["price_source_tags_observed"],
                          "baseline": rep["baseline"],
                          "rerun_command": rep["rerun_command"]},
                         indent=2, default=str))
        print(human_one_liner(rep))
        return
    print(json.dumps(rep, indent=2, default=str))
    print(human_one_liner(rep))


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=("Q48/S55 post-release single-leg Kalshi-lag taker probe on FOMC "
                     "(prep; read-only; no network)"))
    ap.add_argument("--tape-dir", default=str(DEFAULT_TAPE_DIR),
                    help="dir holding polymarket_macro_pairs dt=*.jsonl (default: committed tape)")
    ap.add_argument("--release-ts", default=DEFAULT_RELEASE_TS,
                    help=("release instant(s), ISO-8601 UTC, comma-separated for several FOMC "
                          "statements (default: the 2026-07-29 18:00Z statement). Only one "
                          "burst window can straddle a given instant, so reaching "
                          f"MIN_BURSTS_FOR_CI={MIN_BURSTS_FOR_CI} requires that many meetings."))
    ap.add_argument("--family", default=DEFAULT_FAMILY,
                    help="tape `family` value to analyze (default: fed_decision)")
    ap.add_argument("--baseline", action="store_true",
                    help="print ONLY the non-burst steady-state baseline section")
    ap.add_argument("--json", action="store_true",
                    help="print ONLY the JSON summary object (no human line)")
    args = ap.parse_args(argv)

    rep = run_probe(Path(args.tape_dir), release_ts=args.release_ts, family=args.family)
    print_report(rep, json_only=args.json, baseline_only=args.baseline and not args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
