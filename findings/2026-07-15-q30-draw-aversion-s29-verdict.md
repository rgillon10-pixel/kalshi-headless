# Q30 / S29 — Soccer draw-aversion underpricing maker probe — VERDICT

Date: 2026-07-15
Probe: `scripts/q30_draw_aversion_maker_probe.py` (read-only over `tape/orderbook_depth/`)
Tests: `tests/test_q30_draw_aversion_maker_probe.py` (24 offline tests, no network)
Settlement cache (fresh, committed): `tape/q30_settlement_cache/settlement.json`
(158 settled `-TIE` markets across 19 discovered soccer series; `broker_truth`)
Literature: `kb/quant-finance/draw-aversion-soccer.md` (distilled at Q21 registration)

## Verdict: **DEAD-by-fillability** — two-agent rule, edge-prober + independent `verifier` CONFIRMED numbers, `verifier` REFUTED the ALIVE framing

## Mechanism and headline (spec population)

Draw-aversion (Forrest & Simmons; Constantinou & Fenton; Franck/Verbeek/Nüesch) predicts
bettors underbet the draw (`-TIE`) leg of 3-way soccer markets. Resting a maker BID at the
draw-YES leg's **earliest pre-close** `best_yes_bid` (queue-aware fill-sim, L39, reused from
Q27), pooled across 19 discovered `-TIE` soccer series (a documented improvement over Q27's
fixed 7-series list — target discovered programmatically, not hardcoded):

- 157 distinct joinable games, fill rate 100% (L53: passes trivially over a wide resting window)
- mean fill price (`real_bid`) **$0.1799**; draw rate among fills **28.03%** (44/157)
- fill-conditional NO-draw rate (binding gate 2, catastrophic adverse leg) **71.97%** (113/157)
- breakeven draw-rate (fill + $0.01 maker fee) **18.99%**; net underpricing edge **+9.03¢**
- block-bootstrap by GAME: mean **+$0.0903**, 95% CI **[+0.0208, +0.1627]**, n=157 games,
  admissible (113 opposing-sign clusters), clears the 1-tick magnitude gate

Every BINDING gate in the queue spec passes on this population. Taken at face value this
contradicts the queue's own honest expectation ("probably DEAD-by-fee") — draw-aversion is
genuinely, measurably present: draws settled ~28% of the time against resting bids priced at
~18¢.

## Why the headline is not a real edge: the entry-timing artifact

The spec entry is the game's **earliest** pre-close snapshot — median **65.6 hours** before
close (up to 168h / 7 days), with a **p90 entry spread of 86 cents**. Hand-inspection of the
widest-spread filled trades (verifier, independent) found rows like:

```
KXUSLCUPGAME-26JUL11OAKSPO-TIE  result=no  entry_bid=0.05 entry_ask=0.94 spread=0.89 ttc=92.1h
  entry yes_bids: [[0.05, 1.0], [0.01, 910.0]]  queue_ahead=1.0
```

A single 1-contract nickel bid against an 87-94¢-wide ask, days before kickoff, is a nominal
lottery-ticket placeholder, not a competitive resting order — the same nominal-price-as-fillable
mistake CLAUDE.md's prime directive forbids, one abstraction up from a synthetic midpoint. The
deliberately-generous queue-aware fill-sim (a cancel ahead counts as advancing us) still marks
these FILLED trivially.

Two honest fillable-entry robustness cuts, run and reported inside the same probe:

| cut | n fills | n games | edge | 95% CI | passes all gates |
|---|---|---|---|---|---|
| **two-sided book** (entry spread ≤ 10¢) | 119 | ~113 | +7.34¢ | **[−0.0065, +0.1564]** — straddles zero, fails tick-magnitude | **NO** |
| **near-close** (entry ttc ≤ 24h) | 15 | 15 | **−4.47¢** (negative) | [−0.2207, +0.1587] — below the 10-game power floor too | **NO** |

Both defensible populations a real trader could actually rest a competitive maker bid in fail
to clear the CI/magnitude gates; the near-close cut goes negative outright. The +9¢ headline is
fully explained by the wide-early-book population, not by a demonstrated fillable edge.

## Verifier findings

Independent from-scratch re-derivation (fresh tape parse, own bootstrap, no shared helpers)
reproduced every load-bearing number bit-for-bit (157 games, 44/113 draw/no-draw split, mean
fill $0.17994, edge +9.03¢, CI within seed noise of the probe's). Confirmed: no lookahead (entry
always genuinely pre-close), L52 scalar filter correctly applied (1 scalar market dropped from
the 158-market cache), the 19-series discovery is correct (fresh grep confirms exactly 19 series
carry a trailing `-TIE` leg; no false positive/negative), and the depth window
(`dt=2026-07-07..2026-07-15`, 07-09 absent) matches the committed tree. `pytest` (24/24) and
`invariants.py --full` both green.

The verifier's recommendation — do not register S29 alive; the honest read is DEAD-by-fillability
under the only defensible fillable-entry populations — was adopted verbatim. The probe's own
verdict logic was patched (post-verification) so a future re-run on updated tape computes this
verdict automatically rather than requiring a human override every time.

## Registry

`kb/strategies/00-index.md` S29 flipped `idea` → **`dead ✗`**. Still **0 proven edges**.

## New lessons

- **L69** — a queue-aware maker fill-sim resting at the *earliest* pre-close snapshot
  systematically enters on thin, often one-sided early books; the fillable-entry restriction
  (two-sided book / near-close) must be the PRIMARY population of any such probe, not a
  robustness footnote applied after a positive headline.
- **L70** — draw-aversion IS directionally present on Kalshi 3-way soccer (empirical record:
  draws settled 28.0% vs resting bids at ~18¢) but does not survive a realistic fillable-entry
  restriction — an outcome-type bias that is real-but-unfillable, distinct from L54's
  favorite/longshot closure (absent-vs-unfillable).
- **L71** — the gate-4 power-floor formula is `sqrt(p(1-p)/n)` (a one-sigma SE), not a
  1.96-scaled half-width; pin this so a future settlement-Bernoulli probe doesn't reach for the
  wrong scaling by reflex.

## Next

If S29 is ever revisited, the correct spec is the fillable-entry-restricted population
(two-sided book ≤10¢ and/or near-close) as the PRIMARY test from the start — not as an
after-the-fact robustness cut on an artifact-driven headline. On today's tape that re-run
already reads DEAD, so no near-term follow-up is queued.
