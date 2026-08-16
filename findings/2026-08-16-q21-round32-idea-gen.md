# Q21 idea-gen round #32 — 1 of 3 survived (S82); the survivor rests on a SEPARATE family's real_ask, and the "trust=FALSE" re-derivation caught the join key

**Run:** kalshi-edge-hunter nightly, 2026-08-16 ~04:15Z UTC. **Trigger:** eligible queue count < 2.
Full Q0–Q56 file-shape rescan (L25, each item's LATEST dated status) = **0 eligible
TODO/unclaimed/unblocked** → Q21 round required per the edge-hunter spec.

**Two-agent pre-registration discipline ran for real this round.** This session carried the
`Agent`/`verifier` subagent, so each candidate was attacked by an independent agent that
re-derived every load-bearing number off committed tape BEFORE any registration. **And, because
one candidate flipped TOWARD survival, the producer independently re-derived its substrate to the
digit** ("trust=FALSE on a flip-toward-survival verdict", the S68/round-#19 precedent) — the
reconciliation is documented below and was itself load-bearing.

## Outcome

Three NEW falsifiable candidates, each aimed at the freshest/richest committed surface. An
independent `verifier` attacked all three. **1 SURVIVE (C1 → registered S82) / 2 KILL (C2, C3).**
This is the **first Q21 survivor since S78 (2026-08-05)**, which then tested DEAD. A registration
is not a proof — S82 is an `idea` with a binding probe (Q57), presumptive KILL. Still **0 proven
edges.** Consumed S82 → next free = **S83**.

| cand | name | verdict | load-bearing tape fact |
|---|---|---|---|
| **C1 → S82** | Game-level `count`-weighted signed-taker-flow **FADE** taker, held to settlement | **SURVIVE → registered `idea`** | 72 distinct traded `*GAME` game-ids → **34 settled in `settlement_ledger` → 34 also depth-covered** (triple-join {traded ∩ settled ∩ depth}) ≥ the L41 floor of 10. The fillable entry `real_ask` lives in `tape/orderbook_depth/` (`best_yes_ask`/`best_no_ask`, `price_source_tag: real_ask`), a SEPARATE family covering the same GAME tickers — so the "print tape has no book → WALL-B" reflex does NOT kill it. It survives its dead cousin S79 (aggressor-flow *continuation* taker, DEAD-by-CI [−0.2724,+0.1521]) because a dead FOLLOW ≠ a dead FADE, and round-#28's "bigger prints settle WORSE" residual gives the `count`-weighted fade a plausible non-zero positive sign. Fate rests on whether the real-ask CI clears WALL-A — a bootstrap question, not a committed-tape fact. |
| **C2** | Near-money `crypto_hourly` two-sided income maker on the census-confirmed 418 units | **KILL (WALL-B + L39 + S14 family)** | `crypto_hourly` outcome keys are exactly `[cap_strike, floor_strike, no_ask, no_bid, price_source_tag, strike_type, ticker, title, yes_ask, yes_bid]` — **no size/volume/count/depth field.** A "forward-interval" fill (a later snapshot showing the price crossed the resting level) is the textbook L39 queue-blind print-through, biased UPWARD, and with no volume field you cannot even apply L39's necessary-but-insufficient volume gate. Same near-money slice, same substrate, same 1¢ fee as the DEAD S14 (crypto-ladder overround-underwriting maker, CI −$0.0453). Near-money 0.40–0.60 population is also only ~30 brackets. |
| **C3** | Recall-audit label-unlock settlement-basis taker (the 367 net-new labels) | **KILL (L41 / L359)** | Reproduced the 2026-08-15 audit's own `reports/settlement_source_recall_audit.json`: the 367 net-new `broker_truth` labels land on **8 of 110,632 depth legs**, making **4 of 4,171** depth event units newly fully labeled — the fillable real_ask substrate gains **4 units < the L41 floor of 10.** The 38 price legs are `sports_pairs`, which L359 confirmed schema-only (`result` on ZERO objects, `status=="active"` on all 31,016). This is exactly the audit's own F2/L359 finding: a label count is not a scoreable-unit count. |

## The reconciliation that made the registration honest (the durable methods product)

The producer's FIRST independent re-derivation of C1's substrate returned **1 traded game / 0
settled** — flatly contradicting the verifier's 72/34. That is precisely the divergence the
"trust=FALSE on a flip-toward-survival verdict" rule exists to force into the open. The cause:
`tape/kalshi_trades/` carries **`event_ticker: None`** on every row, so joining on `event_ticker`
reads a single null key. The game identity must be derived from the ticker:
`ticker.rsplit('-',1)[0]` (strip the outcome suffix, e.g.
`KXKBOGAME-26JUL070530KIALOT-KIA` → `KXKBOGAME-26JUL070530KIALOT`), which is exactly the
`event_ticker` that `settlement_ledger` and `orderbook_depth` DO carry. Re-run with the correct
key: **72 traded → 34 settled → 34 depth-covered**, reproducing the verifier to the digit.

Two durable facts fall out, both baked into the S82/Q57 registration so the probe cannot repeat them:

> **(1) A probe that joins `kalshi_trades` on `event_ticker` silently reads 0 units** — the field
> is null; the game-key is the outcome-suffix-stripped ticker.

> **(2) A "print tape has no resting book" (WALL-B) reflex is NOT sufficient to kill a taker-FADE
> sports probe.** The resting `real_ask` can live in a SEPARATE family (`orderbook_depth`)
> covering the same GAME tickers; the fillable-price surface is the UNION of families, not the
> trade tape alone. (Deferred to `kb-distiller` — NOT enshrined here; this round produced an
> idea-stage registration, not a verdict-class output.)

## Why S82 is a legitimate registration and not a graveyard re-skin

The binding discipline (verifier + producer) both had to clear three specific attacks, and the
one that could still bury it is deferred to the probe, not assumed away:

- **Adequacy:** 34 independent games ≥ L41 floor of 10, unit = the game (one directional bet),
  so NOT the within-game complementary-outcome trap.
- **Constructible price:** entry is a real `orderbook_depth` `real_ask`, not a synthetic
  reconstruction (the pt1 forbidden move is avoidable).
- **The L51 risk is real and is the probe's job:** on a 2-way market a fade and a follow are
  mechanically complementary, so Q57's binding gate (3) requires pre-registering the aggregation
  window and PROVING it differs from S79's print-level continuation window BEFORE scoring — else
  L51 collapses S82 into the already-dead S79 and the measurement is void.

Honest expectation stated up front: **presumptive KILL.** WALL-A (7¢ taker + bracket overround)
has killed every taker cousin; the ONLY thing distinguishing S82 from the dead S79 is the
round-#28 "bigger prints settle worse" residual applied with the opposite sign. A clean
CI-straddle-zero converts S82 to tested-dead and closes the signed-flow-taker family — a valid,
cheap, decisive outcome either way.

## The saturation signal, and what actually changed

Rounds #27–#31 were five consecutive 0-registration rounds; the binding constraint has been the
DATA SURFACE, not idea capacity, and it still is — the two named unblocks (multi-day
`kalshi_trades` on book-covered tickers Q47/Q51; a forward `settlement_ledger` past `dt=2026-07-22`
Q45) remain Ryan-side and unchanged. What produced a survivor this round was NOT a new tape
surface but a new **join**: recognising that the fillable price for a trade-tape strategy can be
sourced from a different family. That is a methods unlock, not a data unlock — and it is scoped to
this one candidate class (taker fade with a depth-family entry), not a general escape from the walls.

## Provenance / discipline

- All counts re-derived by an independent `verifier` AND independently reconciled by the producer
  from committed tape (`tape/kalshi_trades/` 6 days, `tape/orderbook_depth/`, `tape/settlement_ledger/`,
  `tape/crypto_hourly/`, `reports/settlement_source_recall_audit.json`). Fees only via `core.pricing`
  (`TAKER_FEE_RATE=0.07`, `MAKER_FEE_RATE=0.0175`). Bootstrap unit = independent game (L6); floor =
  10 units (L41).
- One candidate registered as `idea` (S82) + queue item Q57 appended; two killed at idea stage.
  Nothing here is verdict-class — no CI, no P&L, no registry flip to `dead`/`proven`. Still
  **0 proven edges.**
