# Q21 idea-gen round #27 — 0 of 3 candidates survived verifier attack (all killed on committed tape)

**Run:** kalshi-edge-hunter nightly, 2026-08-11 ~04:15Z UTC. **Trigger:** eligible queue count < 2
(Q56 fully done — both S80 dead-flipped and S81 verifier-confirmed admissible NULL; Q54/S79 DEAD;
Q52/S78 collect-and-revisit not-runnable at 34/328 games; everything else gated/blocked) → Q21 round
required per the edge-hunter spec.

## Outcome

Three NEW falsifiable S-candidates proposed; an independent `verifier` subagent attacked each against
committed tape BEFORE registration (two-agent pre-registration discipline). **0 survived.** No
registration, no new queue item, no registry flip — still **0 proven edges**. A 0-registration round
with honest verifier refutations is a valid outcome.

| cand | name | verdict | load-bearing tape fact (verifier-rederived) |
|---|---|---|---|
| α | Draw-underpricing TAKER buy on 3-way soccer `-TIE` legs, fill-evidenced by executed prints (the S29 fill-first revival) | **DEAD by CI (edge, not data)** | Data ADEQUATE — `tape/kalshi_trades/` carries **35 distinct non-WC 3-way-league `-TIE` tickers** (KXNWSL/KXALLSVENSKAN/KXUECL/KXURYPD/KXKLEAGUE/…), 34 settled (11 draws / 23 no) ≫ the 10-game floor. Block-bootstrap **by game** (L6, n=34, genuine sign variation), net taker-buy-tie P&L at executed `yes_price` net one 7% `core.pricing` fee → **95% CI [−0.120, +0.100]**, straddles zero. Every charitable re-entry also straddles (earliest-print [−0.096, +0.223]; low-price ≤0.30 [−0.007, +0.308]; median [−0.118, +0.103]). |
| β | Weather-actuals "known-outcome" late taker (observed-actual timing, not forecast calibration) | **DEAD — CI + unmeasurable precondition** | The "outcome observable before settle" precondition is **NOT on tape**: `tape/weather_actuals/` rows are captured ~8h AFTER close (close 05:00Z, actuals captured 13:02Z) with no high-realization timestamp. Honest no-look-ahead test (max-`yes_ask` bracket at a fillable ≤2h-pre-close snapshot), block-bootstrap by station (40 blocks / 416 events) → net taker P&L **95% CI [−0.0049, +0.0402]**, straddles zero. Near close the fillable book is mostly penny junk (median favorite `yes_ask` 0.01). |
| γ | Low-fee S&P/NDX index-bracket longshot-fade re-test (the 3.5% fee lever) | **DEAD — data-DEAD** | `tape/universe_sweep/` contains **exactly ONE** S&P/NDX index bracket row in the entire tape (`KXINXHUD-26JUL211600-T7508.67`, single snapshot) and **zero** NDX rows — ~10x below the L41 ≥10-unit floor. The 3.5% fee lever is untestable on committed tape. |

Full candidate specs (mechanism/counterparty/data/gate/kill/survival paragraph) are in the run's
scratch and reproduced in the log entry.

## Why α matters (a genuine NULL, not a treadmill re-skin)

S29 (soccer draw-aversion maker bid) was killed 2026-07-15 by *fillability* while its at-quote edge
was POSITIVE (draw rate among fills 28.03% vs breakeven 18.99%, CI [+0.0208, +0.1627]). Round #27's α
tested the natural next question — does that edge survive when the fill is an *observed* `broker_truth`
executed print instead of an assumed maker rest? The answer is **no**: on 35 non-WC 3-way-league TIE
series with actual executed prints, the tie is **well-calibrated** (draw-games average price 0.58–0.70,
non-draw 0.12–0.29), so block-by-game net of the 7% taker fee there is no edge (CI straddles zero). The
pooled print-level +0.079 was a **print-count-weighting look-ahead artifact** — draw games accrue huge
late-game volume at already-high tie prices (e.g. NWSL-DENBOS 10,156 prints @ $0.63), which conflates
within-game resolution drift with edge. This closes the S29-revival door with real fill evidence, not
prose.

## Verifier lesson candidates (flagged for kb-distiller, NOT enshrined here)

1. **Print-count-weighting look-ahead in sports pricing:** pooling per-print P&L across an in-game
   price path conflates within-game resolution drift with edge; the only admissible unit is the GAME
   (reinforces L6). On round #27's α tape, pooled +0.079 vs block-by-game ~0 on the identical data.
2. **Winner-selection look-ahead in weather:** conditioning on the settled-winning bracket gives
   frac>0 = 100% by construction; any "known-outcome" weather taker must first prove the outcome was
   OBSERVABLE at the trade timestamp, which needs an observation-time field `tape/weather_actuals/`
   does not carry.

## Provenance / discipline

- All CIs and counts re-derived by the `verifier` from committed tape; nothing trusted from proposal
  prose. Fees recomputed from `core.pricing` (7% taker; 3.5% index rate for γ).
- A pre-registration verifier attack is the mandated step for idea-stage candidates; it ran and
  returned 0 survivors. No candidate was ever registered, so nothing is verdict-class here.
- Tape read: `tape/kalshi_trades/`, `tape/weather_books/`, `tape/weather_actuals/`,
  `tape/universe_sweep/`, `tape/{q26,q30,q51}_settlement_cache/`.
