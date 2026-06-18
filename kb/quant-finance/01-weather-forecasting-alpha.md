# Weather forecasting as alpha — the only edge most aligned with these markets

`reproduced` · 2026-06-18 · QF Theme 5 deepened · supports strategy S5 (weather rehab) & S4

Most Kalshi contracts these repos trade are **daily high-temperature brackets** per city.
The thesis: if you can produce a *better-calibrated* probability for each bracket than the
market maker, the gap is alpha. This note is the recipe and the honest caveats.

## The core mistake to avoid (first principles)

You **cannot** read a probability off the raw fraction of ensemble members in a bracket.
Raw ensembles are **underdispersed** — they are systematically overconfident, especially in
the tails. The fraction-of-members estimate is biased. This is the single most important
fact in the theme, and it's why a naive "4-model ensemble vs market" strategy (arb-bot's
KXHIGH, now `dead`) had a real *signal* but no real *dollar edge*.

## The recipe (calibrated post-processing)

1. **Gather an ensemble** of forecasts for the target (daily Tmax at the contract's station):
   multiple models (ECMWF/GFS/ICON/GEM) and/or members. Open-Meteo exposes these free.
2. **Post-process to a calibrated predictive distribution.** Two canonical methods:
   - **EMOS** (Ensemble Model Output Statistics) — Gneiting, Raftery, Westveld & Goldman
     (2005), *Monthly Weather Review* 133. Fit a parametric distribution (e.g. Gaussian) whose
     mean is a bias-corrected affine function of the ensemble mean and whose **variance is an
     affine function of ensemble spread**, estimated by **minimizing CRPS**. This directly
     fixes the underdispersion.
   - **BMA** (Bayesian Model Averaging) — Raftery, Gneiting, Balabdaoui & Polakowski (2005),
     *MWR* 133. A weighted mixture of each member's predictive distribution; handles
     multimodality (e.g. a frontal-passage bimodal day).
3. **Score with CRPS, not accuracy.** Gneiting & Raftery (2007), *JASA* 102 — minimizing a
   strictly proper scoring rule (CRPS) yields the best full-distribution forecast, which is
   exactly the profit-optimal probability source for threshold contracts.
4. **Integrate above each bracket threshold** to get `P(low ≤ Tmax < high)` per bracket.
5. **Trade the gap** vs. the market's `yes_ask / bracket_sum` normalized implied probability —
   only when the gap exceeds the fee + overround bar (~3–7¢, see `../kalshi-api/03-fees-and-breakeven.md`).

A complementary physical-measure model: **Alaton, Djehiche & Stillberger (2002)**, *Applied
Mathematical Finance* 9 — daily temperature as a seasonal mean plus a mean-reverting (OU)
Gaussian process, with closed-form HDD/CDD pricing. Useful as an independent sanity check on
the data-driven EMOS distribution and for longer horizons.

## Why this is the most fee-robust edge here

It is a genuine **informational** edge: the probability is *better*, not a behavioral bias that
fees erase. The gap can be large precisely on the days the market is hardest to price (high
convective uncertainty — summer), which is also where arb-bot's synthetic edge concentrated
(+$0.165 on the summer subset).

## The honest caveats (why S5 is still an open question, not a yes)

- **Sophisticated competition.** Energy firms and weather-derivative desks already post-process
  ensembles, especially at short horizons in liquid contracts. Your edge is largest on **thin,
  long-dated, or off-the-run** city/day contracts (Theme 1: thin markets are less efficient).
- **The overround still has to be cleared.** A better probability is necessary but not
  sufficient — the gap must exceed fee+overround *at the fillable ask*. arb-bot proved a real
  signal can still be a losing dollar trade. This is exactly what S5's forward paper test checks.
- **Tail data is sparse.** Extreme brackets (the wings, S4) are where EMOS/BMA are least reliable
  and where overconfidence bites hardest — yet also where the fattest mispricing might live
  (FEx fat-tail thesis). Validate tail calibration separately; don't trust a Gaussian in the wings.
- **Regime dependence.** The edge is plausibly seasonal/convective. Hard rule #6's regime-conditional
  Kelly ρ exists for this reason. A summer-only result may not generalize to winter frontal regimes.

## What this implies for the build

- S5 (weather rehab) is worth the **$0-capital forward paper test**: real captured asks (from S0's
  tape) × an EMOS/BMA-calibrated distribution × an honest no-mid fill model, on the summer subset.
  If the bootstrap CI still straddles zero, the weather family is dead — pivot to S2/S3/S6.
- The **forecast tape is the missing input** (data-to-collect #4): there is zero forecast tape
  anywhere, which blocks both this and any latency edge. Start a forecast collector with ms-precision
  `fetch_ts` per city/model now.
- Do **not** re-deploy the raw-ensemble KXHIGH strategy. Post-process first or don't trade.

## Reproduced (2026-06-18)

Runnable proof: **`../scripts/emos_demo.py`** (stdlib only — `math`/`statistics`/`random`,
seeded `SEED=20260618`, no numpy/scipy; deterministic, identical every run). It builds a toy
12-member daily-Tmax ensemble that is deliberately **cold-biased (+2.5F) and underdispersed**
(member sd 3F vs true day-to-day sd 9F), fits an EMOS Gaussian — predictive mean = `ens_mean`
plus a learned bias correction, predictive variance = affine `a + b·ens_var` — by **minimizing
the closed-form Gaussian CRPS** (Gneiting & Raftery 2007: `sigma*[z(2Φ(z)−1)+2φ(z)−1/√π]`,
Φ via `math.erf`) over a 400-pair training set, then scores both forecasts on 200 held-out days.

Cold run (`cd <repo> && ./.venv/bin/python scripts/emos_demo.py`):

```
Fitted: mu = ens_mean + 2.5839   (bias correction)
        sigma^2 = 1.7734 + 0.0254 * ens_var   (spread inflation)

Held-out mean CRPS (lower is better):
  CRPS_raw  (naive ensemble)  = 1.663016
  CRPS_emos (calibrated EMOS) = 0.716507     # 56.92% lower
Bracket: P(74 <= Tmax < 78) = 0.760991   (test day 0, mu=75.0675, sigma=1.3914)
```

So calibrated post-processing scores **0.716507 vs 1.663016** held-out CRPS — the EMOS Gaussian
is strictly better than the raw underdispersed ensemble (the script `assert`s this), confirming
the note's core thesis. The bracket probability `0.760991` is the integral of the fitted Gaussian
between the thresholds; it is **not** a tradable price until compared to the market's
overround-normalized ask (`core.pricing.normalized_ask`) and the fee bar (`scripts/fee_breakeven.py`)
— Hard Rule #3 and the caveats above still apply.
