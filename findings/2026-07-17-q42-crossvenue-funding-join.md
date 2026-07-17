# Q42 (part 2) — Kalshi vs Hyperliquid cross-venue funding join — characterization / sizing memo

`2026-07-17` · LOOP-QUEUE.md **Q42** (characterization sub-milestone, part 2 of 3) ·
collector `collection/hyperliquid_funding.py` (+ tests `tests/test_hyperliquid_funding.py`,
9, offline) · join script `scripts/q42_crossvenue_funding_join.py` (+ tests
`tests/test_q42_crossvenue_funding_join.py`, 8, offline) · **NOT a P&L verdict — no
fee/carry model, no bootstrap CI, no registry status changed** (`kb/strategies/00-index.md`
and Q42's Status line untouched). Both funding legs are tagged **`broker_truth`** (finalized
venue prints, not fills).

## The question

Part 1 proved Kalshi's finalized 8h crypto-perp funding is a **genuine ±1bp dead-band clamp**
— exactly 0 in ~76% of windows pooled (BTC 66.9%, ETH 79.2%). The cross-venue thesis: while
Kalshi's leg is clamped to 0 most windows, an off-venue perp's same-underlying funding is
essentially never 0, so a long-Kalshi / short-offshore delta-neutral pair pays ~0 on the
Kalshi leg and collects the offshore funding — a mechanical basis. Part 2 **sizes that
differential distribution** against Hyperliquid (its public `/info` REST needs no auth and is
not geo-blocked from this sandbox, unlike Binance). This is discovery/characterization only;
it establishes no tradable edge (see Limits) — part 3 (the fee/carry model) owns that, and is
blocked on an authenticated Kalshi `/margin` endpoint.

## Data

