# S10 — Crypto-hourly reachability decay: first cut → structural DEAD

`2026-07-11` · LOOP-QUEUE Q7 · probe `scripts/s10_reachability_probe.py` ·
tests `tests/test_s10_reachability_probe.py` (16, offline) · read-only over
`tape/crypto_hourly/dt=*.jsonl` (7 valid canonical days: 2026-07-03..08, 10)

## Hypothesis (S10)

Far crypto-hourly range-brackets stay priced *above* their remaining-time reachability as the
hour elapses (retail under-updates the tails), so late in the hour a taker could fade an
over-priced, essentially-unreachable bracket — sell the rich YES, i.e. **buy NO** — for a
fee-clearing edge. Gate: "T-5/2 reachability vs ask > overround+fee; **clear the artifact
noise floor** (Kalshi's 1¢ minimum tick) + the chunky longshot fee; bootstrap by hour; CI>0".

## Method

No continuous intra-hour tape exists. The only within-hour time variation is that two
collectors (cloud + VPS) hit the same hourly group at different offsets, giving ~190/240
(symbol, event_ticker) groups **2–3 `real_ask` captures at different `captured_at`** — an EARLY
capture (~30–48 min pre-close) and a LATE capture (~5–6 min pre-close).

Instead of fabricating a stochastic hitting-probability model from thin data, the probe uses
the **realized settlement as ground truth** (`broker_truth`):

- **Far bracket** = one the market ITSELF parks at/near the 1¢ YES floor at the EARLY capture
  (`yes_ask ≤ threshold`; primary threshold 0.01 = strictly floor-pinned). No external vol
  model invented — the market's own near-zero judgment.
- **Trade booked** (mechanically-available taker trade): buy NO at the **LATE** capture's
  `no_ask` (`real_ask`). Realized P&L = payout − cost − fee, where payout = \$1 if the bracket
  settled NO (did not hit) else \$0 (`broker_truth`), and fee = `core.pricing.fee_per_contract`
  (never hand-rolled — lesson L18).
- **Settlement join:** an event X's settlement is carried by the pass whose
  `previous_settlement.event_ticker == X` (that pass' own `current` event is
  `next_hour_event_ticker(X)`; round-trips with the collector's `previous_hour_event_ticker`,
  unit-tested).
- **Bootstrap unit = the hour**, never the bracket (brackets in one hour are correlated draws —
  lesson L6 / CLAUDE.md / S7c).

Every persisted number carries its tag: entry prices `real_ask`, settlement `broker_truth`.
The stray `tape/crypto_hourly/dt=2026-07-10/` directory of raw blobs is skipped (`*.jsonl`
glob + `is_file` guard — lesson L25).

## Result

Sample: 471 records → 240 current groups → **190 multi-capture** → **164 multi-capture +
resolved settlement**.

**The decay the thesis needs is not observable, because the far brackets are already on the
floor at the EARLY capture.** Across 18,992 far-bracket observations (thr=0.01), the mean
early→late `yes_ask` change is **+0.00014** (essentially none — you cannot decay below a 1¢
floor already hit). This is exactly the "artifact noise floor" the gate warned about, read off
the market's own book.

**The mechanically-available taker trade is capped at ~\$0 by the tick floor.** A genuinely-far
bracket has `yes_ask` at the 1¢ floor, hence `yes_bid = 0`, hence **`no_ask` pinned at \$1.00** —
you pay a full dollar to (at best) win a dollar back. Of 18,992 far observations, only **4
(0.02%)** had any `no_ask < \$1.00` room at all. `fee_per_contract(1.00) = 0`, so the ideal case
(buy NO at \$1.00, settle NO) nets **exactly \$0**, not a positive edge.

Threshold sweep (`real_ask` entry / `broker_truth` outcome), all n_hours = 164:

| thr (early yes_ask ≤) | n_trades | has_room (no_ask<\$1) | settled NO | mean realized P&L |
|---|---|---|---|---|
| 0.01 | 18,992 | 4 (0.02%) | 100.000% | **+\$0.000008** |
| 0.02 | 19,261 | 11 (0.06%) | 99.995% | +\$0.000020 |
| 0.05 | 19,793 | 36 (0.18%) | 99.965% | −\$0.000066 |
| 0.10 | 20,283 | 89 (0.44%) | 99.921% | −\$0.000114 |

Relaxing "far" to find `no_ask < \$1` room only pulls in genuinely-reachable brackets that
sometimes hit — flipping the mean **negative** (a rare catastrophic −\$1 NO loss swamps the
handful of +1¢ gaps). There is **no threshold at which the mean clears zero.**

**Block-bootstrap by hour** (thr=0.01, 10,000 resamples, seed 42, n_hours=164, n_trades=18,992):
mean **+\$0.000008/contract**, **95% CI [+\$0.000000, +\$0.000024]** (`real_ask` / `broker_truth`).

## Verdict: DEAD

The binding bar (block-bootstrapped 95% CI **strictly > 0** at `real_ask` net of fees) is not
met — the lower bound is **+0.000000**, i.e. not strictly positive. And even the point estimate
is economically meaningless: +\$0.000008/contract is ~0.001¢, three orders of magnitude below
the 1¢ minimum tick — it is the rounding residue of a few floored trades where `fee(\$1.00)=0`,
not a fillable edge. Declaring "alive" off a CI whose lower bound is a floating-point 0 and
whose magnitude is unfillable would be exactly the "stretch a descriptive cut into a verdict"
error the charter forbids.

This is a **structural / data-adequacy DEAD**, not a marginal miss: the taker trade the S10
thesis requires does not exist at a positive-edge fillable price. The 1¢ minimum YES tick
mirrors into a \$1.00 NO ask on every genuinely-far bracket, and there is no observable decay
beneath a floor the market already sat on ~40 minutes before close. Same cheap-kill family as
S8's ρ-guard — the artifact floor the gate demanded be cleared cannot be cleared because there
is nothing beneath it.

## What a fuller cut would need (not pursued — the structure, not the sample, is the wall)

- **Continuous sub-hourly tape** (a burst-capture leg, like the S9-motivated ones) would give
  real decay curves — but it would not change the floor: the NO ask is pinned at \$1.00 by the
  tick, so a taker fade has no price to fill at regardless of resolution.
- **The maker side is a different, untested trade** (out of scope for this taker-bar
  milestone): rest a NO offer / sell the rich YES *at* the elevated ask rather than crossing to
  a \$1.00 NO ask. That is S6/S11 territory (maker fee 4× cheaper) and would need the L2 depth
  tape + a fill-sim; it is not falsified here, just not this trade.
- A real reachability model (Brownian bridge on `synthetic` spot vol) could sharpen "far" vs
  "reachable", but the ground-truth settlement already bounds the answer more defensibly than a
  fabricated model would on 164 hours.

## Lesson candidates (for kb-distiller)

- **L-cand A:** Kalshi's 1¢ minimum YES tick mirrors into a **\$1.00 NO ask** on any
  genuinely-far bracket (yes_bid=0). A taker "fade the over-priced tail" strategy therefore has
  no fillable price — profit is capped at exactly \$0 before fees. Any tail-fade edge is
  structurally a **maker** trade, not a taker one. (Generalizes L12's floor-artifact caution to
  the NO side / the fade direction.)
- **L-cand B:** `fee_per_contract(1.00) == 0` (and near \$1.00 rounds to \$0.01) — a bootstrap
  over trades dominated by \$1.00-priced legs can produce a CI whose lower bound is a
  floating-point 0. That is NOT a positive edge; the economic-significance check (magnitude vs
  the 1¢ tick) must gate the CI, or a floored population fakes a hair-above-zero "alive".
- **L-cand C:** When a strategy's own gate says "clear the artifact floor," verify the floor is
  even *observable* first: S10's far brackets were already floor-pinned at the EARLY capture, so
  there was no decay below the floor to measure — the descriptive check (early-capture floor
  fraction) should precede any decay/CI work.
