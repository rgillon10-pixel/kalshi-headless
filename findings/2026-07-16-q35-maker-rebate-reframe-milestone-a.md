# Q35 Milestone A — Maker-rebate reframe of the 5 fee-killed maker candidates

`2026-07-16` · LOOP-QUEUE.md **Q35** (analysis half) · script
`scripts/q35_maker_rebate_reframe.py` · tests `tests/test_q35_maker_rebate_reframe.py`
(10, offline, pin the `rebate_swap`/`_group`/`filter_two_sided_fills` arithmetic) ·
**verifier: REFUTED then CONFIRMED** (two rounds — see trail below) · two-agent rule
satisfied · **no registry status changed** (Q35 spec: a fee-line CI flip is a candidate,
never a proven edge) · every price below carries its source tag via each source strategy.

## The question

Five maker-side candidates died PARTLY on Kalshi's flat ~1¢ maker fee (`core.pricing`
`MAKER_FEE_RATE`, `fee_per_contract(P, MAKER_FEE_RATE) == $0.01` at every interior price,
L30): **S13** (sports maker bid at DK-devig fair−1¢), **S19** (crypto wing-fade maker
short), **S21** (sports-longshot maker rich-ask sell), **S23** (favorite settlement-
underpricing maker bid), **S29** (soccer draw-aversion maker bid). Polymarket's Fee
Structure V2 PAYS makers a rebate instead of charging a fee (~+0.5¢/contract conservative,
~+1.25¢/contract the Polymarket US venue figure — see CLAUDE.md's 2026-07-15 regime-change
section). Milestone A: read-only, re-run each strategy's existing simulation over its
existing committed tape/cache, swap the fee line only (Kalshi fee removed, rebate added),
and report which candidates flip from DEAD to a fee-line CI-positive candidate.

## Method

`scripts/q35_maker_rebate_reframe.py` imports each of the 5 source scripts as a module and
calls their own simulate/aggregate functions directly — no re-derivation of their logic, no
network, no live fetch, no tape mutation. Per filled/settled unit it recovers the Kalshi
maker fee from the row's own price via `core.pricing.fee_per_contract(price, MAKER_FEE_RATE)`
(never hand-rolled) and computes three parallel P&L series: **as-is** (the already-verdicted
Kalshi-fee number, a correctness check against each committed finding), **+0.5¢ rebate**, and
**+1.25¢ rebate** (fee removed + rebate added — `rebate_swap`). Because the Kalshi maker fee
is a flat $0.01 at every interior price, the per-contract swing is an exact constant
(`kalshi_fee + rebate`). Each series is block-bootstrapped (`core.bootstrap.block_bootstrap`)
on the SAME unit the original strategy blocked on (game for S13/S21/S23/S29; event-hour for
S19) and run through `clears_tick_magnitude`. A data-adequacy floor of 10 distinct block
units gates every verdict (S19/S21 fail it outright).

## Two-agent trail (two rounds — the first round was REFUTED)

1. **Producer** (edge-prober): built the script, reported "1/5 flips (S13 only)."
2. **Verifier round 1: REFUTED.** Independently re-derived S13/S19/S21/S23 exactly, but
   caught that `collect_s29` fed `build_draw_trades()`'s **raw, unfiltered earliest-pre-close-
   entry population** (n=157) into the reframe. That population's +9.03¢ headline is an
   entry-timing artifact `findings/2026-07-15-q30-draw-aversion-s29-verdict.md` itself
   disowns as the basis for S29's DEAD-by-fillability verdict — the real basis is the
   **two-sided-book entry cut** (`entry_yes_spread <= 0.10`, n=119 fills), which the finding
   reports straddles zero even with the Kalshi fee. The verifier built an independent check
   script over that cut and got a CI that clears the tick gate at +1.25¢ — directly
   contradicting the "only S13 flips" headline.
3. **Fix**: `collect_s29` now filters through a new pure helper `filter_two_sided_fills()`
   before building bootstrap units, matching the finding's actual DEAD-verdict population.