- **Kalshi leg** — `tape/perp_tape/dt=2026-07-17.jsonl`, the `funding_rates` `mode=="backfill"`
  record (part 1's population): finalized 8h prints, **2026-06-03 → 07-16**, deduped on
  `(market_ticker, funding_time)`. 130 BTC + 130 ETH windows. `broker_truth`.
- **Hyperliquid leg** — newly collected `tape/hyperliquid_funding/dt=2026-07-17.jsonl`:
  **1,063 hourly** finalized funding prints per coin (BTC + ETH), **2026-06-03T00:00Z →
  2026-07-17T06:00Z**, tagged `broker_truth`. Fetched once, live, from the public endpoint
  and committed (prime directive #2 — HL's history API may not reach back forever).
- Read-only, offline: the join script reads committed tape, makes **no** network call.

## Method

- **Cadence bridge.** Kalshi finalizes funding every **8 hours**; Hyperliquid pays **hourly**.
  For each Kalshi print at time `T`, the matching 8h window is the 8 HL hourly rates at hours
  `(T-7h … T]`, **compounded** into an 8h-equivalent `prod(1+r)-1` (a simple sum is also
  reported — at ~1e-4/hr the two agree to ~1e-7, immaterial). `differential = HL 8h-equiv −
  Kalshi print`, per `(asset, window)`.
- **Window alignment was checked, not assumed.** Kalshi's actual `funding_time`s are at
  **04 / 12 / 20 UTC**, NOT the naive 0/8/16 — the window is anchored to each print's real
  `T`. HL stamps its hourly `time` a few ms past `:00`; hours are matched by **rounding to the
  nearest hour** (a strict `<=` compare would drop the edge row and mis-window every bucket).
- **Partial windows excluded, never zero-filled** (a missing HL rate is not a zero — same
  discipline as part 1). Result: **0 partial windows** for either asset — HL's history fully
  covers every Kalshi window (HL starts 06-03T00:00Z, Kalshi's first print is 06-03T20:00Z).
- **Join-sanity anchor.** The joined-set Kalshi zero-fraction must reproduce that asset's
  full-population zero-fraction (else the join silently dropped/duplicated windows); for BTC it
  is additionally pinned against part 1's published 0.669. Both pass exactly.

## Numbers (all `broker_truth`; 1e-4 = 1 basis point per 8h window)

| quantity | BTC (KXBTCPERP↔BTC) | ETH (KXETHPERP↔ETH) |
|---|---|---|
| windows joined / partial-excluded | 130 / 0 | 130 / 0 |
| Kalshi zero-fraction (joined) | **0.6692** (= full-pop = part1) | **0.7923** (= full-pop) |
| HL zero-fraction (joined) | **0.0000** (0/130) | **0.0000** (0/130) |
| Kalshi 8h rate, mean | +0.439 bp | −0.265 bp |
| HL 8h-equiv, mean / median | +0.677 bp / +0.876 bp | +0.513 bp / +0.903 bp |
| **differential, mean / median** | **+0.238 bp / +0.702 bp** | **+0.777 bp / +1.000 bp** |
| differential p10 / p50 / p90 | −1.076 bp / +0.702 bp / +1.000 bp | −0.383 bp / +1.000 bp / +1.485 bp |

**Regime — tercile by |HL 8h-equiv| (does the basis widen when HL funding is large?):**

| tercile | BTC diff mean | ETH diff mean |
|---|---|---|
| low \|HL\| | **−0.557 bp** | +0.620 bp |
| mid \|HL\| | +0.548 bp | +1.014 bp |
| high \|HL\| | +0.712 bp | +0.700 bp |

**Regime — sign of HL 8h-equiv:**

| HL sign | BTC (n, diff mean) | ETH (n, diff mean) |
|---|---|---|
| positive | 120, +0.355 bp | 100, +1.022 bp |
| negative | 10, −1.162 bp | 30, −0.039 bp |
| zero | 0 | 0 |

## What the distribution says

- **The thesis's two structural facts both hold on the overlapping window set.** Kalshi is
  clamped to exactly 0 in **67% (BTC) / 79% (ETH)** of joined windows; Hyperliquid is **never 0**
  (0 of 1,063 hourly, 0 of 130 8h-equivalents, each asset). The join reproduces part 1's BTC
  zero-fraction to the fourth decimal — the join is clean, not an artifact.
- **The modal window is Kalshi≈0, HL≈+1bp.** Hyperliquid's ~+0.0000125/hr interest-rate
  baseline compounds to ≈**+1 bp / 8h**, which is exactly where the differential's median and
  its p75/p90 pile up (the repeated `+1.000 bp` is HL's own baseline floor, **not** a Kalshi
  cap — Kalshi nonzeros are continuous up to ~9.7 bp). So the typical differential is a
  **~+1 bp / 8h mechanical basis**: ≈+3 bp/day, ≈**+11%/yr gross** at 3 windows/day — a
  magnitude large enough, before any cost is subtracted, that it's **worth building the real
  fee/carry model (part 3)** to find out whether it survives contact with fees and margin drag,
  not a claim that it will.
- **But it is NOT a free lunch, and the sign is regime-dependent.** The differential goes
  **negative** in BTC's low-|HL| tercile (−0.557 bp) and in every window where HL funding is
  negative (BTC −1.162 bp over 10 windows; ETH ≈0 over 30). BTC's p10 is −1.076 bp. In those
  windows Kalshi's own (unclamped) funding exceeds HL's, or HL flips sign — the pair would bleed.
  So the harvest concentrates in the HL-positive / larger-|HL| regime, and **regime selection is
  load-bearing**, not incidental — precisely what part 3's cost stack has to survive.

## Limits — characterization only, NO edge established

- **No P&L claim.** No fee model, no margin/carry drag, no basis-risk or liquidation model, no
  bootstrap CI. The reported `differential` is a raw funding-rate difference, not a net return.
- **Sign convention is deliberately unresolved.** The differential is reported as raw
  `HL 8h-equiv − Kalshi print`; how it maps to *income to a long-Kalshi/short-HL pair* depends on
  each venue's charged-at-start-vs-end and sign-accrual conventions, which are a part-3 execution
  detail. Read the numbers here as **magnitude and dispersion**, not as a signed P&L.
- **Short, single-regime sample.** 43 days / 130 windows per asset, one macro regime (perps
  launched six weeks ago). No seasonality, no funding-stress episode in-sample.
- **Part 3 (TODO, needs auth):** the honest carry model — post-promo Kalshi perp fee schedule
  (`/margin` `fee_tiers`, auth-gated), margin drag on both legs, mark-vs-mark basis risk,
  liquidation at the leverage caps. Perps trading is outside the current execution lane.
- The Q42 deliverable stays a **verdict + sizing memo, never a green light**.

## Reproduce

```
python -m collection.hyperliquid_funding                 # re-fetch HL tape (live, idempotent)
python3 scripts/q42_crossvenue_funding_join.py           # offline join over committed tape
```

Gates: full `pytest` green (1108 passed), `python scripts/invariants.py --full` green
(final line `invariants: all green`; the stranded-ref / directory-dt / missing-cadence-day
lines are the known pre-existing non-gating advisories).

## New lesson candidates (for kb-distiller)

- **Two funding venues on different cadences must be bridged on the *finer* leg by
  nearest-hour bucketing, anchored to the *coarser* leg's actual print timestamps — never to
  assumed UTC-aligned boundaries.** Kalshi finalizes at 04/12/20 UTC (not 0/8/16), and
  Hyperliquid stamps hourly a few ms past `:00`; a strict `<=` window edge silently drops the
  boundary hour and mis-windows every bucket. Round to the nearest hour, window as `(T-7h … T]`
  in rounded-hour space, and require all 8 hours present (partial ⇒ excluded, never zero-filled).
- **A repeated exact percentile value in a cross-venue differential is usually one venue's own
  baseline, not a shared cap.** Here `+1.000 bp` recurs at the differential's p75/p90 because
  it is Hyperliquid's interest-rate funding baseline (0.0000125/hr × 8), not a Kalshi clamp cap
  — Kalshi nonzeros are continuous to ~9.7 bp. Check *which* leg pins a suspicious round number
  before attributing it.
- **Reproduce the prior milestone's headline on the overlapping join set as a join-sanity
  gate.** The BTC zero-fraction reproducing part 1's 0.669 to four decimals is what proves the
  cross-venue join didn't drop or duplicate windows — a cheap, decisive integrity check that a
  raw differential number alone would not surface.

## Artifacts

- `collection/hyperliquid_funding.py`, `tests/test_hyperliquid_funding.py` (9 tests)
- `scripts/q42_crossvenue_funding_join.py`, `tests/test_q42_crossvenue_funding_join.py` (8 tests)
- `tape/hyperliquid_funding/dt=2026-07-17.jsonl` (BTC + ETH, 1,063 hourly prints each, `broker_truth`)
