# Q21 idea-gen round #33 — kalshi-edge-hunter 2026-08-17

**One-line:** Round #33 proposed 3 MAKER candidates anchored on the one fillable-book family
(`orderbook_depth`); the independent `verifier` KILLED all three off committed tape before any
registration — **0 registered, 0 S-numbers burned (next free stays S83)**. Still 0 proven edges.

## Why the round fired
Eligible (TODO / unclaimed / unblocked) queue items, re-derived by each item's LATEST-dated
Status line (L25 file-shape rule, not path existence): **1** — only Q57 (S82 flow-fade,
verifier-reopened, PROVISIONAL/OPEN) is non-terminal. Every other item Q0–Q56 is
DONE / DEAD / BLOCKED / cred- or burst-gated per its newest status. 1 < 2 → a Q21 round is due.
This is the 33rd round. Rounds #28–#31 registered 0; #32 registered S82 (`idea`), which the
Q57 binding probe then found population-inadequate (two-sided only at a 15-min window, one game
short of the L41 floor) — so the pipeline is near-dry and the retro (PR #386, 08-16) has already
flagged saturation. These candidates were proposed in good faith with honest presumptive KILLs;
**0 survivors is a valid, expected outcome** and was NOT padded to quota.

## The one substrate fact that shaped the round
`tape/orderbook_depth/` is the ONLY committed family that carries a real resting book at scale:
full price-size ladders (`yes_bids`/`no_bids` = `[[price, size], …]`, plus `depth`) AND
`best_yes_ask`/`best_no_ask` tagged `real_ask`, across 41 day-files (2026-07-07 →). Round #31's
own deferred lesson was that a MAKER-capture claim on the book-less print tape
(`kalshi_trades`, `crypto_hourly`) is unconstructible without a cited fill model (the S13 wall).
All three round-#33 candidates therefore anchor their FILL on `orderbook_depth`'s real ladders,
not on the print tape — that is the single distinction that separates them from the makers
round #31 killed (candidate A = impact-reversion on kalshi_trades → S80 re-skin; candidate B =
toxicity maker on crypto_hourly → no size field).

## Candidates (full text in the run's working memo; verdicts below)
- **C1 → S83** — Queue-depletion touch-capture MAKER on the depth book: fire on a near-touch
  queue depletion with a thick opposite side, rest at the vacated level, capture the widened
  spread from the next forced taker. Distinctness claim: not S6 (event-gated, not always-on),
  not S19 (posts at the depleted touch = fillability-positive, not a stale far wing), not S22
  (predicts a short-horizon spread, never settlement direction).
- **C2 → S84** — Flow-neutral-window selective MAKER: rest only when `kalshi_trades` net signed
  flow ≈ 0 (informed-flow toxicity filter). Load-bearing question: is this exactly what S78
  (`dead ✗`) already tested, or a distinct construction?
- **C3 → S85** — Transient single-print impact-reversion MAKER: rest at the pre-print level on a
  large-print dislocation. Distinctness claim: not S24 (that was a taker round-trip). Overlap
  risk with C1 and with round-#31 candidate A (ruled an S80 re-skin).

## Verifier disposition — C1 KILL · C2 KILL · C3 KILL (0 survivors)
An independent `verifier` subagent re-measured the substrate on committed tape (12 tool calls)
before any registration. Load-bearing facts it measured this run:
- **Book cadence** (all three depend on it): across `orderbook_depth` GAME tickers, 151,355
  consecutive intra-ticker snapshot gaps → **median 31.5 min, p10 28.2 min; only 0.8% < 5 min,
  0.3% < 2 min, 0.0% < 1 min** (reproduces L283 ~180 min / L328 bimodal).
