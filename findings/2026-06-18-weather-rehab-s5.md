# S5 weather rehab — real-ask paper test: the weather family is DEAD on this sample

`tested` · 2026-06-18 · settles strategy candidate **S5** (kb/strategies/00-index.md) ·
probe: `scripts/weather_rehab_s5.py` · result dump: `reports/weather_rehab_s5_full.json`

## The question

The directional weather signal is real (arb-bot's KXHIGH had a genuine signal) but the
*dollar* edge died to overround at real asks (S1 longshot fade confirmed this). S5 asks the
last open question of the weather family: does an **EMOS-CALIBRATED** predictive probability
(not the raw underdispersed ensemble) clear the fee+overround bar at **real, fillable asks**?
A null result was the expected, valuable outcome — it declares the weather family dead and
pivots the project to S2/S3/S6.

## Verdict (HONEST)

**The lower bootstrap CI bound does NOT clear zero. The weather family is DEAD on this
sample. Pivot to S2/S3/S6.**

- Net per-trade P&L = **−$0.02789** (a *loss*).
- 95% moving-block-bootstrap CI = **[−$0.06297, +$0.00788]** (n_boot=10,000, 21 contract-day
  blocks). The mean is negative and the CI is mostly below zero; it does not strictly clear
  zero, so by the prime directive there is no edge to graduate.
- n = **641 trades** across **165 usable (city, day) groups**, 8 cities, 21 contract-days.

This is not a near-miss in the right direction — the point estimate is a *loss*, and raising
the conviction bar makes it worse, not better (see adversarial checks). The directional
signal does not survive the real-ask overround + taker fee.

## Calibration sanity check (CRPS, lower is better)

Pooled over all held-out leave-one-day-out folds (8 cities × 21 days):

| forecast | held-out mean CRPS |
|---|---:|
| raw 3-model ensemble (N(ens_mean, ens_sd)) | 2.3658 |
| **EMOS, LOO-calibrated** | **2.1799** |

EMOS **improves** pooled calibration by **+7.86%** — i.e. post-processing does fix the raw
ensemble's underdispersion, exactly as the literature (Gneiting et al. 2005) and
`scripts/emos_demo.py` predict. The calibration thesis is upheld. **A better-calibrated
probability was necessary but not sufficient: it still does not clear the overround at the
fillable ask.** That is the whole point of S5, and it failed at the dollar step, not the
calibration step. (Per single city the CRPS improvement is noisy — Chicago alone showed EMOS
slightly *worse* (−4.25%) on only 21 days — because a 3-model ensemble fit on ~21 spring days
is data-thin; pooled across cities the underdispersion correction dominates.)

## The killer: overround

Mean **overround_absorbed = 0.0984** (median 0.10) at the real asks at decision time — the
bracket asks summed to ~$1.10. That ~10c structural taker cost across the 6-bracket ladder is
the same tax that ate arb-bot's pt1 and S1. An EMOS edge would have to exceed ~10c of true-vs-
fillable probability *per bracket* to overcome it, and on this sample it does not.

## Method (what was actually run)

- **Decision time** T := close_T(group) − 24h, where close_T is the latest 'ticker'-event ts
  across the group's 6 brackets (the real market close). Identical definition to
  `scripts/longshot_fade_probe.py`. Empirically T ≈ contract-day D, 04:00–06:00 UTC.
- **Real asks** reconstructed from the tape's self-contained 'ticker' BBO
  (`yes_ask_dollars`/`yes_bid_dollars`), the exchange's own published taker price, at the most
  recent event AT OR BEFORE T (strictly causal). `price_source_tag = "real_ask"`. Market
  implied prob via `core.pricing.normalized_ask` (Hard Rule #3 — overround removed by the
  bracket_sum divisor). A group is usable only if all 6 brackets have a book at T.
- **Anti-leak forecast** (the load-bearing control): **Open-Meteo Single Runs API**, run
  pinned to the **(D−1) 00:00 UTC** model run — issued ~D−1 04–06Z, comfortably before T.
  A hard guard asserts run_init < T for every group (0 violations). The Historical-Forecast
  archive was deliberately **NOT** used: it stitches lead≈0 hours (a near-nowcast/near-actual)
  and would leak the answer for a day-ahead decision — venues.yaml warns about exactly this.
- **Ensemble** = GFS + ECMWF-IFS025 + ICON (3 models). GEM (`gem_global`/cmc_gem_gdps) single-
  runs are not archived for Apr–May 2026, so it is **honestly dropped, not substituted** →
  member_count = 3. (Hard Rule #1: `ncep_gefs025` is never in the list.) The 3-member ensemble
  variance feeds EMOS as a spread regressor only — never `core.stats.safe_pstdev` (whose n≥4
  guard, Hard Rule #2, is reserved for sizing signals).
- **EMOS** generalises `scripts/emos_demo.py`: predictive mean = ens_mean + CRPS-optimal bias
  correction; predictive variance = a + b·ens_var, (a,b) minimising closed-form Gaussian CRPS.
  Fit by **leave-one-day-out CV** — each day's trades use coefficients fit on all *other* days,
  so a day is never fit and evaluated on itself. (Pre-registered fallback for folds with <5
  train days: μ = ens_mean, σ = 2.5·max(ens_sd, 1.5°F). All 21 folds had enough data → EMOS
  used, 0 fallback.) The EMOS training *target* is the settled bracket's realized-Tmax
  midpoint — hindsight used only to fit calibration coefficients on other days, never on the
  traded day and never as a price.
- **Bracket probability** = ∫ predictive Gaussian over [lo, hi), bounds from the authoritative
  settlement strike fields with half-degree integer-rounding: band lo..hi → [lo−0.5, hi+0.5);
  "<X" → (−∞, X−0.5); ">X" → [X+0.5, ∞). Φ via math.erf, no scipy.
- **Trade rule + honest no-mid fill:** trade a bracket only when |model_prob −
  market_implied| > **0.05** (the fee+overround bar). Underpriced → BUY YES by lifting the real
  YES ask; overpriced → BUY NO by lifting the real NO ask (= one minus the best YES bid). Buy at
  the ask, settle $1/$0 — **never** a mid. Taker fee = roundup_cent(0.07·p·(1−p)) on entry.
  No fill-probability haircut (optimistic direction — so a null is robust).
- **Bootstrap:** moving-block by contract-day (intra-day brackets share one weather
  realization), 10,000 resamples → 95% CI.

## n / drops (honest completeness)

- 176 groups total → **165 usable**. Drops: 11 incomplete-book-at-T (book missing for ≥1 of
  the 6 brackets at T → 51 brackets had no book), 0 no-close, 0 crossed, 0 no-forecast,
  **0 leak-guard** (the pinned run was always before T).
- 1,056 brackets total; 0 had ask≥1 at T; 0 crossed.
- From 165 usable groups, 641 trades cleared the |edge|>0.05 bar (338 BUY-YES, 303 BUY-NO).

## Per-trade provenance (CLAUDE.md trust defaults)

Every trade persists `raw_yes_ask`, `bracket_sum`, `overround_absorbed`, `member_count`,
`models_json` (the 3 model Tmax values), and `price_source_tag = "real_ask"`. Verified
present on every row in the JSON dump. Example: `models_json =
{"gfs_seamless": 88.1, "ecmwf_ifs025": 88.5, "icon_seamless": 88.8}`.

## Adversarial checks (I distrusted the result and tried to break it)

The CI did not produce a false positive (the mean is a loss), but per the prime directive I
ran the falsification battery anyway — and also checked the result is not an artifact masking
a real edge:

1. **Edge-bar sweep** (does higher conviction help?): bar 0.05 → mean −$0.028, CI
   [−0.063, +0.008]; bar 0.10 → **−$0.042**, CI [−0.079, **−0.006**] (fully below zero);
   bar 0.15 → −$0.044, CI [−0.090, +0.002]. Raising the bar makes per-trade P&L *more
   negative* — the opposite of a real edge. Uniformly null/negative.
2. **Fill/cost-model sign audit** (the exact S1 / pt1 false-positive failure mode): hand-
   recomputed gross, fee, net for sample trades independently — **0 mismatches**. Every
   *winning* trade has gross > 0; every *losing* trade has gross < 0 (no sign inversion).
   YES entry == raw_yes_ask exactly (bought at the real ask, not a mid). NO entry = one minus
   the best YES bid (the correct, *more expensive* NO-taker complement — a cost, never an
   improvement). In the sample: 5 wins (mean +$0.328) vs 20 losses (mean −$0.154) — the model's
   "edge" trades lose far more often than they win.
3. **Anti-leak timing**: run_init(D−1 00Z) < decision_T verified for every trade; whole-study
   leak_guard drops = 0. The forecast genuinely predates the decision.
4. **Not a mis-signed informative model**: the loss is not concentrated such that flipping the
   rule would win — the point estimate is a modest loss driven by the ~10c overround eating
   small, noisy edges, not a large anti-correlation. There is no exploitable flip.

## Caveats (all stated plainly)

- **Short spring window.** Tape is 2026-04-16 .. 2026-05-09 (~22 days, 21 usable contract-
  days). The QF note flags the weather edge as plausibly *summer*/high-convective; this spring
  sample is not the regime where the synthetic edge concentrated. A summer tape could differ —
  but we do not have one, and the prime directive judges on data we have.
- **EMOS is data-thin.** 3 models (GEM unavailable in the single-runs archive) and ~21 days
  per LOO fold. The fit is honest (LOO, pre-registered fallback) but low-powered; per-city CRPS
  is noisy.
- **Decision time near market open.** T ≈ D 04–06 UTC is early in the observation day, when
  books may be thin/wide; 11 groups dropped on incomplete books at T.
- **L1-only fills.** The tape's 'ticker' BBO is best-bid/best-ask only; no depth, so size and
  slippage beyond the top level are not modelled (we assume a single-contract lift fills).
- **No fill haircut** (optimistic) — strengthens the null but would only worsen a positive.

## Conclusion → project direction

EMOS calibration works (CRPS improves), but a better probability is still not enough: the
~10c real-ask overround plus taker fee swallows the edge, and the net-P&L CI does not clear
zero. Consistent with S1 (longshot fade, dead) and arb-bot's pt1 post-mortem. **The weather
family is dead on this sample.** No weather-model capital. Pivot to the non-weather, prob-to-
prob / microstructure candidates: **S2** (FOMC × ZQ basis — no weather overround), **S3**
(cross-strike monotonicity staleness), **S6** (inventory-aware market-making — earn the spread
instead of paying the overround).