4. **Verifier round 2: CONFIRMED.** Re-ran the fixed script; S29's three CIs reproduced the
   round-1 verifier's independently-computed numbers to 4 decimal places; the other 4
   strategies were confirmed byte-identical to round 1 (diff-checked against the fix commit).
   Full `pytest -q` and `python scripts/invariants.py --full` green.

## Result — corrected headline: 2/5 flip, not 1/5

| Strategy | block unit | n units | as-is CI (Kalshi fee) | +0.5¢ CI | +1.25¢ CI | verdict |
|---|---|---|---|---|---|---|
| **S13** sports maker bid | game | 80 | `[-0.00020,+0.00040]` (mean +0.00009) | `[+0.01480,+0.01540]` ✓clears | `[+0.02230,+0.02290]` ✓clears | **FLIPS** (both scenarios) |
| **S19** crypto wing-fade | event-hour | 2 | `[+0.285,+0.425]` | `[+0.300,+0.440]` | `[+0.308,+0.448]` | STAYS DEAD — data-adequacy (n<10) |
| **S21** sports-longshot rich-ask | game | 0 | none (0 fills) | none | none | STAYS DEAD — data-adequacy (0 fills) |
| **S23** favorite underpricing | game | 23 | `[-0.24348,+0.13696]` (mean −0.0404) | `[-0.22848,+0.15196]` | `[-0.22098,+0.15946]` | STAYS DEAD — lost by more than the fee line |
| **S29** draw-aversion (two-sided-book cut) | game | 119 | `[-0.00647,+0.15639]` (mean +0.0734) | `[+0.00853,+0.17139]` (fails tick gate) | `[+0.01603,+0.17889]` ✓clears | **FLIPS** (+1.25¢ only) |

## Honest caveats — a flip here is a CANDIDATE, not a proven edge

- **S13's flip is mechanical.** `bid = fair − 1¢` by construction, so the pre-fee edge is a
  fixed ~1¢; the Kalshi fee happened to eat almost exactly that. The flip says nothing about
  whether the DK-close devig anchor is even right — it is purely the fee-line arithmetic
  found by design, already flagged in the original S13 finding.
- **S29's flip is fragile and scenario-dependent.** It clears only at the +1.25¢
  (Polymarket-US) rebate, not the conservative +0.5¢ figure, and the finding's own near-close
  robustness cut (a stricter, more realistic maker-fill population) goes CI-negative even
  before any rebate — that cut was not re-run under the rebate here and would need to be
  before S29 is treated as a serious candidate.
- **S19/S21 cannot be revived by any rebate** — they are starved of block units (2
  event-hours / 0 fills), not fee-killed; no fee-line arithmetic manufactures data.
- **S23 lost by more than the fee line** (mean −4.04¢, roughly double the largest rebate
  swing of +2.25¢) — the rebate narrows the loss but the CI stays firmly on the negative
  side.
- Per Q35's own spec: any flip here still owes **Milestone B** (BUILD, gated on the
  Polymarket collector) — portability (does Polymarket's market shape even host the
  strategy?), resolution-basis parity, and the full real-ask/real-fill bar on the actual
  venue — before it is anything more than a candidate worth re-testing if/when a Polymarket
  execution leg exists.

## Registry / bookkeeping

No status change in `kb/strategies/00-index.md` — Q35 Milestone A is explicitly scoped as
read-only analysis that never flips a registry entry. Still **0 proven edges**.

## New lesson candidates (for kb-distiller)

- A fee/rebate reframe of an already-DEAD strategy must re-derive its number from the
  population the strategy's OWN verdict rests on, not from whichever aggregate function is
  easiest to import — a robustness-cut population and its parent "headline" population can
  give opposite fee-line-flip answers (S29: raw n=157 "only S13 flips" vs. two-sided-book
  n=119 "S13 and S29 both flip"). Always re-read the source finding's verdict basis before
  reusing its simulate function in a downstream reframe.
- Because Kalshi's maker fee is a flat $0.01 (L30), any fee↔rebate reframe is an exact
  per-contract constant shift; the "does it flip" question reduces to whether the as-is CI's
  lower bound sits within `-(fee+rebate)` of zero. Only sub-~2¢ fee-line losers (or near-
  misses) can flip — a strategy that lost by more, or died on adequacy/fillability, cannot be
  revived by the fee line alone.
