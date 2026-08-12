# Q21 idea-gen round #28 — 0 of 3 candidates survived verifier attack (all killed on committed tape)

**Run:** kalshi-edge-hunter nightly, 2026-08-12 ~04:15Z UTC. **Trigger:** eligible queue count < 2
(full Q0–Q56 rescan = 0 eligible TODO/unclaimed/unblocked, the 6th consecutive idle-adjacent run;
Q56 fully done, Q52/S78 + Q54/S79 data-gated collect-and-revisit, everything else DONE / cred- or
burst-gated / on a dead strategy) → Q21 round required per the edge-hunter spec.

## Outcome
Three NEW falsifiable S-candidates (S82/S83/S84) proposed by the producer, each attacking a
mechanism round #27 (α draw-tie taker / β weather known-outcome / γ index low-fee) did NOT test.
An independent `verifier` subagent attacked each against committed tape BEFORE registration
(two-agent pre-registration discipline). **0 survived.** No registration, no new queue item, no
registry flip — still **0 proven edges**. A 0-registration round with honest verifier refutations
is a valid outcome. **No S-numbers were burned** (round #27 precedent): next free stays **S82**.

Surface note: `tape/kalshi_trades/` is byte-frozen at 6 backfill days (last `dt=2026-08-03`; the
collector is Ryan-key-gated, Q47/Q51). Rounds #25–#27 worked this same frozen tape. The binding
constraint remains the DATA SURFACE, not idea capacity.

| cand | name | verdict | load-bearing tape fact (verifier-rederived) |
|---|---|---|---|
| **S82** | Size-conditioned informed-flow settlement follow (large-print aggressor continuation) | **KILL by CI (edge, not data)** | Population **66 settled games** (clears the L41 floor). Entered at the aggressor's OWN print price (a *generous* zero-slippage follower fill), followed `taker_book_side` to settlement net one 7% `core.pricing` taker fee, block-bootstrap **by game**. CI **straddles zero at every size decile** and the mean gets **monotonically worse as size rises**: ≥p90 mean −0.0089 CI [−0.0777,+0.0447]; ≥p95 −0.0178 [−0.084,+0.040]; ≥p99 −0.0397 [−0.102,+0.031]. This *directly refutes* the Easley–O'Hara "informed traders trade larger" premise on this tape — bigger prints predict settlement **worse**. Same taker-fee + adverse-selection wall as S79. |
| **S83** | Realized effective-half-spread maker-capture on the print×book join | **KILL / FOLD (S78; S6/S13)** | The producer's data-inadequacy kill was itself WRONG (**62.76%** of broker_truth prints join a ≤15-min book — 133,985 prints / 72 tickers / 57 settled games — not the 0.46% L280 slice; the high-volume days hold 46–48 depth captures each). But the mechanism dies anyway: the headline `\|print−mid\|−maker_fee` = **+0.1185 CI [+0.081,+0.140]** is a **stale-mid artifact**, not a spread — `\|print−mid\|` collapses 0.160→0.128→0.085→0.031 as print-to-book age shrinks 15min→5min→2min→30s, while the book's OWN half-spread `(best_ask−best_bid)/2` is a flat **0.7¢** throughout. Real capturable half-spread **0.7¢ < 1¢ maker fee** (`fee_per_contract(·,MAKER_FEE_RATE)=0.01`) → the **S6/S13 flat-fee->spread wall reproduces**, net negative; and "resting maker before the cross" against the measured **+0.015 adverse markout** IS S78's registered markout lane → **folds into S78**. |
| **S84** | Trade-intensity burst as a settlement-direction signal on sports | **KILL by CI (negative)** | Population **59 settled games** (yes 39 / no 31 — healthy side variation, not S79's one-sided-support artifact). Followed net aggressor direction in each game's top print-arrival-rate window to settlement, net 7% taker fee, block-bootstrap by game. CI **entirely below zero**: [−0.168,−0.010] (60s bins), [−0.158,−0.013] (300s bins) — not merely straddling. Also fails to beat an arbitrary first-window benchmark (−0.080), so intensity adds nothing beyond the L130 mid-efficiency wall + the taker fee. |

## Producer-spec errors the verifier caught (recorded, not hidden)
1. **S83's "~0.46% L280 data-inadequate slice" is FALSE** — 62.76% of prints join a ≤15-min book;
   the high-volume trade days (07-07/07-11/07-12) hold 46–48 depth captures, not the ~4 the L280
   deep-dive slice implied. The kill is on the EDGE (0.7¢ real spread < 1¢ fee), not on adequacy.
2. **The "settled population may be <10" kill triggers for NONE of the three** (66 / 57 / 59
   settled games via `core.settlement_sources.resolve_market_results` across all 10 declared
   families). The "9 games" in the surface note was a stale `dt=2026-08-03`-only figure; the full
   6-day tape clears the L41 floor comfortably. (The registered cousin S79 itself re-derives to
   **45 settled game units**, mean −0.077 CI [−0.219,+0.069], DEAD-by-CI — consistent.)
3. **S83's "survives S6/S13 because it measures the REALIZED spread" is inverted** — measured
   against the real book, the realized half-spread (0.7¢) *reproduces* S6/S13; it IS S6/S13.

## Verifier lesson candidate (flagged for kb-distiller, NOT enshrined here)
`\|print − contemporaneous_mid\|` off a sparsely-captured book is dominated by **price drift
between the capture instant and the print**, not by the bid-ask spread. It inflates monotonically
with quote age (0.031 @≤30s → 0.160 @≤15min on this tape) and must never be read as a capturable
maker half-spread — always compare against the book's own `(best_ask−best_bid)/2`. This is the
pt1 synthetic-price-as-fill error in a new costume (a positive CI on a quantity that is not a
fillable edge). Generalizes the price-provenance discipline to the print×book join.

## Provenance / discipline
- All CIs, populations and counts re-derived by the `verifier` from committed tape; nothing
  trusted from proposal prose. Fees recomputed from `core.pricing` (7% taker, 1.75% maker).
  Bootstrap unit = GAME (L6, via `q51_maker_fillsim.game_of`); floor = 10 units (L41); settlement
  via `core.settlement_sources.resolve_market_results` across all 10 families (L165 / issue #310).
- A pre-registration verifier attack is the mandated step for idea-stage candidates; it ran and
  returned 0 survivors. No candidate was registered, so nothing here is verdict-class.
- Tape read: `tape/kalshi_trades/`, `tape/orderbook_depth/`, `tape/{settlement_ledger,q26,q30,q51}`.
- Still **0 proven edges.** Binding constraint stays the DATA SURFACE (multi-day `kalshi_trades`
  aimed at book-covered tickers; Q47/Q51 collector, Ryan-key-gated). Consumed nothing → next free
  stays **S82**.
