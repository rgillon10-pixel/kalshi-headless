# Seed 5 — perp-funding directional prior on Kalshi crypto-hourly ladders (first-cut scoping probe)

`date 2026-07-17` · `script scripts/seed5_funding_prior_probe.py` · `tests tests/test_seed5_funding_prior_probe.py`
· **VERDICT: DEAD across the full 12-cell grid** (falsified at `real_ask` net of taker fee) · first-cut scoping probe, **NOT a graduation**

## Hypothesis (falsifiable)

Elevated perpetual funding at a Kalshi crypto-hourly window's OPEN is a directional prior for the
within-hour settle side that the range ladder underprices — enough to clear the TAKER round-trip on
the ACTIVE (fillable) band. Honest prior is NULL: within-hour crypto direction is ~martingale and
funding is a slow 8h signal against a 1h horizon.

## Data window + n

- **Tape:** `tape/crypto_hourly/dt=2026-07-03 .. dt=2026-07-16` (read-only). 462 MECE/complete/uniquely-settled
  events joined (earliest `current` capture → `previous_settlement` `broker_truth`). Symbol split: BTC 231, ETH 231.
  Event open-time span 2026-07-03T10:00Z .. 2026-07-16T23:00Z.
- **Unit of bootstrap:** `event_ticker` (one hold-to-settlement trade per event = the independent unit, L6/L33).
- **Bootstrap:** `core.bootstrap.block_bootstrap`, 10,000 resamples, seed 42. Gates: `clears_tick_magnitude` (L27),
  `bootstrap_verdict_admissible` (L41).

## Funding source actually used + tag

- **OKX** `public/funding-rate-history` for `BTC-USD-SWAP` / `ETH-USD-SWAP`, keyless, read-only. Tagged
  **`synthetic`**, role = directional PRIOR only, NEVER a fill price or settlement predictor.
- **Substitution note:** the seed spec named Binance USDs-M funding, but `fapi.binance.com` is geo-blocked from
  this environment (HTTP 451). The script already substitutes OKX (perp funding is highly cross-venue correlated).
  Hyperliquid (the sanctioned second fallback) was **not needed** — OKX was reachable this run.
- **Coverage:** OKX returned 100 prints/symbol spanning 2026-06-14T00:00Z .. 2026-07-17T00:00Z at 8h cadence —
  fully covers the tape window. Cached for offline reproducibility:
  - `tape/seed5_funding_cache/okx_funding_20260717.json` (script `--funding-cache` replay format)
  - `tape/seed5_funding_cache/okx_funding_20260717.jsonl` (one source-tagged row per print: `venue=okx`,
    `price_source_tag=synthetic`, `role=directional_prior`, `fetched_at`)
- Reproduce: `python scripts/seed5_funding_prior_probe.py --funding-cache tape/seed5_funding_cache/okx_funding_20260717.json`

## Full cell grid (no cherry-picking — all 12 cells)

Median |funding| over events (the "elevated" threshold) = 6.345e-05. Entry = earliest capture (~24 min into the
hour), `real_ask`; settle = `broker_truth`; funding = perp prior (`synthetic`). Net P&L = payout − entry − taker
fee (`core.pricing.fee_per_contract`, TAKER 0.07).

| band (raw yes_ask) | convention | thr | n | win | mean $ | 95% CI $ | clears_tick | adm (L41) | side_deg | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| [0.05,0.95] | momentum   | all      | 414 | 0.186 | -0.03556 | [-0.07053, +0.00014] | False | True | one_sided_0.96 | **DEAD** |
| [0.05,0.95] | momentum   | elevated | 211 | 0.185 | -0.02810 | [-0.07754, +0.02412] | False | True | one_sided_1.00 | **DEAD** |
| [0.05,0.95] | contrarian | all      | 427 | 0.164 | -0.05396 | [-0.08761, -0.01822] | False | True | one_sided_0.98 | **DEAD** |
| [0.05,0.95] | contrarian | elevated | 210 | 0.190 | -0.02267 | [-0.07519, +0.03062] | False | True | one_sided_1.00 | **DEAD** |
| [0.03,0.97] | momentum   | all      | 460 | 0.167 | -0.03204 | [-0.06335, +0.00061] | False | True | one_sided_0.97 | **DEAD** |
| [0.03,0.97] | momentum   | elevated | 229 | 0.170 | -0.02729 | [-0.07179, +0.01921] | False | True | one_sided_1.00 | **DEAD** |
| [0.03,0.97] | contrarian | all      | 457 | 0.153 | -0.03982 | [-0.07151, -0.00691] | False | True | one_sided_0.96 | **DEAD** |
| [0.03,0.97] | contrarian | elevated | 228 | 0.175 | -0.01246 | [-0.05934, +0.03596] | False | True | one_sided_1.00 | **DEAD** |
| [0.10,0.90] | momentum   | all      | 363 | 0.212 | -0.03551 | [-0.07548, +0.00625] | False | True | one_sided_0.96 | **DEAD** |
| [0.10,0.90] | momentum   | elevated | 179 | 0.218 | -0.02268 | [-0.08061, +0.03860] | False | True | one_sided_1.00 | **DEAD** |
| [0.10,0.90] | contrarian | all      | 403 | 0.161 | -0.07672 | [-0.11146, -0.04099] | False | True | one_sided_0.98 | **DEAD** |
| [0.10,0.90] | contrarian | elevated | 194 | 0.191 | -0.04119 | [-0.09454, +0.01351] | False | True | one_sided_1.00 | **DEAD** |

