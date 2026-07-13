# S19 elevated-wing stale-ask maker fade (Q23) — verdict: DEAD

`2026-07-13` · LOOP-QUEUE.md **Q23** · registry **S19** · script
`scripts/s19_wing_fade_fillsim.py` · tests `tests/test_s19_wing_fade_fillsim.py` (22,
offline/synthetic) · **read-only, no network, no orders, no auth** · **verifier: CONFIRMED**
(every number reproduced byte-for-byte independently) · two-agent verdict rule satisfied —
registry flip authorized.

## Question

S10 died as a TAKER trade (L26): a floor-pinned far bracket's 1¢ YES mirrors to a $1.00 NO ask
— no fillable taker price. That verdict explicitly left the MAKER side untested. Q20's ladder
anatomy (`findings/2026-07-13-btc-ladder-overround-anatomy-q20.md`) documented `wing_elevated`
members — stale one-sided YES asks (`yes_ask` in [0.20, 0.67], `yes_bid=0`, outside ±3
strike-spacings of spot) that almost surely settle NO. Mechanism: rest a maker short-YES (buy-NO
at `1−yes_ask`) on those stale wings and hold to settlement, collecting the premium from whoever
lifts the stale far-OTM ask.

## Method

`scripts/s19_wing_fade_fillsim.py` (read-only, fully offline):
- **Wing selection** matches Q20's `wing_elevated` definition exactly (outside ±3 strike
  spacings of spot — spacing read off the ladder's own between-band floors, `synthetic` spot as
  a binning coordinate only, never a fill price; `yes_ask` in [0.20, 0.67], real_ask; `yes_bid ==
  0`).
- **Entry** = earliest capture of each settled event-hour (same convention as S14; aligns the
  executed-volume window with the S14 candle cache).
- **Fill rule — queue-aware, NOT a candlestick print (L39).** A new resting NO bid joins the
  BACK of the `orderbook_depth` `no_bids` queue Q20 measured at these wings (166–503 contracts).
  Filled iff the ask was touched (max realized trade high ≥ yes_ask) AND executed volume over
  the hold ≥ the queue ahead (real_bid `no_bids` size at price ≥ our level). Executed volume and
  max trade high come from the already-committed S14 candlestick cache
  (`tape/s14_ladder_fillsim/`), read offline, never re-fetched.
- **P&L** net of the flat 1¢ maker fee (`core.pricing.fee_per_contract` at `MAKER_FEE_RATE`),
  explicitly split by settle-YES-given-filled (the predicted toxic leg) vs settle-NO-given-filled
  (the win leg), so the adverse-selection correlation the mechanism predicts is surfaced rather
  than averaged away.
- **Gate**: block-bootstrap E[P&L] BY EVENT-HOUR (`core.bootstrap`, L6) over the filled
  population, L27 tick-magnitude gate on the CI lower bound, and a data-adequacy floor
  (`MIN_CI_UNITS=10` filled event-hours) below which a CI is not trusted regardless of sign.

## Result

- **Wing population:** 895 `wing_elevated` members (BTC 806, ETH 89) across 175 settled
  event-hours.
- **Join coverage:** 402/895 = 44.92% (both queue and executed volume measurable offline; ceiling
  set by `orderbook_depth` starting 07-07 vs `crypto_hourly` 07-03, L9).
- **Observability precheck:** only 16/402 joinable wings (3.98%) ever had the ask touched at all
  — these wings are stale precisely because almost nobody lifts them.
- **Fills:** 4 (queue-aware) = **0.45% overall**, 1.00% among joinable — below S14's incidental
  wing fill rate of 2.5%.
- **Adverse selection:** 0/895 wings settled YES (0.00%), so 0/4 fills settled YES. The toxic
  loss leg the mechanism predicts is **unobserved** in this tape (a sparsity fact, not a
  disproof) — win-leg P&L (filled & settle-NO) mean **+$0.3550** (n=4, real_ask premium net of
  the flat maker fee, broker_truth settlement).
- **Bootstrap** (block-boot by event-hour, filled population): mean +0.3550, 95% CI [+0.2850,
  +0.4250], but **n_units = 2 event-hours** — below the `MIN_CI_UNITS=10` data-adequacy floor.
  This CI is a resampling artifact of 4 wins / 0 losses across 2 units, not a testable edge.
- Under the max-generous relaxation (treat every touched wing as a fill, i.e. drop the queue
  gate entirely) the fill rate only rises to 1.79% — still below the 5% near-zero-fill floor,
  still DEAD. The queue gate is measured as materially binding, not cosmetic.

**Verdict: DEAD via near-0%-fill / data-adequacy null.** Every kill condition in Q23's binding
gate is met: fill rate (0.45%) is below the near-zero floor, and the filled population (2
event-hours) is below the bootstrap's data-adequacy floor, so no CI is trusted regardless of its
sign. This converts S10-maker / L26 from "untested" to **tested-dead**.

Price-source tags: `yes_ask` → `real_ask`; queue depth (`no_bids`) → `real_bid`; settlement →
`broker_truth`; spot (binning only) → `synthetic`; executed volume → drawn from the S14 candle
cache, itself sourced from `real_ask`-tagged trade prints.

## Verification

Independent `verifier` re-run reproduced every number byte-for-byte (895 wings, 402 join, 16
touched, 4 fills, 0/895 and 0/4 settle-YES, +0.3550 mean, identical CI). Confirmed: no network
call anywhere in the script; spot never enters the P&L; the queue gate is materially binding
(collapses 16 touched wings to 4 fills); the DEAD verdict is robust even under the
maximally-generous no-queue relaxation; the 0/895 settle-YES observation is real (not a
settlement-join drop — the winner ticker is present in all 324 settled hours, and far winners
are geometrically possible, just never landed in this window); the fee is the maker flat 1¢ rate,
not the taker rate (L5/L30); the bootstrap unit is the event-hour (L6). **Verdict: CONFIRMED**,
no weakening caveat.

## Gates

`pytest`: 712 passed (22 new). `python scripts/invariants.py --full`: all green (only the
standing non-gating advisories — 2 local stray tape refs, 4 known stray `dt=` directories,
both pre-existing and unrelated to this change).

## Registry action

`kb/strategies/00-index.md` S19 row: `idea` → `dead ✗`.

## Lesson candidates (for a future `kb-distiller` pass)

1. A positive-looking, magnitude-gate-clearing CI can still be DEAD by construction when
   `n_units` is tiny AND the mechanism's predicted loss leg is unsampled — a verdict must gate
   on data-adequacy (filled event-hour count) and on whether the adverse leg was even
   observable, not only on CI sign + tick magnitude.
2. Zero observed toxic events is a sparsity fact, not evidence of safety — a probe conditioning
   P&L on a rare adverse correlation should surface the adverse-leg sample size explicitly (here
   it is 0 of 4 fills, 0 of 895 wings).
3. The committed S14 candlestick cache (`tape/s14_ladder_fillsim/`) is a reusable OFFLINE
   executed-volume source for any queue-aware crypto fill-sim, keyed by ticker over the
   earliest-capture→close window — lets a probe stay fully offline instead of re-fetching.