- **Touch spread** (C2's fee-wall): 152,600 GAME touch obs → **modal spread 1¢ (28.0%), median
  3¢, 41.2% ≤ 2¢**.
- **Maker fee**: `core/pricing.py` `MAKER_FEE_RATE = 0.0175` via `fee_per_contract` with
  round-up-to-cent → effective floor **~$0.01/contract** across the 0.1–0.9 band (S6's flat 1¢).
- **Flow asymmetry** (L279): `kalshi_trades` `taker_book_side` bid 151,968 / ask 61,520 = **71.2%
  one-sided** (matches L279 to rounding).

**C1 → S83 KILL — cadence wall (filter-independent).** The entry trigger is a queue-depletion
event "across consecutive snapshots," but consecutive GAME snapshots are ~31.5 min apart and never
< 1 min. A seconds-to-minutes liquidity event is neither observable (two 30-min-apart books can't
distinguish depletion from ordinary drift) nor fillable-within-window, and the "next taker paying
the widened spread" is ~30 min later, after any transient widening resolved. This is the S9/S79
exit-cadence wall shown to bind the ENTRY signal. Secondary (independently sufficient): the
depletion IS the adverse-selection signal (book cleared because informed flow arrived; the
thick-opposite-side filter only "partly" defuses it), and it degenerates on L279 single-sidedness
(the same `{no:11, yes:0}` shape that sank S82/Q57). Distinctness vs S6/S19/S22 holds but is
necessary-not-sufficient.

**C2 → S84 KILL — S6 fee-wall + S78 holdout null.** The verifier first SETTLED the load-bearing
question: S78's `dead ✗` did NOT test C2's construction — S78 gates on a per-`(series × bucket ×
regime)` cell of realized post-fill markout learned train/holdout; C2 gates on a contemporaneous
net-signed-flow ≈ 0 window. Different proxy, so NOT a byte-identical re-skin. But C2 dies anyway on
two filter-independent mechanisms: (1) **S6 fee-wall** — modal touch spread 1¢, 41.2% ≤ 2¢; the
capturable half of a 1–2¢ spread (0.5–1¢) is ≤ the round-up ~1¢ maker fee BEFORE any adverse
selection, and a flow-neutral gate reduces toxicity but cannot WIDEN the spread; flow-neutral
windows are the quiet windows where S6's frozen-inclusive **−$0.00195** governs. (2) **S78 holdout
null** — the direct markout-optimal filter already returned n=34, mean +$0.0035, 95% CI
[−$0.0087, +$0.0146], `clears_tick_magnitude: false`, 5.80% fill; a contemporaneous-flow proxy is
a strictly weaker instance of the same class and cannot clear where the stronger filter straddled
zero. Same short-the-toxic-side factor family (Hard-Rule-6 ρ cap).

**C3 → S85 KILL — collapses into S80 + L329 + cadence.** S80 (print-VWAP-overshoot maker fade on
the identical `orderbook_depth × kalshi_trades` sports substrate) already tested "fade a
print-driven touch dislocation as a maker" → DEAD-by-CI, mean **−$0.09727, 95% CI
[−$0.18770, −$0.01229]**, 27 games, 69.42% fill. C3 rests at the pre-print level instead of scoring
overshoot but is the same family. It is hit directly by **L329**, which S80 measured on its mirror
leg: adverse-selection cost **+$0.07603 = 101.3% of the static edge before the fee**, because a
resting bid below the post-print touch is filled preferentially when the move was PERMANENT (the
adverse case) and skipped when it REVERTS (the case it bets on). Plus the same ~31.5-min cadence
wall makes transient-vs-permanent impact unseparable and the transient window unfillable.

Cited by the verifier: index rows S6/S19/S22/S24/S78/S80/S82; `core/pricing.py` L111–117; measured
`orderbook_depth`/`kalshi_trades` distributions; L51/L279/L283/L312/L321/L328/L329.

## New verifier lesson candidate (flagged for kb-distiller, NOT minted an L-number this run)
**Cadence is an ENTRY-signal wall, not only an exit wall.** The ~31-min-median / <1%-under-5-min
`orderbook_depth` snapshot cadence (L283/L328) blocks not just fillable exits (S9/S79) but any
maker whose ENTRY trigger is a microstructure event — queue depletion (C1), single-print impact
(C3). If the selecting event is faster than the median snapshot gap it is neither observable nor
fillable-within-window on committed tape, independent of fees or edge sign. A candidate whose entry
gate is a liquidity/print event should be pre-killed on cadence unless a sub-minute book surface
(e.g. Q47 `orderbook_delta`) exists. Generalizes L283/L328 from the exit side to the entry side.
(Left as a candidate rather than a new L-row to avoid the lesson-ID collision churn of the last
three merges; round-#27 precedent for deferring to kb-distiller.)

## Outcome
- **0 of 3 registered** (KILL / KILL / KILL). A valid, expected honest outcome — the 6th
  near-zero round in the last 7 (rounds #28–#31 = 0; #32's S82 found population-inadequate by Q57).
  No candidate was padded to quota. **0 proven edges** unchanged; **next free S-number stays S83.**
- The two-agent idea-stage rule ran in full (producer + independent `verifier`). No
  "trust=FALSE" producer re-derivation is owed: all three verdicts moved in the conservative
  (KILL) direction, not toward survival.
- **The saturation signal is now unambiguous and structural, not idea-capacity:** every maker on
  committed tape faces either the ~31-min book cadence (fast-event entries unobservable) or the
  1¢ round-up maker fee against a 1–3¢ modal spread; every taker faces WALL-A. The two standing
  unblocks are both Ryan-side and data-surface (a sub-minute book = Q47 `orderbook_delta`; more
  book-covered `kalshi_trades` days). This corroborates retro PR #386's "pipeline nearly dry."