Every cell: mean strictly negative; CI either entirely below 0 or straddling 0; NONE clears the 1-tick magnitude
gate (`clears_tick=False` in all 12 — a positive lower bound never occurs, and the two lower bounds closest to 0
are +0.00014 / +0.00061, three orders below a fillable 1¢ tick, the exact L27 residue shape). **Zero ALIVE cells.**

## Why it dies (mechanics, not noise)

- **Signal degeneracy is the headline caveat.** Funding sign was positive at **446/462 opens (96.5%)** — BTC 100%
  positive, ETH 93.1% positive — over this 2-week window of persistent positive carry. So the "directional funding
  prior" collapses into a near-static side bet: `momentum` buys the up-side OTM bracket ~96–100% of the time,
  `contrarian` buys the down-side ~96–98% of the time. Every cell's `side_degeneracy_flag` fires (all `elevated`
  cells are `one_sided_1.00`). The window carries almost no cross-sectional sign variation, so it cannot cleanly
  distinguish "funding direction predicts settle side" from "always buy one OTM band." This is a data-adequacy
  limitation ON TOP OF the falsification, most acute for the `elevated` cells.
- **The loss is the overround + fee tax on an OTM lottery bracket.** Primary cell (band [0.05,0.95], momentum, all):
  mean entry `real_ask` = $0.206, mean normalized_ask = 0.066, win rate 18.6% (77/414). Gross EV ≈ 0.186 − 0.206 =
  −$0.020; minus a ~$0.02 taker fee ≈ −$0.036, matching the observed −$0.0356 within rounding. The nearest fillable
  bracket to spot is a ~20¢ out-of-the-money range ticket; buying it hourly just pays the structural cost.
- **L41 admissibility passes but is not exculpatory:** `adm=True` everywhere because winning vs losing events give
  genuinely opposite-signed unit means (mixed population, no resample-artifact). The kill is real, not a degenerate
  all-one-direction bootstrap. The *directional-signal* degeneracy is the separate `side_degeneracy_flag`, reported
  above.

## Kill-criteria assessment

- **Binding bar (block-bootstrap 95% CI strictly > 0 at `real_ask` net of fees, clearing the tick-magnitude gate):**
  FAILED in all 12 cells. Six cells straddle 0 (CI lower < 0), four are entirely negative, and none has a lower
  bound ≥ 1 tick. Verdict: **DEAD — falsified.**
- **Data-adequacy:** every cell met the n ≥ 10 unit floor (n = 179–460), so no cell is DEAD-by-data-adequacy on
  count. BUT the `elevated` cells are directionally degenerate (`one_sided_1.00`): the funding signal never flipped
  sign among them, so their CIs test a fixed-side bet, not a direction-conditioned one. Treat the `elevated` cells
  as **falsified AND under-powered as a directional test** — a fair retest needs a window with materially more
  negative-funding hours (a crypto downtrend / funding-flip regime).

## Header-claim vs code verification (task-mandated)

- **`nearest_fillable_bracket` refuses pinned / no-ask brackets:** CONFIRMED. It admits an outcome only if its RAW
  `yes_ask ∈ [lo, hi]` (primary [0.05, 0.95]), which excludes the 1¢ YES-floor pins (S10) and the ≥0.95 / $1.00-NO-mirror
  side (L26). Pinned-only sides return `None` → no trade, counted honestly (n_no_fillable=48 in the primary cell),
  never a synthetic fill. Pinned by unit tests `test_nearest_fillable_excludes_floor_pinned_wings` /
  `_excludes_ceiling_pinned`.
- **`trade_net_pnl` fee treatment:** the model is BUY-YES-and-HOLD-TO-SETTLEMENT. On Kalshi settlement is free (no
  closing trade), so the complete fee is the single ENTRY taker fee — which is what the code charges
  (`fee_per_contract(entry, TAKER_FEE_RATE)`, via the sanctioned `core.pricing`, L5/L18). **Minor wording flag:** the
  header says "full taker fee round-trip," but a hold-to-settle position has no exit leg — it is an entry-only taker
  fee, which is the correct and complete fee for this strategy. This does NOT flatter the edge: charging a phantom
  exit fee would only push every cell MORE negative, so the DEAD verdict is robust to the wording nuance.

## Notes / scope

- This is a **first-cut scoping probe, not a graduation.** No paper/live path touched; read-only over `tape/`; the
  only network call was the keyless OKX funding read.
- Funding is a PRIOR tagged `synthetic`; entries priced at `real_ask`; settlement `broker_truth`. No synthetic price
  was ever treated as fillable (prime directive / L1).
- Gates at run time: seed5's 17 offline tests green; `scripts/invariants.py --full` green. Full `pytest -q` has ONE
  unrelated pre-existing failure — `tests/test_s17_leadlag_probe.py::test_parse_capture_time_prefers_captured_at`, a
  Python 3.9 `datetime.fromisoformat` limitation on single-digit fractional seconds (`'...:03.5+00:00'` raises
  `ValueError`); file untouched by this probe (git clean), not a seed5 regression.
