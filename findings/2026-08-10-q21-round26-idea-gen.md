# Q21 idea-gen round #26 — 2 of 3 candidates survived verifier attack (first registrable survivors since S34)

**Run:** kalshi-edge-hunter nightly, 2026-08-10 ~04:15Z UTC. **Trigger:** eligible queue count < 2
(Q53 CLOSED, Q54/S79 DEAD-by-CI, Q52/S78 not-runnable) → Q21 round required per the edge-hunter spec.

## Outcome

Three NEW falsifiable S-candidates proposed; an independent `verifier` subagent attacked each against
committed tape BEFORE registration (two-agent discipline, LOOP-QUEUE.md step 5). **2 survived, 1 killed.**

| cand | name | verdict | load-bearing tape fact |
|---|---|---|---|
| α | Perp-anchored crypto-hourly near-money staleness taker | **DEAD — sub-hourly-cadence (S9-class)** | `crypto_hourly` = ONE snapshot per event ~5 min pre-close, every ~3h; `perp_tape` = 7 captures/day. No intra-hour series exists on either leg, so the "briefly stale ask on a sharp intra-hour move" mechanism is structurally unmeasurable. |
| β | Print-VWAP-overshoot contrarian maker fade (late sports flow) | **REGISTER → S80** | `tape/kalshi_trades/` = 76 distinct sports games / 6 trade-days / 213k `broker_truth` prints (≫ 10-game floor); `orderbook_depth` median intra-ticker gap ~29 min on TRADED sports tickers (≈6–12 snapshots/game) — refutes the proposal's own L283-`~3h` blocker. Not the sign-flip of taker S79. |
| γ | Funding-regime-conditioned crypto-hourly directional settlement bias | **REGISTER → S81** | `hyperliquid_funding` genuinely hourly, regime contrast pin 848 / sub-baseline 607 / negative 179; joinable to 215 BTC captured settlement events over ~338 regime runs (≫ 10-unit floor even collapsed to run-level blocks); near-money brackets carry genuine 2-sided `real_ask` (e.g. 0.44/0.50 @1¢) so S10's 1¢-pinned no-fillable-price kill does not apply. |

Full candidate specs (mechanism/data/gate/kill/survival paragraph) are in the run's scratch and reproduced
verbatim in the S80/S81 registry rows.

## Why this round matters (against the anti-treadmill posture)

Rounds S43–S79 registered only `collect-and-revisit` shells or died at the idea/data-adequacy stage,
because no genuinely new *adequately-cadenced* tape surface had appeared (the retro's #208/#271 diagnosis).
Round #26 breaks that specifically because the multi-day `tape/kalshi_trades/` backfill (phase-1/phase-2,
2026-08-08/09) created a NEW high-frequency `broker_truth` surface **and** the verifier's independent
cadence re-measurement showed `orderbook_depth` is far finer (~29 min) on the traded-sports subset than
the ~3h figure the graveyard has been citing as a blanket maker-fill blocker. Both S80 and S81 are
`binding-test-defined` idea-stage only — NO CI, NO P&L, NO kill, NO registry flip of any existing
strategy; still **0 proven edges**. Each carries an honest weak-prior warning and a defined kill.

## Verifier's lesson candidates (flagged for kb-distiller, not enshrined here)

1. `crypto_hourly`'s true cadence is **one snapshot per event ~5 min pre-close, sampled every ~3h** (not
   "hourly"); `perp_tape` is a **7×/day snapshot**. Any strategy asserting intra-hour Kalshi-vs-perp
   dynamics is S9-dead on this tape.
2. **L283 scope reconciliation owed:** measured `orderbook_depth` cadence is ~29 min on TRADED sports
   tickers, contradicting L283's ~3h if that figure is read as universal. Reconcile L283's population
   scope before it is cited again as a maker-fill blocker (it gates S80's binding test directly).

## Provenance / discipline

- All numbers re-derived by the `verifier` from committed tape; nothing trusted from proposal prose.
- Registration of a new idea-stage candidate is NOT verdict-class (no CI, no kill, no status flip of an
  existing row) — the mandated step is the pre-registration verifier attack, which ran and passed 2/3.
- The binding tests for S80/S81 are future `edge-prober` milestones under full two-agent discipline; a
  bootstrap CI at real asks net of fees remains the only proof of edge.
