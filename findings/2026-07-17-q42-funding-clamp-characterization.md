# Q42 (part 1) — Kalshi perp funding dead-band clamp — characterization: GENUINE ±1bp CLAMP

`2026-07-17` · LOOP-QUEUE.md **Q42** (characterization sub-milestone, part 1 of 3) ·
script `scripts/q42_funding_clamp_probe.py` · tests `tests/test_q42_funding_clamp_probe.py`
(15, offline) · **verifier: CONFIRMED** (independent from-scratch recompute off raw tape,
then re-ran the committed script — matched exactly) · **NOT a P&L verdict — no registry
status changed** (`kb/strategies/00-index.md` untouched) · every funding number below is
tagged **`broker_truth`** (venue-computed, not a fill).

## The question

Kalshi launched CFTC-regulated crypto perpetual futures 2026-05-29 (13 active contracts,
8h funding, zero-fee launch promo). The recon anomaly: finalized 8h funding prints are
**exactly 0 in a majority of windows per contract**. Q42 part 1 asks whether that is a
**genuine formula dead-band/clamp** or an **artifact** (a display/API rounding quantization
straddling zero). This milestone characterizes the clamp only; it establishes no tradable
edge (see Limits).

## Data

- Source: `tape/perp_tape/dt=2026-07-17.jsonl`, the single `record_type=="funding_rates"`
  `mode=="backfill"` record — **1,447 finalized prints** since launch, **2026-06-03 → 07-16**,
  across **13 contracts**. Dedup on `(market_ticker, funding_time)`.
- Every funding number carries the source tag **`broker_truth`** (the venue-computed funding
  family; not a `real_ask` fill price).
- Read-only, offline: the probe reads committed tape, makes no network call.

## Method

Per contract and pooled: exact-zero fraction; the distribution of nonzero magnitudes; and the
**clamp-vs-rounding discriminator** — whether the nonzeros are continuous/unquantized vs
sitting on a fixed lattice, and whether a **hard gap** exists in the open interval just above
zero `(0, 1e-4)`. A dead-band clamp forces rates inside a ±band to *exactly* 0 while leaving
the surviving nonzeros continuous; a symmetric-rounding/quantization artifact would instead
put the "zeros" on a lattice bucket straddling zero, with nonzeros landing on that same tick
grid. The discriminator therefore tests the gap **relative to the data's own granularity**,
not against an absolute threshold (fixtures pin both signatures:
`test_clamp_signature_clear_gap`, `test_rounding_signature_one_tick_from_zero`).

## Numbers (all `broker_truth`)

| quantity | value |
|---|---|
| finalized prints (dedup) | 1,447 |
| window | 2026-06-03 → 2026-07-16 |
| contracts | 13 |
| pooled exact-zero fraction | **0.762** (1,102 of 1,447 exactly 0) |
| per-contract zero-fraction range | **61.6% – 99.1%** |
| BTC (KXBTCPERP) zero-fraction | ~66.9% |
| LINK (KXLINKPERP) zero-fraction | ~99.1% |

**The decisive evidence — a hard gap in `(0, 1e-4)`.** Across the pooled population:

- **1,102** prints are exactly 0,
- **0** nonzero values fall in the open interval `(0, 1e-4)`,
- **186** values fall in `[1e-4, 1.5e-4)`.

The nonzero rates are **continuous / unquantized**, not lattice-quantized: the per-contract
smallest nonzero `|rate|` **varies** (e.g. BTC 1.0004e-4 up to SUI 1.0560e-4). What is uniform
across contracts is that **no contract has any nonzero magnitude below ~1e-4** — a hard floor,
**not a single shared value**. Because the nonzeros are continuous rather than sitting on a
1e-4 lattice, the exact-zeros are **NOT** a symmetric-rounding/quantization bucket straddling
zero; they are rates inside a **±1 basis-point band forced to exactly 0**.

(We deliberately do **not** headline an inferred single tick size / "ticks-from-zero" figure —
that number is a sample-dependent proxy, not a physical venue tick, and reads as more precise
than the data supports.)

## Characterization result

A **GENUINE ±1 basis-point funding dead-band CLAMP on 12 of 13 contracts**. The exactly-zero
majority is a formula property (a dead band), not a rounding/display artifact.

- **KXLINKPERP is data-adequacy-UNDECIDABLE** — only **1** nonzero print in the entire window,
  too few to characterize its band. Reported as **undecidable**, not clamped.

## Limits — characterization only, NO edge established

- This result characterizes the clamp's existence and shape. It does **NOT** establish a
  tradable edge. The Q42 thesis (long-Kalshi / short-offshore funding carry, delta-neutral)
  is **unproven** and out of scope here.
- **Part 2 (TODO):** the Hyperliquid cross-venue funding join — size the Kalshi-vs-offshore
  funding differential distribution by regime. Needs live network / a non-geoblocked venue.
- **Part 3 (TODO):** the honest carry model — post-promo Kalshi perp fee schedule (the
  `/margin` `fee_tiers` endpoint needs auth; promo economics are not durable economics),
  margin drag on both legs, mark-vs-mark basis risk, and liquidation risk at the leverage
  caps. Needs auth.
- Perps trading itself is **outside** the current execution lane (leveraged delta-1 — would
  need its own client + the full LIVE-AUTH gate). The Q42 deliverable stays a **verdict +
  sizing memo, never a green light**.

## Verification

Independent verifier re-derived the headline numbers **from scratch off the raw tape**
(bypassing the probe), then re-ran the committed `scripts/q42_funding_clamp_probe.py` and got
an exact match. Verifier flagged and this note avoids two over-compressions: (1) the
"min_abs_nonzero uniformly 1.000e-4" phrasing — replaced by the hard-gap `(0, 1e-4)` framing
with the 1,102 / 0 / 186 counts and the per-contract smallest-nonzero variation; (2) headlining
the inferred single tick / ticks-from-zero number (a sample-dependent proxy). Full `pytest -q`
and `python scripts/invariants.py --full` green. **Verdict: CONFIRMED.**

## Reproduce

```
python3 scripts/q42_funding_clamp_probe.py
```

Reads `tape/perp_tape/dt=2026-07-17.jsonl` (committed), offline, no network.

## New lesson candidate (for kb-distiller)

- A clamp-vs-rounding (dead-band vs quantization) discriminator must test the **gap relative
  to the data's own granularity** — whether the nonzeros are continuous vs lattice-quantized,
  and whether a hard gap exists just above zero — **NOT** compare against an absolute
  threshold. An absolute-threshold test would misclassify either a fine-tick or a coarse-tick
  series.

## Artifacts

- `scripts/q42_funding_clamp_probe.py`, `tests/test_q42_funding_clamp_probe.py` (15 tests)
- `tape/perp_tape/dt=2026-07-17.jsonl` (`record_type=="funding_rates"`, `mode=="backfill"`)
